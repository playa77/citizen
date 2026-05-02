"""OCR service — local-only document processing with three-tier fallback.

Pipeline
--------
1. Validate file size against ``settings.MAX_FILE_SIZE_MB``.
2. Route by MIME type:
   - ``application/pdf`` → text extraction (``pdfplumber`` → ``PyMuPDF``),
     then image-based OCR if text extraction yields nothing.
   - ``image/*`` → ``Pillow`` → ``standardize_to_jpg`` → ``pytesseract``.
3. Normalize cleaned text via ``app.utils.text.normalize_text``.
4. Return UTF-8 string.
"""

from __future__ import annotations

import io
import logging

import fitz  # PyMuPDF
import pytesseract
from fastapi import UploadFile
from PIL import Image

from app.core import config
from app.utils.image import standardize_to_jpg
from app.utils.pdf import extract_pdf_text
from app.utils.text import normalize_text

logger = logging.getLogger(__name__)


class OCRFailedError(Exception):
    """Raised when all OCR back-ends produce empty text."""


async def process_document(file: UploadFile) -> str:
    """Extract and normalize text from a scanned document or image.

    Parameters
    ----------
    file : UploadFile
        Uploaded file (PDF, JPG, PNG, etc.). Must be smaller than
        ``settings.MAX_FILE_SIZE_MB``.

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

    # Route by MIME type.
    if content_type == "application/pdf":
        text = _process_pdf(raw_bytes, cfg)
    elif content_type.startswith("image/"):
        text = _process_image(raw_bytes, cfg)
    else:
        raise ValueError(f"Unsupported content type: {content_type or '(unknown)'}")

    # Normalize and return.
    cleaned = normalize_text(text)
    if not cleaned.strip():
        raise OCRFailedError("All OCR tiers produced empty text.")
    logger.info("Document processed (%d chars after normalization)", len(cleaned))
    return cleaned


# ---------------------------------------------------------------------------
# PDF processing — text extraction → image-based OCR fallback
# ---------------------------------------------------------------------------


def _process_pdf(raw_bytes: bytes, cfg: config.Settings) -> str:  # pragma: no cover
    """Attempt text extraction first; fall back to image-based OCR if empty."""
    # Tier 1 + 2: pdfplumber → PyMuPDF (via existing pdf.py)
    try:
        text = extract_pdf_text(raw_bytes)
        if text.strip():
            logger.info("PDF text extracted via text extraction chain (%d chars)", len(text))
            return text
    except RuntimeError:
        logger.info("PDF text extraction failed, falling back to image-based OCR")

    # Tier 3: Render each page as an image → standardize → pytesseract
    return _ocr_pdf_pages(raw_bytes, cfg)


def _ocr_pdf_pages(raw_bytes: bytes, cfg: config.Settings) -> str:  # pragma: no cover
    """Render PDF pages to images, standardize, and run pytesseract."""
    doc = fitz.open(stream=raw_bytes, filetype="pdf")
    try:
        pages_text: list[str] = []
        for page in doc:
            pixmap = page.get_pixmap(dpi=cfg.OCR_DPI)
            img = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
            standardized = standardize_to_jpg(img)
            page_text = pytesseract.image_to_string(standardized)
            pages_text.append(page_text)
        return "\n".join(pages_text)
    finally:
        doc.close()


# ---------------------------------------------------------------------------
# Image processing — Pillow → standardize → pytesseract
# ---------------------------------------------------------------------------


def _process_image(raw_bytes: bytes, cfg: config.Settings) -> str:  # pragma: no cover
    """Load image with Pillow, standardize, and run pytesseract."""
    img = Image.open(io.BytesIO(raw_bytes))
    standardized = standardize_to_jpg(img)
    return str(pytesseract.image_to_string(standardized))
