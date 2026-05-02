"""PDF text extraction with local fallback chain."""

import io
import logging

import fitz  # PyMuPDF
import pdfplumber

logger = logging.getLogger(__name__)


def _extract_with_pdfplumber(file_bytes: bytes) -> str:
    """Extract text using pdfplumber. Returns empty string if no text found."""
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        pages: list[str] = []
        for page in pdf.pages:
            text = page.extract_text()
            pages.append(text or "")
        result = "\n".join(pages)
        if not result.strip():
            return ""
        return result


def _extract_with_pymupdf(file_bytes: bytes) -> str:
    """Extract text using PyMuPDF (fitz). Raises on failure."""
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    try:
        pages: list[str] = []
        for page in doc:
            pages.append(page.get_text())
        return "\n".join(pages)
    finally:
        doc.close()


def extract_pdf_text(file_bytes: bytes) -> str:
    """Extract text from a PDF using a deterministic fallback chain.

    Chain order:
    1. pdfplumber (preferred for text-heavy digital PDFs)
    2. PyMuPDF / fitz (fallback when pdfplumber returns nothing)

    Returns
    -------
    str
        Clean, UTF-8 extracted text.

    Raises
    ------
    ValueError
        If the input is empty (zero bytes).
    RuntimeError
        If both extraction back-ends fail.
    """
    if not file_bytes:
        raise ValueError("file_bytes must not be empty")

    # --- Tier 1: pdfplumber ---
    try:
        text = _extract_with_pdfplumber(file_bytes)
        if text.strip():
            logger.info("PDF text extracted via pdfplumber (%d chars)", len(text))
            return text
        logger.info("pdfplumber returned empty text, falling back to PyMuPDF")
    except Exception:  # pragma: no cover - fall through to next tier
        logger.exception("pdfplumber extraction failed, falling back to PyMuPDF")

    # --- Tier 2: PyMuPDF ---
    try:
        text = _extract_with_pymupdf(file_bytes)
        if text.strip():
            logger.info("PDF text extracted via PyMuPDF (%d chars)", len(text))
            return text
    except Exception as exc:
        raise RuntimeError("All PDF text extraction back-ends failed") from exc

    raise RuntimeError("All PDF text extraction back-ends returned empty text")
