"""Corpus management endpoints — manual trigger and status for scraper/chunker.

Provides two endpoints:
    POST /api/v1/corpus/update       — Trigger a full scrape of gesetze-im-internet.de,
                                      parse the hierarchy, split into chunks, generate
                                      embeddings, and upsert to the database.

    GET  /api/v1/corpus/status/{job_id} — Query the status of a corpus update job,
                                          including substage tracking for progress UI.

The update endpoint runs the work in a background task and immediately returns
a job identifier. Status can be polled via the GET endpoint.
"""

# Semantic Version: 0.1.0

from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, status

from app.db.session import get_session_factory
from app.services.corpus import generate_embeddings, scrape_and_chunk, upsert_chunks

logger = logging.getLogger(__name__)

router = APIRouter()

# In-memory job tracking — extremely lightweight, for WP-013 only.
# Production would use a proper job queue (Celery/Redis). This is sufficient
# for the acceptance criteria which only require a 200 response.
_job_store: dict[str, dict[str, Any]] = {}


# ---------------------------------------------------------------------------
# Helper — background job
# ---------------------------------------------------------------------------


async def _run_corpus_update(job_id: str) -> None:
    """Background task that executes the full corpus update pipeline.

    Catches all exceptions and records detailed status in ``_job_store``,
    including substage transitions so the frontend can render progress.
    """
    try:
        logger.info("Corpus update job started: job_id=%s", job_id)
        _job_store[job_id].update(status="running", substage="scraping")

        # Stage 1 — scrape & chunk for each valid source type
        chunks: list[dict[str, Any]] = []
        for source_type in ("sgb2", "sgbx"):
            try:
                source_chunks = await scrape_and_chunk(source_type=source_type)
                chunks.extend(source_chunks)
                _job_store[job_id]["chunks_scraped"] = len(chunks)
                logger.info(
                    "Corpus job %s: scraped %d chunks for source_type=%s",
                    job_id,
                    len(source_chunks),
                    source_type,
                )
            except Exception as exc:
                logger.warning(
                    "Corpus job %s: failed to scrape source_type=%s: %s",
                    job_id,
                    source_type,
                    exc,
                )

        if not chunks:
            logger.warning("Corpus job %s: no chunks scraped from any source", job_id)
            _job_store[job_id].update(status="completed", substage="done", chunks_processed=0)
            return

        logger.info("Corpus job %s: scraped %d chunks total", job_id, len(chunks))

        # Stage 2 — generate embeddings
        _job_store[job_id].update(substage="embedding")
        chunks = await generate_embeddings(chunks)
        logger.info("Corpus job %s: generated embeddings for %d chunks", job_id, len(chunks))

        # Stage 3 — upsert to DB
        _job_store[job_id].update(substage="upserting")
        session_factory = get_session_factory()
        async with session_factory() as session:
            await upsert_chunks(session, chunks)
            # upsert_chunks already commits internally, but we commit here too for safety
            await session.commit()

        _job_store[job_id].update(status="completed", substage="done", chunks_processed=len(chunks))
        logger.info("Corpus update job completed: job_id=%s, chunks=%d", job_id, len(chunks))
    except Exception as exc:
        logger.exception("Corpus update job failed: job_id=%s", job_id)
        _job_store[job_id].update(status="failed", substage=None, error=str(exc), chunks_processed=0)


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post("/corpus/update", status_code=status.HTTP_202_ACCEPTED)
async def corpus_update(background_tasks: BackgroundTasks) -> dict[str, str | int]:
    """Trigger a manual corpus refresh in the background.

    Returns immediately with a ``job_id`` that can be used to query
    status via ``GET /api/v1/corpus/status/{job_id}``.

    The background job will:
      1. Scrape legal sources (gesetze-im-internet.de)
      2. Chunk hierarchically by §/Abs/Satz
      3. Generate embeddings via OpenRouter
      4. Upsert all records to the database

    Returns
    -------
    dict[str, str | int]
        ``{"job_id": "<uuid>", "status": "queued"}``

    Raises
    ------
    HTTPException(500)
        If the background task could not be scheduled (extremely rare).
    """
    job_id = str(uuid.uuid4())
    _job_store[job_id] = {"status": "queued", "substage": None, "chunks_scraped": 0}

    try:
        background_tasks.add_task(_run_corpus_update, job_id)
    except Exception as exc:
        logger.exception("Failed to schedule corpus update job")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to schedule background job.",
        ) from exc

    logger.info("Corpus update scheduled: job_id=%s", job_id)
    return {"job_id": job_id, "status": "queued"}


@router.get("/corpus/status/{job_id}")
async def corpus_status(job_id: str) -> dict[str, Any]:
    """Query the status of a corpus update job.

    Returns the current state from the in-memory job store, including
    substage tracking so the frontend can render granular progress.

    Returns
    -------
    dict[str, Any]
        ``{"job_id": "...", "status": "queued|running|completed|failed", "substage": "...", "chunks_scraped": 0, "chunks_processed": 0}``

    Raises
    ------
    HTTPException(404)
        If no job with the given ``job_id`` exists.
    """
    job = _job_store.get(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Auftrag {job_id} nicht gefunden.",
        )
    return {"job_id": job_id, **job}
