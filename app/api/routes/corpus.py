"""Corpus management endpoint — manual trigger for scraper/chunker.

Provides a single endpoint:
    POST /api/v1/corpus/update — Trigger a full scrape of gesetze-im-internet.de,
    parse the hierarchy, split into chunks, generate embeddings, and upsert
    to the database.

The endpoint runs the update in a background task and immediately returns
a job identifier. Status can be tracked via application logs or future
extensions (not in WP-013 scope).
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

    Catches all exceptions and records final status in ``_job_store``.
    """
    try:
        logger.info("Corpus update job started: job_id=%s", job_id)
        _job_store[job_id]["status"] = "running"

        # Stage 1 — scrape & chunk for each valid source type
        chunks: list[dict[str, Any]] = []
        for source_type in ("sgb2", "sgbx", "weisung", "bsg"):
            try:
                source_chunks = await scrape_and_chunk(source_type=source_type)
                chunks.extend(source_chunks)
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
            _job_store[job_id]["status"] = "completed"
            _job_store[job_id]["chunks_processed"] = 0
            return

        logger.info("Corpus job %s: scraped %d chunks total", job_id, len(chunks))

        # Stage 2 — generate embeddings
        chunks = await generate_embeddings(chunks)
        logger.info("Corpus job %s: generated embeddings for %d chunks", job_id, len(chunks))

        # Stage 3 — upsert to DB
        session_factory = get_session_factory()
        async with session_factory() as session:
            await upsert_chunks(session, chunks)
            # upsert_chunks already commits internally, but we commit here too for safety
            await session.commit()

        _job_store[job_id]["status"] = "completed"
        _job_store[job_id]["chunks_processed"] = len(chunks)
        logger.info("Corpus update job completed: job_id=%s, chunks=%d", job_id, len(chunks))
    except Exception as exc:
        logger.exception("Corpus update job failed: job_id=%s", job_id)
        _job_store[job_id]["status"] = "failed"
        _job_store[job_id]["error"] = str(exc)


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post("/corpus/update", status_code=status.HTTP_202_ACCEPTED)
async def corpus_update(background_tasks: BackgroundTasks) -> dict[str, str | int]:
    """Trigger a manual corpus refresh in the background.

    Returns immediately with a ``job_id`` that can be used to query
    status (via the in-memory job store — WP-013 only).

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
    _job_store[job_id] = {"status": "queued"}

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
