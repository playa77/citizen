"""OCR assessment endpoint — pre-pipeline quality check.

Provides a single endpoint:
    GET /api/v1/ocr/assess — Assess OCR quality of extracted text.
    Returns an ``OcrQualityReport`` as JSON.

Use this endpoint to pre-check text quality before submitting it to the
full analysis pipeline.
"""

# Semantic Version: 0.1.0 | 2026-07-13

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import unquote

from fastapi import APIRouter, HTTPException, Query, status

from app.services.ocr_quality import assess_ocr_quality

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/ocr/assess", status_code=status.HTTP_200_OK)
async def ocr_assess(
    text: str = Query(..., description="Extracted text to assess"),
) -> dict[str, Any]:
    """Assess OCR quality of the provided text.

    Parameters
    ----------
    text : str
        The extracted UTF-8 text to assess (URL-encoded in query parameter).

    Returns
    -------
    dict
        An ``OcrQualityReport`` as JSON with keys: ``score``, ``level``,
        ``issues``, ``warnings``, ``ocr_artifacts_detected``,
        ``readable_words_pct``, ``language_detected``, ``recommendations``.

    Raises
    ------
    HTTPException(400)
        If ``text`` is empty or too long (>100_000 chars).
    """
    # Decode URL-encoded text
    decoded = unquote(text)

    if not decoded.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Text parameter must be non-empty.",
        )

    if len(decoded) > 100_000:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Text parameter exceeds maximum length of 100,000 characters.",
        )

    logger.info("OCR assess request: %d characters", len(decoded))

    report = assess_ocr_quality(decoded)

    return {
        "score": report.score,
        "level": report.level,
        "issues": report.issues,
        "warnings": report.warnings,
        "ocr_artifacts_detected": report.ocr_artifacts_detected,
        "readable_words_pct": report.readable_words_pct,
        "language_detected": report.language_detected,
        "recommendations": report.recommendations,
    }
