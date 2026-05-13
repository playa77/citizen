"""Corpus management endpoints — manual trigger and status for scraper/chunker.

Provides three endpoints:
    POST /api/v1/corpus/update       — Trigger a full scrape of gesetze-im-internet.de,
                                      parse the hierarchy, split into chunks, generate
                                      embeddings, and upsert to the database.

    GET  /api/v1/corpus/status/{job_id} — Query the status of a corpus update job,
                                          including substage tracking for progress UI.

    GET  /api/v1/corpus/health       — Corpus health check: chunk counts, source info,
                                      warnings.
"""

# Semantic Version: 0.2.0

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from sqlalchemy import func, select

from app.core import config as cfg
from app.core.config import settings
from app.db.models import LegalChunk, LegalSource
from app.db.session import get_session_factory
from app.services.corpus import generate_embeddings, scrape_and_chunk, upsert_chunks

logger = logging.getLogger(__name__)

router = APIRouter()

# In-memory job tracking — extremely lightweight, for WP-013 / WP-014.
# Production would use a proper job queue (Celery/Redis). This is sufficient
# for the acceptance criteria which only require a 200 response.
_job_store: dict[str, dict[str, Any]] = {}


# Map source_type abbreviations to human-readable names for the progress UI.
_SOURCE_DISPLAY_NAMES: dict[str, str] = {
    "sgb2": "SGB II (Bürgergeld)",
    "sgbx": "SGB X (Verwaltungsverfahren)",
    "sgb12": "SGB XII (Sozialhilfe)",
    "sgb1": "SGB I (Allgemeiner Teil)",
    "sgb3": "SGB III (Arbeitsförderung)",
    "sgb9": "SGB IX (Rehabilitation und Teilhabe)",
    "bgb": "BGB (Bürgerliches Gesetzbuch)",
    "vwvfg": "VwVfG (Verwaltungsverfahrensgesetz)",
    "sgg": "SGG (Sozialgerichtsgesetz)",
}


# ---------------------------------------------------------------------------
# Helper — background job
# ---------------------------------------------------------------------------


async def _run_corpus_update(job_id: str) -> None:
    """Background task that executes the full corpus update pipeline.

    Catches all exceptions and records detailed status in ``_job_store``,
    including substage transitions and the currently processed source type
    so the frontend can render granular progress.

    Enforces ``CORPUS_INGESTION_TIMEOUT_SEC`` via ``asyncio.wait_for``.
    """
    timeout = cfg._get_settings().CORPUS_INGESTION_TIMEOUT_SEC

    async def _do_run() -> None:
        logger.info("Corpus update job started: job_id=%s", job_id)
        _job_store[job_id].update(
            status="running", substage="scraping", current_source=None
        )

        source_types = settings.CORPUS_SOURCES
        per_source: dict[str, int] = {}

        # Stage 1 — scrape & chunk for each configured source type
        chunks: list[dict[str, Any]] = []
        for idx, source_type in enumerate(source_types):
            display_name = _SOURCE_DISPLAY_NAMES.get(source_type, source_type.upper())
            _job_store[job_id].update(
                current_source=source_type,
                current_source_display=display_name,
                source_index=idx + 1,
                source_total=len(source_types),
            )
            logger.info(
                "Corpus job %s: ingesting %s (%d/%d)",
                job_id,
                display_name,
                idx + 1,
                len(source_types),
            )
            try:
                source_chunks = await scrape_and_chunk(source_type=source_type)
                chunks.extend(source_chunks)
                per_source[source_type] = len(source_chunks)
                _job_store[job_id]["chunks_scraped"] = len(chunks)
                _job_store[job_id]["per_source"] = dict(per_source)
                logger.info(
                    "Corpus job %s: scraped %d chunks for source_type=%s",
                    job_id,
                    len(source_chunks),
                    source_type,
                )
            except Exception as exc:
                per_source[source_type] = 0
                _job_store[job_id]["per_source"] = dict(per_source)
                logger.warning(
                    "Corpus job %s: failed to scrape source_type=%s: %s",
                    job_id,
                    source_type,
                    exc,
                )

        _job_store[job_id].update(current_source=None, current_source_display=None)

        if not chunks:
            logger.warning("Corpus job %s: no chunks scraped from any source", job_id)
            _job_store[job_id].update(
                status="completed",
                substage="done",
                chunks_processed=0,
                per_source=per_source,
            )
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
            await session.commit()

        _job_store[job_id].update(
            status="completed",
            substage="done",
            chunks_processed=len(chunks),
            per_source=_job_store[job_id].get("per_source", {}),
        )
        logger.info("Corpus update job completed: job_id=%s, chunks=%d", job_id, len(chunks))

    try:
        await asyncio.wait_for(_do_run(), timeout=timeout)
    except TimeoutError:
        logger.error(
            "Corpus update job timed out after %ds: job_id=%s",
            timeout,
            job_id,
        )
        _job_store[job_id].update(
            status="failed",
            substage=None,
            error=(
                f"Zeitüberschreitung nach {timeout}s — "
                "der Corpus-Abruf dauerte zu lange. Bitte versuchen Sie es "
                "erneut oder reduzieren Sie die konfigurierten Corpus-Quellen."
            ),
            chunks_processed=0,
        )
    except Exception as exc:
        logger.exception("Corpus update job failed: job_id=%s", job_id)
        _job_store[job_id].update(
            status="failed", substage=None, error=str(exc), chunks_processed=0,
        )


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


# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------


@router.get("/corpus/health")
async def corpus_health() -> dict[str, Any]:
    """Return corpus health status: chunk/source counts, source breakdown, warnings.

    Queries the database to count chunks and sources, and returns a summary.
    Useful for pre-flight checks before running the pipeline.
    """
    session_factory = get_session_factory()
    warnings: list[str] = []

    async with session_factory() as session:
        total_chunks = await session.scalar(select(func.count(LegalChunk.id))) or 0
        total_sources = await session.scalar(select(func.count(LegalSource.id))) or 0

        # Per-source chunk counts
        rows = await session.execute(
            select(
                LegalSource.source_type,
                func.count(LegalChunk.id).label("chunk_count"),
                func.max(LegalSource.updated_at).label("last_updated"),
            )
            .outerjoin(LegalChunk, LegalChunk.source_id == LegalSource.id)
            .group_by(LegalSource.source_type)
        )
        sources = [
            {
                "type": row.source_type,
                "chunk_count": row.chunk_count,
                "last_updated": str(row.last_updated) if row.last_updated else None,
            }
            for row in rows.mappings().all()
        ]

    is_healthy = total_chunks > 0

    if total_chunks == 0:
        warnings.append(
            "Der Corpus enthält keine Rechtsquellen. "
            "Bitte führen Sie eine Corpus-Aktualisierung durch: POST /api/v1/corpus/update"
        )
    elif total_chunks < 100:
        warnings.append(
            f"Der Corpus enthält nur {total_chunks} Textblöcke – "
            "für eine zuverlässige Analyse werden mehr Rechtsquellen empfohlen."
        )

    # Check configured sources vs actual sources
    configured = set(settings.CORPUS_SOURCES)
    available = {s["type"] for s in sources}
    missing = configured - available
    if missing:
        warnings.append(
            f"Konfigurierte Quellen nicht im Corpus: {', '.join(sorted(missing))}. "
            "Bitte Corpus aktualisieren."
        )

    return {
        "total_chunks": total_chunks,
        "total_sources": total_sources,
        "sources": sources,
        "is_healthy": is_healthy,
        "warnings": warnings,
    }
