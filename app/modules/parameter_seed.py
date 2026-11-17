"""Parameter rows → ``legal_parameter`` upsert (WP-93 loader, shared since WP-111).

One upsert for both writers: the file seeder
(``scripts/seed_module_parameters.py``) and the signed update channel
(``app/updates``). Identity is ``(parameter_key, domain, valid_from)``;
differing fields of an existing row are updated, identical rows skipped.

``protected`` identities are left untouched when their values differ: the
file seeder passes the identities a signed feed wrote, so re-seeding from
module files that predate a published correction never reverts it (the next
module release carries the corrected value in its files, and then the two
agree again). The caller owns the transaction.
"""

# Semantic Version: 1.0.0 | 2026-11-17 — WP-111: extracted from the seed script.

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import LegalParameter
from app.modules.parameters import ParameterRow

logger = logging.getLogger(__name__)

UPDATABLE = (
    "value_numeric",
    "value_json",
    "value_text",
    "unit",
    "valid_to",
    "review_status",
    "regime",
    "notes",
)

Identity = tuple[str, str, date]  # (key, domain, valid_from)


@dataclass
class UpsertResult:
    created: list[Identity] = field(default_factory=list)
    updated: list[Identity] = field(default_factory=list)
    unchanged: list[Identity] = field(default_factory=list)
    protected: list[Identity] = field(default_factory=list)

    def action(self, identity: Identity) -> str:
        for name in ("created", "updated", "unchanged", "protected"):
            if identity in getattr(self, name):
                return name
        raise KeyError(identity)


async def upsert_parameter_rows(
    session: AsyncSession,
    rows: Iterable[ParameterRow],
    *,
    protected: frozenset[Identity] = frozenset(),
) -> UpsertResult:
    """Upsert *rows* in *session* (flushes, does not commit)."""
    result = UpsertResult()
    for row in rows:
        identity: Identity = (row.key, row.domain, row.valid_from)
        existing = (
            await session.execute(
                select(LegalParameter).where(
                    LegalParameter.parameter_key == row.key,
                    LegalParameter.domain == row.domain,
                    LegalParameter.valid_from == row.valid_from,
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            session.add(
                LegalParameter(
                    parameter_key=row.key,
                    domain=row.domain,
                    valid_from=row.valid_from,
                    **{attr: getattr(row, attr) for attr in UPDATABLE},
                )
            )
            result.created.append(identity)
            logger.info("created  %s@%s (regime=%s)", row.key, row.valid_from, row.regime)
            continue
        changes = [a for a in UPDATABLE if getattr(existing, a) != getattr(row, a)]
        if not changes:
            result.unchanged.append(identity)
            continue
        if identity in protected:
            result.protected.append(identity)
            logger.warning(
                "kept     %s@%s — value set by a signed update feed differs from the "
                "module file (%s); the feed value stays",
                row.key,
                row.valid_from,
                ", ".join(changes),
            )
            continue
        for attr in changes:
            setattr(existing, attr, getattr(row, attr))
        result.updated.append(identity)
        logger.info("updated  %s@%s (regime=%s)", row.key, row.valid_from, row.regime)
    await session.flush()
    return result


__all__ = ["UPDATABLE", "Identity", "UpsertResult", "upsert_parameter_rows"]
