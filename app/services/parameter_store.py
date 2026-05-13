"""Async query layer for versioned legal parameters stored in the DB.

Provides lookup functions that retrieve ``LegalParameter`` rows by key and
validity date, and a convenience ``build_legal_snapshot`` for audit trails.

Architecture:
    Pure DB queries — no business logic.  The caller (``calculation.py``)
    merges results with the deterministic rules engine, which still contains
    hardcoded fallback values.
"""

# Semantic Version: 0.1.0

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import LegalParameter

logger = logging.getLogger(__name__)


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
    ``parameter_key``, ``review_status``, ``error``.  If no matching parameter
    is found, ``value`` is **None** and ``error`` contains a description.

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
            LegalParameter.review_status == "verified",
        )
        .where(
            (LegalParameter.valid_to.is_(None)) | (LegalParameter.valid_to >= as_of_date)
        )
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

    return {
        "value": param.value_numeric,
        "unit": param.unit,
        "valid_from": param.valid_from,
        "valid_to": param.valid_to,
        "parameter_key": param.parameter_key,
        "review_status": param.review_status,
        "error": None,
    }


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
            LegalParameter.review_status == "verified",
        )
        .where(
            (LegalParameter.valid_to.is_(None)) | (LegalParameter.valid_to >= as_of_date)
        )
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

    return {
        "value": param.value_json,
        "unit": param.unit,
        "valid_from": param.valid_from,
        "valid_to": param.valid_to,
        "parameter_key": param.parameter_key,
        "review_status": param.review_status,
        "error": None,
    }


# ---------------------------------------------------------------------------
# Legal snapshot (audit trail)
# ---------------------------------------------------------------------------


async def build_legal_snapshot(
    session: AsyncSession, *, year: int
) -> dict[str, Any]:
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
            version_str = f"{key}@{result['valid_from']}"
            snapshot["parameter_versions"].append(version_str)

    return snapshot
