"""Ingestion endpoint — OCR and text normalization.

Provides a single endpoint:
    POST /api/v1/ingest — Upload a document (PDF/JPG/PNG) and receive
    normalized UTF-8 text as JSON.

The endpoint enforces the ``MAX_FILE_SIZE_MB`` limit and validates MIME type.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app.services.ocr import OCRFailedError, process_document

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/ingest", status_code=status.HTTP_200_OK)
async def ingest(file: UploadFile = File(...)) -> dict[str, str]:  # noqa: B008
    """Extract and normalize text from an uploaded document.

    Parameters
    ----------
    file : UploadFile
        The uploaded file (PDF, JPG, PNG). Must obey the configured
        ``MAX_FILE_SIZE_MB`` limit and have a recognized MIME type.

    Returns
    -------
    dict[str, str]
        ``{"text": "<normalized content>"}``

    Raises
    ------
    HTTPException(400)
        If the file is too large, MIME type is unsupported, or OCR yields
        no text.
    HTTPException(415)
        If the file MIME type is not supported.
    """
    logger.info(
        "Ingest request received: filename=%s, content_type=%s", file.filename, file.content_type
    )

    allowed_types = {
        "application/pdf",
        "image/jpeg",
        "image/jpg",
        "image/png",
    }
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported media type: {file.content_type}. Allowed: PDF, JPG, PNG",
        )

    try:
        normalized_text = await process_document(file)
    except ValueError as exc:
        # Size limit or unsupported type
        logger.warning("Ingest validation error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except OCRFailedError as exc:
        logger.error("OCR failed for upload: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OCR processing failed — all extraction tiers yielded empty text.",
        ) from exc
    except Exception as exc:
        logger.exception("Unexpected error during ingestion")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during document processing.",
        ) from exc

    logger.info("Ingest complete — extracted %d characters", len(normalized_text))
    return {"text": normalized_text}
