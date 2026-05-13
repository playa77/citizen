"""Corpus management endpoints — manual trigger, status, source configuration.

Provides endpoints for:
    POST   /api/v1/corpus/update           — Trigger corpus scrape+embed+upsert
    GET    /api/v1/corpus/status/{job_id}  — Query job progress
    GET    /api/v1/corpus/health           — Corpus health check
    GET    /api/v1/corpus/available-sources — List all known source types with metadata
    GET    /api/v1/corpus/sources          — Get current source selection
    PUT    /api/v1/corpus/sources          — Save source selection (persisted to disk)
"""

# Semantic Version: 0.3.0

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Body, HTTPException, status
from sqlalchemy import func, select

from app.core import config as cfg
from app.core.config import settings
from app.db.models import LegalChunk, LegalSource
from app.db.session import get_session_factory
from app.services.corpus import (
    CORPUS_SOURCE_METADATA,
    generate_embeddings,
    get_effective_corpus_sources,
    load_runtime_sources,
    save_runtime_sources,
    scrape_and_chunk,
    upsert_chunks,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# In-memory job tracking — extremely lightweight, for WP-013 / WP-014.
# Production would use a proper job queue (Celery/Redis). This is sufficient
# for the acceptance criteria which only require a 200 response.
_job_store: dict[str, dict[str, Any]] = {}


# ---------------------------------------------------------------------------
# Helper — background job
# ---------------------------------------------------------------------------


async def _run_corpus_update(
    job_id: str, override_sources: list[str] | None = None
) -> None:
    """Background task that executes the full corpus update pipeline.

    *override_sources*, when provided, takes precedence over both runtime
    and env-default source lists for this single job execution.
    """
    timeout = cfg._get_settings().CORPUS_INGESTION_TIMEOUT_SEC

    async def _do_run() -> None:
        logger.info("Corpus update job started: job_id=%s", job_id)
        _job_store[job_id].update(
            status="running", substage="scraping", current_source=None
        )

        source_types = (
            override_sources
            if override_sources is not None
            else await get_effective_corpus_sources()
        )
        per_source: dict[str, int] = {}

        # Stage 1 — scrape & chunk for each configured source type
        chunks: list[dict[str, Any]] = []
        for idx, source_type in enumerate(source_types):
            meta = CORPUS_SOURCE_METADATA.get(source_type, {})
            display_name = str(meta.get("full_name") or meta.get("name", source_type.upper()))
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
async def corpus_update(
    background_tasks: BackgroundTasks,
    payload: dict[str, Any] | None = Body(None),
) -> dict[str, str | int]:
    """Trigger a manual corpus refresh in the background.

    Optionally accepts a JSON body with ``sources`` (list of source type keys)
    to override the active source selection for this job.  The override is
    **not** persisted — use ``PUT /api/v1/corpus/sources`` for persistent
    changes.

    The background job will:
      1. Scrape legal sources (gesetze-im-internet.de / arbeitsagentur.de)
      2. Chunk hierarchically by §/Abs/Satz
      3. Generate embeddings via OpenRouter
      4. Upsert all records to the database

    Returns
    -------
    dict[str, str | int]
        ``{"job_id": "<uuid>", "status": "queued"}``
    """
    job_id = str(uuid.uuid4())
    _job_store[job_id] = {"status": "queued", "substage": None, "chunks_scraped": 0}

    # Capture optional one-shot source override
    override_sources: list[str] | None = None
    if payload and isinstance(payload.get("sources"), list):
        override_sources = [str(s) for s in payload["sources"] if s in CORPUS_SOURCE_METADATA]

    try:
        background_tasks.add_task(_run_corpus_update, job_id, override_sources)
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
    configured = set(await get_effective_corpus_sources())
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


# ---------------------------------------------------------------------------
# Runtime source configuration endpoints
# ---------------------------------------------------------------------------


@router.get("/corpus/available-sources")
async def available_sources() -> list[dict[str, object]]:
    """Return all known corpus source types with their metadata.

    Includes display names, descriptions, tooltips, scraper availability,
    and smart defaults so the frontend can render a configuration dialogue.
    """
    currently_active = await get_effective_corpus_sources()
    active_set = set(currently_active)

    result: list[dict[str, object]] = []
    for key, meta in CORPUS_SOURCE_METADATA.items():
        result.append(
            {
                **meta,
                "active": key in active_set,
            }
        )
    return result


@router.get("/corpus/sources")
async def get_sources() -> dict[str, object]:
    """Return the currently active corpus source selection."""
    sources = await get_effective_corpus_sources()
    is_runtime = load_runtime_sources() is not None
    return {
        "sources": sources,
        "source": "runtime" if is_runtime else "env_default",
    }


@router.put("/corpus/sources")
async def set_sources(
    payload: dict[str, Any] = Body(...),
) -> dict[str, object]:
    """Persist a new corpus source selection to disk.

    Expects ``{"sources": ["sgb2", "sgbx", ...]}`` in the request body.
    The selection takes effect on the next corpus update (scrape+embed+upsert)
    and survives server restarts.

    Raises 422 if the payload is malformed or contains unknown source types.
    """
    raw = payload.get("sources")
    if not isinstance(raw, list) or not all(isinstance(s, str) for s in raw):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="'sources' must be a list of source type strings.",
        )

    selected = [str(s) for s in raw]

    unknown = set(selected) - set(CORPUS_SOURCE_METADATA)
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown source type(s): {', '.join(sorted(unknown))}",
        )

    if not selected:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one source must be selected.",
        )

    save_runtime_sources(selected)
    logger.info(
        "Runtime corpus sources updated: %s → %s",
        settings.CORPUS_SOURCES,
        selected,
    )
    return {
        "sources": selected,
        "status": "saved",
    }
