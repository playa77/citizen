"""The ``module_update`` ledger (WP-111): applied state per module.

Read at startup (``load_applied_updates`` → provenance ``parameter_set``),
by the apply path (last serial, anti-rollback) and by the file seeder
(``feed_owned_parameters``: identities a feed wrote stay as the feed set
them).
"""

# Semantic Version: 1.0.0 | 2026-11-17 — WP-111: initial version.

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ModuleUpdate
from app.modules.parameter_seed import Identity


@dataclass(frozen=True)
class AppliedUpdates:
    """Applied-feed state of one module (for provenance)."""

    module_id: str
    serial: int  # highest applied serial
    latest_valid_from: date | None  # newest valid_from any applied feed wrote


async def last_serial(session: AsyncSession, module_id: str) -> int:
    value = await session.scalar(
        select(func.max(ModuleUpdate.serial)).where(ModuleUpdate.module_id == module_id)
    )
    return int(value or 0)


async def load_applied_updates(session: AsyncSession) -> dict[str, AppliedUpdates]:
    """Applied-feed state of every module that has one."""
    state: dict[str, AppliedUpdates] = {}
    rows = (await session.execute(select(ModuleUpdate))).scalars().all()
    for row in rows:
        dates = [date.fromisoformat(p["valid_from"]) for p in row.parameters]
        latest = max(dates, default=None)
        current = state.get(row.module_id)
        if current is not None:
            serial = max(current.serial, row.serial)
            candidates = [d for d in (current.latest_valid_from, latest) if d is not None]
            latest = max(candidates, default=None)
        else:
            serial = row.serial
        state[row.module_id] = AppliedUpdates(row.module_id, serial, latest)
    return state


async def feed_owned_parameters(session: AsyncSession) -> frozenset[Identity]:
    """``(key, domain, valid_from)`` of every parameter a feed created or updated."""
    owned: set[Identity] = set()
    for row in (await session.execute(select(ModuleUpdate))).scalars().all():
        for param in row.parameters:
            if param.get("action") in ("created", "updated", "unchanged"):
                owned.add((param["key"], param["domain"], date.fromisoformat(param["valid_from"])))
    return frozenset(owned)


__all__ = ["AppliedUpdates", "feed_owned_parameters", "last_serial", "load_applied_updates"]
