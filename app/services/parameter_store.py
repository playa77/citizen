"""Async and sync query layers for versioned legal parameters.

Async functions
---------------
- get_parameter_numeric() — async DB lookup for scalar numeric parameters
- get_parameter_json() — async DB lookup for JSON-valued parameters
- build_legal_snapshot() — audit-trail snapshot of which param versions were used
- reload_parameter_cache() — rebuild the in-memory sync cache from the DB

Sync functions
--------------
- param() — synchronous lookup from an in-memory cache, used by deterministic
  LLM-free engines (e.g. the Fristen engine, WP-21).

Architecture:
    Async functions query the DB directly.  The sync ``param()`` reads from a
    module-level dict populated at startup by ``reload_parameter_cache()``
    (called from ``main.py`` lifespan).  This avoids async DB access in contexts
    that must be deterministic and synchronous.
"""

# Semantic Version: 0.2.0

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import LegalParameter

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# In-memory parameter cache (populated at startup)
# ---------------------------------------------------------------------------
# Keyed by (parameter_key, domain) -> list[dict] sorted by valid_from DESC.
# The list holds all rows (any review_status) so the sync `param()` can decide
# which to include.
_parameter_cache: dict[tuple[str, str], list[dict[str, Any]]] = {}


async def reload_parameter_cache(session: AsyncSession) -> None:
    """Rebuild the in-memory parameter cache from the database.

    Called at application startup from ``main.py`` lifeycle.  After this call
    the synchronous ``param()`` function can be used without a DB session.
    """
    stmt = select(LegalParameter).order_by(
        LegalParameter.parameter_key,
        LegalParameter.domain,
        LegalParameter.valid_from.desc(),
    )
    result = await session.execute(stmt)
    rows = result.scalars().all()

    cache: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        key = (row.parameter_key, row.domain)
        entry = {
            "value_numeric": row.value_numeric,
            "value_json": row.value_json,
            "value_text": row.value_text,
            "unit": row.unit,
            "valid_from": row.valid_from,
            "valid_to": row.valid_to,
            "review_status": row.review_status,
            "regime": row.regime,
            "notes": row.notes,
        }
        cache.setdefault(key, []).append(entry)

    global _parameter_cache
    _parameter_cache = cache
    logger.info(
        "Parameter cache reloaded — %d keys, %d total rows",
        len(cache),
        len(rows),
    )


# ---------------------------------------------------------------------------
# Sync convenience function (no DB session needed)
# ---------------------------------------------------------------------------


def param(
    key: str,
    on_date: date,
    *,
    domain: str = "sgb2",
    regime: str | None = None,
) -> dict[str, Any]:
    """Synchronous parameter lookup from the in-memory cache.

    For use by deterministic, LLM-free engines (Fristen engine, WP-21) that
    cannot perform async DB access.

    Returns the same dict shape as :func:`get_parameter_numeric`, but pure
    synchronous.  Supports both ``"verified"`` and ``"proposed"`` rows —
    the latter include a ``"status": "verification_required"`` flag.

    When *regime* is provided, only parameters whose ``regime`` field matches
    (case-sensitive, exact match) are considered.  When *regime* is ``None``,
    the existing date-based fallback applies (any regime).

    Parameters
    ----------
    key :
        Parameter key (e.g. ``"sgb2.regelbedarf.rbs1"``).
    on_date :
        Date for validity check.
    domain :
        Legal domain (default ``"sgb2"``).
    regime :
        Optional regime tag to filter by (e.g. ``"a.F._2025"`` or
        ``"n.F._2026"``).  When provided, only parameters whose regime
        matches this value are returned.
    """
    entries = _parameter_cache.get((key, domain), [])
    if not entries:
        return {
            "value": None,
            "unit": None,
            "valid_from": None,
            "valid_to": None,
            "parameter_key": key,
            "review_status": None,
            "error": f"Kein Parameter '{key}' im Cache gefunden für {on_date}.",
        }

    for entry in entries:
        # When regime is specified, skip entries that don't match.
        if regime is not None and entry.get("regime") != regime:
            continue

        valid_from: date = entry["valid_from"]
        valid_to: date | None = entry["valid_to"]
        if valid_from > on_date:
            continue
        if valid_to is not None and valid_to < on_date:
            continue

        # Found a matching row
        result: dict[str, Any] = {
            "value": entry["value_numeric"]
            if entry["value_numeric"] is not None
            else entry["value_json"],
            "unit": entry["unit"],
            "valid_from": valid_from,
            "valid_to": valid_to,
            "parameter_key": key,
            "review_status": entry["review_status"],
            "regime": entry["regime"],
            "notes": entry["notes"],
            "error": None,
        }

        if entry["review_status"] != "verified":
            result["status"] = "verification_required"

        return result

    regime_note = f" (regime={regime})" if regime else ""
    return {
        "value": None,
        "unit": None,
        "valid_from": None,
        "valid_to": None,
        "parameter_key": key,
        "review_status": None,
        "error": f"Kein gültiger Parameter '{key}' gefunden für {on_date}{regime_note}.",
    }


# ---------------------------------------------------------------------------
# Scalar numeric parameter lookup
# ---------------------------------------------------------------------------


async def get_parameter_numeric(
    session: AsyncSession,
    parameter_key: str,
    as_of_date: date,
    *,
    domain: str = "sgb2",
) -> dict[str, Any]:
    """Get a scalar numeric legal parameter valid on a given date.

    Returns a dict with keys: ``value``, ``unit``, ``valid_from``, ``valid_to``,
    ``parameter_key``, ``review_status``, ``regime``, ``notes``, ``error``.
    If no matching parameter is found, ``value`` is **None** and ``error``
    contains a description.

    Supports both ``"verified"`` and ``"proposed"`` rows.  Rows with a
    review_status other than ``"verified"`` include ``"status": "verification_required"``
    so callers know not to trust the value blindly.

    Parameters
    ----------
    session :
        An open async SQLAlchemy session.
    parameter_key :
        The unique key identifying the parameter (e.g. ``"sgb2.regelbedarf.rbs1"``).
    as_of_date :
        The date for which the parameter should be valid.
    domain :
        Legal domain filter (default ``"sgb2"``).
    """
    stmt = (
        select(LegalParameter)
        .where(
            LegalParameter.parameter_key == parameter_key,
            LegalParameter.domain == domain,
            LegalParameter.valid_from <= as_of_date,
            LegalParameter.review_status.in_(["verified", "proposed"]),
        )
        .where((LegalParameter.valid_to.is_(None)) | (LegalParameter.valid_to >= as_of_date))
        .order_by(LegalParameter.valid_from.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    param = result.scalar_one_or_none()

    if param is None:
        return {
            "value": None,
            "unit": None,
            "valid_from": None,
            "valid_to": None,
            "parameter_key": parameter_key,
            "review_status": None,
            "error": f"Kein verifizierter Parameter '{parameter_key}' gefunden für {as_of_date}.",
        }

    result_dict = {
        "value": param.value_numeric,
        "unit": param.unit,
        "valid_from": param.valid_from,
        "valid_to": param.valid_to,
        "parameter_key": param.parameter_key,
        "review_status": param.review_status,
        "regime": param.regime,
        "notes": param.notes,
        "error": None,
    }

    if param.review_status != "verified":
        result_dict["status"] = "verification_required"

    return result_dict


# ---------------------------------------------------------------------------
# JSON-valued parameter lookup
# ---------------------------------------------------------------------------


async def get_parameter_json(
    session: AsyncSession,
    parameter_key: str,
    as_of_date: date,
    *,
    domain: str = "sgb2",
) -> dict[str, Any]:
    """Get a JSON-valued legal parameter valid on a given date.

    Behaves like :func:`get_parameter_numeric` but returns
    ``value_json`` instead of ``value_numeric``.
    """
    stmt = (
        select(LegalParameter)
        .where(
            LegalParameter.parameter_key == parameter_key,
            LegalParameter.domain == domain,
            LegalParameter.valid_from <= as_of_date,
            LegalParameter.review_status.in_(["verified", "proposed"]),
        )
        .where((LegalParameter.valid_to.is_(None)) | (LegalParameter.valid_to >= as_of_date))
        .order_by(LegalParameter.valid_from.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    param = result.scalar_one_or_none()

    if param is None:
        return {
            "value": None,
            "unit": None,
            "valid_from": None,
            "valid_to": None,
            "parameter_key": parameter_key,
            "review_status": None,
            "error": f"Kein verifizierter Parameter '{parameter_key}' gefunden für {as_of_date}.",
        }

    result_dict = {
        "value": param.value_json,
        "unit": param.unit,
        "valid_from": param.valid_from,
        "valid_to": param.valid_to,
        "parameter_key": param.parameter_key,
        "review_status": param.review_status,
        "regime": param.regime,
        "notes": param.notes,
        "error": None,
    }

    if param.review_status != "verified":
        result_dict["status"] = "verification_required"

    return result_dict


# ---------------------------------------------------------------------------
# Legal snapshot (audit trail)
# ---------------------------------------------------------------------------


async def build_legal_snapshot(session: AsyncSession, *, year: int) -> dict[str, Any]:
    """Build a ``legal_snapshot`` dict recording which parameter versions were used.

    Returns a dict suitable for storing in ``case_run.legal_snapshot``.

    Parameters
    ----------
    session :
        An open async SQLAlchemy session.
    year :
        Calendar year whose mid-year parameter versions to record.
    """
    as_of = date(year, 7, 1)  # mid-year lookup
    snapshot: dict[str, Any] = {"year": year, "parameter_versions": []}

    for key in ["sgb2.regelbedarf.rbs1", "sgb2.regelbedarf.rbs2"]:
        result = await get_parameter_numeric(session, key, as_of)
        if result["value"] is not None:
            regime = result.get("regime") or ""
            version_str = f"{key}@{result['valid_from']}" + (f"({regime})" if regime else "")
            snapshot["parameter_versions"].append(version_str)

    return snapshot
