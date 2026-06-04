"""Per-area corpus readiness check.

A case covering ``["erbrecht", "familienrecht"]`` can only run if at
least one ``legal_chunk`` exists for each of those areas. This module
queries the DB and returns a per-area status so the API can answer:

  "If I start the pipeline with these areas, will I get evidence?"

Used by ``analyze.py`` to gate the run with HTTP 409 and a list of
missing sources the user can fix.
"""

# Semantic Version: 0.3.0

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import LegalChunk, LegalSource

logger = logging.getLogger(__name__)


# Map a high-level legal_area to the corpus source_types that satisfy it.
# This is the source of truth for "is this area loadable?".
AREA_TO_SOURCE_TYPES: dict[str, tuple[str, ...]] = {
    "sozialrecht": ("sgb1", "sgb2", "sgb3", "sgb9", "sgb12", "sgbx", "weisung", "bsg", "vwvfg", "sgg"),
    "erbrecht": ("bgb", "erbstg", "hoefev"),
    "schenkungsrecht": ("bgb", "erbstg"),
    "familienrecht": ("bgb",),
    "mietrecht": ("bgb",),
    "arbeitsrecht": ("bgb",),
    "vertragsrecht": ("bgb",),
    "verwaltungsrecht": ("vwvfg", "sgbx"),
    "strafrecht": (),
    "andere": (),
}


async def get_area_status(
    session: AsyncSession,
    legal_areas: list[str],
) -> dict[str, dict[str, Any]]:
    """Return per-area corpus status.

    Parameters
    ----------
    session :
        An open async DB session.
    legal_areas :
        A list of legal_area keys (e.g. ``["sozialrecht", "erbrecht"]``).

    Returns
    -------
    dict[str, dict[str, Any]]
        Mapping ``legal_area → {chunk_count, source_types, is_ready,
        missing_source_types}``. Areas with zero expected source types
        (e.g. ``"andere"``) are reported as ``is_ready=False``.
    """
    if not legal_areas:
        return {}

    # Aggregate chunk counts grouped by source_type in a single query.
    rows = await session.execute(
        select(
            LegalSource.source_type,
            func.count(LegalChunk.id).label("chunk_count"),
        )
        .outerjoin(LegalChunk, LegalChunk.source_id == LegalSource.id)
        .where(LegalSource.is_active.is_(True))
        .group_by(LegalSource.source_type)
    )
    by_source: dict[str, int] = {
        row.source_type: int(row.chunk_count) for row in rows.all()
    }

    result: dict[str, dict[str, Any]] = {}
    for area in legal_areas:
        source_types = AREA_TO_SOURCE_TYPES.get(area, ())
        chunk_count = sum(by_source.get(st, 0) for st in source_types)
        present_sources = tuple(st for st in source_types if by_source.get(st, 0) > 0)
        missing_sources = tuple(st for st in source_types if by_source.get(st, 0) == 0)
        is_ready = bool(source_types) and len(missing_sources) == 0

        result[area] = {
            "chunk_count": chunk_count,
            "source_types": list(source_types),
            "present_source_types": list(present_sources),
            "missing_source_types": list(missing_sources),
            "is_ready": is_ready,
        }
    return result


async def check_preflight(
    session: AsyncSession,
    legal_areas: list[str],
) -> dict[str, Any]:
    """Run a pre-flight check for a multi-area case.

    Returns
    -------
    dict
        {
            "is_ready": bool,
            "areas": { ... per-area status ... },
            "missing_source_types": [str, ...],   # all areas combined
            "ready_source_types": [str, ...],
        }
    """
    areas = await get_area_status(session, legal_areas)

    all_missing: set[str] = set()
    any_unready = False
    for area_status in areas.values():
        if not area_status["is_ready"]:
            any_unready = True
        all_missing.update(area_status["missing_source_types"])

    present: set[str] = set()
    for area_status in areas.values():
        present.update(area_status["present_source_types"])

    return {
        "is_ready": not any_unready,
        "areas": areas,
        "missing_source_types": sorted(all_missing),
        "ready_source_types": sorted(present),
    }
