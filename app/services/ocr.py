"""OCR service — local-only document processing with dual preprocessing and LLM synthesis.

Pipeline
--------
1. Validate file size against ``settings.MAX_FILE_SIZE_MB``.
2. Route by MIME type:
   - ``application/pdf`` → text extraction (``pdfplumber`` → ``PyMuPDF``),
     then image-based dual-OCR if text extraction yields nothing.
   - ``image/*`` → standardize → dual-preprocess → Tesseract ×2 → LLM synthesis.
3. Standardization: DPI normalisation to 300 via ``standardize_to_jpg`` (critical
   for Tesseract to interpret text at the correct scale).
4. Dual preprocessing per image:
   - Version A: greyscale + sharpening + contrast enhancement.
   - Version B: greyscale + sharpening + b/w threshold.
   Both are fed to Tesseract independently with ``lang=deu``.
5. LLM synthesis via ``OCR_SYNTHESIS_MODEL`` (default ``deepseek/deepseek-v4-flash``):
   compare both OCR results, reconcile differences, apply spell/grammar correction.
6. Normalize cleaned text via ``app.utils.text.normalize_text``.
7. Return UTF-8 string.
"""

# Semantic Version: 0.2.1

from __future__ import annotations

import asyncio
import io
import logging
from typing import NamedTuple

import fitz  # PyMuPDF
import pytesseract
from fastapi import UploadFile
from PIL import Image

from app.core import config
from app.utils.image import PreprocessedPair, preprocess_for_ocr, standardize_to_jpg
from app.utils.pdf import extract_pdf_text
from app.utils.text import normalize_text

logger = logging.getLogger(__name__)


class DualOCRResult(NamedTuple):
    """Tesseract output from both preprocessed image versions."""
    greyscale_contrast: str  # OCR text from greyscale + contrast image
    black_white: str         # OCR text from black-and-white thresholded image


class OCRFailedError(Exception):
    """Raised when all OCR back-ends produce empty text."""


# Tesseract configuration for German document OCR.
# PSM 3: Fully automatic page segmentation (handles mixed layouts).
# OEM 3: LSTM neural net mode (best accuracy for modern Tesseract 5.x).
_TESSERACT_CONFIG = "--psm 3 --oem 3"
_TESSERACT_LANG = "deu"

# Maximum image dimension (width or height) before down-scaling.
# Extremely large scans can cause Tesseract to run slowly or produce
# truncated output.  5000 px is ~16.7 inches at 300 DPI — generous.
_MAX_IMAGE_DIMENSION = 5000


async def process_document(file: UploadFile, *, synthesize: bool = True) -> str:
    """Extract and normalize text from a scanned document or image.

    Uses dual preprocessing (greyscale+contrast AND black/white thresholded)
    for every image-based OCR pass, then feeds both Tesseract results to the
    configured ``OCR_SYNTHESIS_MODEL`` LLM for comparison, reconciliation,
    and spell/grammar correction.

    Parameters
    ----------
    file : UploadFile
        Uploaded file (PDF, JPG, PNG, etc.). Must be smaller than
        ``settings.MAX_FILE_SIZE_MB``.
    synthesize : bool
        If True (default), run LLM synthesis on dual-OCR results.
        If False, fall back to basic normalization of both OCR outputs
        combined (useful when LLM is unavailable).

    Returns
    -------
    str
        Cleaned, normalized UTF-8 text.

    Raises
    ------
    ValueError
        If the file exceeds the configured size limit.
    OCRFailedError
        If all extraction tiers yield empty text.
    """
    cfg = config._get_settings()

    # Enforce size limit (SpooledTemporaryFile has sync seek/tell).
    file.file.seek(0, 2)
    size_bytes = file.file.tell()
    max_bytes = cfg.MAX_FILE_SIZE_MB * 1024 * 1024
    if size_bytes > max_bytes:
        raise ValueError(
            f"File size {size_bytes / (1024 * 1024):.1f} MB exceeds "
            f"the {cfg.MAX_FILE_SIZE_MB} MB limit."
        )
    file.file.seek(0)

    content_type = file.content_type or ""
    raw_bytes = file.file.read()

    logger.info(
        "Ingestion: content_type=%s, size=%d bytes",
        content_type, len(raw_bytes),
    )

    # Route by MIME type.
    if content_type == "application/pdf":
        raw_text = await _process_pdf(raw_bytes, cfg, synthesize=synthesize)
    elif content_type.startswith("image/"):
        raw_text = await _process_image(raw_bytes, cfg, synthesize=synthesize)
    else:
        raise ValueError(f"Unsupported content type: {content_type or '(unknown)'}")

    # Normalize and return.
    cleaned = normalize_text(raw_text)
    if not cleaned.strip():
        raise OCRFailedError("All OCR tiers produced empty text.")
    logger.info("Document processed (%d chars after normalization)", len(cleaned))
    return cleaned


# ---------------------------------------------------------------------------
# PDF processing — text extraction → image-based dual-OCR fallback
# ---------------------------------------------------------------------------


async def _process_pdf(raw_bytes: bytes, cfg: config.Settings, *, synthesize: bool = True) -> str:  # pragma: no cover
    """Attempt text extraction first; fall back to image-based dual-OCR if empty."""
    # Tier 1 + 2: pdfplumber → PyMuPDF (via existing pdf.py)
    # These are sync but fast — run inline.
    try:
        text = extract_pdf_text(raw_bytes)
        if text.strip():
            logger.info("PDF text extracted via text extraction chain (%d chars)", len(text))
            return text
    except RuntimeError:
        logger.info("PDF text extraction failed, falling back to image-based OCR")

    # Tier 3: Render each page → standardize → dual-preprocess → Tesseract ×2 → synthesize
    return await _ocr_pdf_pages(raw_bytes, cfg, synthesize=synthesize)


# ---------------------------------------------------------------------------
# Image scaling helper — prevent excessively large images from stressing Tesseract
# ---------------------------------------------------------------------------


def _scale_if_needed(image: Image.Image, max_dim: int = _MAX_IMAGE_DIMENSION) -> Image.Image:
    """Downscale *image* if either dimension exceeds *max_dim*, preserving aspect ratio."""
    w, h = image.size
    if w <= max_dim and h <= max_dim:
        return image
    scale = max_dim / max(w, h)
    new_size = (int(w * scale), int(h * scale))
    logger.info(
        "Downscaling image from %dx%d to %dx%d (exceeded %d px limit)",
        w, h, new_size[0], new_size[1], max_dim,
    )
    return image.resize(new_size, Image.Resampling.LANCZOS)


# ---------------------------------------------------------------------------
# Dual-OCR core — runs Tesseract on both preprocessed versions
# ---------------------------------------------------------------------------


def _run_dual_ocr_on_image(image: Image.Image, cfg: config.Settings) -> DualOCRResult:
    """Standardise DPI, preprocess into two versions, and run Tesseract on both.

    Steps:
    1. ``standardize_to_jpg`` — normalise DPI to 300 (critical for Tesseract
       to interpret text scale correctly).
    2. ``preprocess_for_ocr`` — create greyscale+contrast and b/w thresholded versions.
    3. ``pytesseract.image_to_string`` — run Tesseract ``lang=deu`` on each.

    This is a synchronous CPU-bound operation. Call it from an async context
    via ``asyncio.to_thread`` for non-blocking behaviour.
    """
    w, h = image.size
    logger.debug("OCR preprocessing: source image %dx%d, mode=%s", w, h, image.mode)

    # Critical: normalise DPI to 300 so Tesseract interprets text at the correct scale.
    standardized = standardize_to_jpg(image)

    # Optional downscale for extremely large scans.
    standardized = _scale_if_needed(standardized)

    pair: PreprocessedPair = preprocess_for_ocr(
        standardized,
        contrast_factor=cfg.OCR_CONTRAST_FACTOR,
        bw_threshold=cfg.OCR_BW_THRESHOLD,
    )

    text_a = str(
        pytesseract.image_to_string(
            pair.greyscale_contrast,
            lang=_TESSERACT_LANG,
            config=_TESSERACT_CONFIG,
        )
    )
    text_b = str(
        pytesseract.image_to_string(
            pair.black_white,
            lang=_TESSERACT_LANG,
            config=_TESSERACT_CONFIG,
        )
    )

    logger.info(
        "Dual-OCR complete: greyscale+contrast=%d chars, black_white=%d chars",
        len(text_a),
        len(text_b),
    )

    return DualOCRResult(greyscale_contrast=text_a, black_white=text_b)


async def _ocr_pdf_pages(raw_bytes: bytes, cfg: config.Settings, *, synthesize: bool = True) -> str:  # pragma: no cover
    """Render PDF pages to images, run dual-OCR per page, combine and synthesize."""
    doc = fitz.open(stream=raw_bytes, filetype="pdf")
    try:
        pages_text_a: list[str] = []
        pages_text_b: list[str] = []

        logger.info("PDF has %d pages — running dual-OCR on each", len(doc))

        # Run page OCR in a thread pool — pytesseract is CPU-bound and
        # blocks the GIL, so offloading prevents event-loop stalls.
        for i, page in enumerate(doc):
            pixmap = page.get_pixmap(dpi=cfg.OCR_DPI)
            img = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
            result = await asyncio.to_thread(_run_dual_ocr_on_image, img, cfg)
            pages_text_a.append(result.greyscale_contrast)
            pages_text_b.append(result.black_white)
            logger.debug(
                "PDF page %d/%d OCR done: A=%d chars, B=%d chars",
                i + 1, len(doc),
                len(result.greyscale_contrast),
                len(result.black_white),
            )

        combined_a = "\n---\n".join(pages_text_a)
        combined_b = "\n---\n".join(pages_text_b)
    finally:
        doc.close()

    if synthesize and (combined_a.strip() or combined_b.strip()):
        return await _synthesize_ocr_text(combined_a, combined_b)
    else:
        return f"{combined_a}\n{combined_b}"


# ---------------------------------------------------------------------------
# Image processing — standardize → dual-preprocess → Tesseract ×2 → LLM synthesis
# ---------------------------------------------------------------------------


async def _process_image(raw_bytes: bytes, cfg: config.Settings, *, synthesize: bool = True) -> str:  # pragma: no cover
    """Load image with Pillow, standardize, dual-preprocess, run Tesseract on both versions."""
    img = Image.open(io.BytesIO(raw_bytes))
    result = await asyncio.to_thread(_run_dual_ocr_on_image, img, cfg)

    if synthesize:
        return await _synthesize_ocr_text(result.greyscale_contrast, result.black_white)
    else:
        return f"{result.greyscale_contrast}\n{result.black_white}"


# ---------------------------------------------------------------------------
# LLM synthesis — compare, reconcile, spell/grammar check
# ---------------------------------------------------------------------------


async def _synthesize_ocr_text(text_a: str, text_b: str) -> str:
    """Send both OCR results to the synthesis LLM for comparison and correction.

    This is an async function that delegates to the reasoning service.
    """
    from app.services.reasoning import synthesize_and_correct_text

    logger.info(
        "Synthesizing dual-OCR results (A: %d chars, B: %d chars)",
        len(text_a),
        len(text_b),
    )

    try:
        return await synthesize_and_correct_text(text_a, text_b)
    except Exception as exc:
        logger.error(
            "OCR synthesis LLM call failed: %s. Using concatenation fallback.", exc
        )
        return f"{text_a}\n{text_b}"
