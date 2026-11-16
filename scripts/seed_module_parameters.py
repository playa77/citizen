#!/usr/bin/env python3
"""Seed ``legal_parameter`` from module parameter files (WP-93).

Generic loader replacing ``scripts/seed_legal_parameters.py``: every
installed module that declares ``parameters`` in its ``module.yaml`` has its
YAML rows upserted on (key, domain, valid_from); differing fields of an
existing row are updated, identical rows are skipped. The in-memory
parameter cache is reloaded afterwards.

Usage::

    python -m scripts.seed_module_parameters                 # all modules
    python -m scripts.seed_module_parameters --module sozialrecht
    python -m scripts.seed_module_parameters --dry-run       # validate only

Exit codes: 0 success, 1 invalid module data or unknown module, 2 database error.
"""

# Version: 2026-11-16.1 (WP-93; supersedes seed_legal_parameters.py 1.0.0)

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from sqlalchemy import select

from app.modules.parameters import ParameterRow, load_parameter_rows
from app.modules.registry import ModuleManifestError, default_modules_root, discover_modules

logger = logging.getLogger("seed_module_parameters")

_UPDATABLE = (
    "value_numeric",
    "value_json",
    "value_text",
    "unit",
    "valid_to",
    "review_status",
    "regime",
    "notes",
)


async def _upsert(rows: list[ParameterRow]) -> tuple[int, int, int]:
    """Upsert *rows*; return (created, updated, unchanged)."""
    from app.db.models import LegalParameter
    from app.db.session import async_session_factory
    from app.services.parameter_store import reload_parameter_cache

    created = updated = unchanged = 0
    async with async_session_factory() as session:
        for row in rows:
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
                        **{attr: getattr(row, attr) for attr in _UPDATABLE},
                    )
                )
                created += 1
                logger.info("created  %s@%s (regime=%s)", row.key, row.valid_from, row.regime)
                continue
            dirty = False
            for attr in _UPDATABLE:
                if getattr(existing, attr) != getattr(row, attr):
                    setattr(existing, attr, getattr(row, attr))
                    dirty = True
            if dirty:
                updated += 1
                logger.info("updated  %s@%s (regime=%s)", row.key, row.valid_from, row.regime)
            else:
                unchanged += 1
        await session.commit()
        # Make the new values visible to the sync param() cache immediately.
        await reload_parameter_cache(session)
    return created, updated, unchanged


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--module", action="append", help="module id (repeatable); default: all")
    parser.add_argument("--dry-run", action="store_true", help="validate files, touch no database")
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )

    try:
        modules = discover_modules(default_modules_root())
        selected = args.module or sorted(modules)
        unknown = [m for m in selected if m not in modules]
        if unknown:
            logger.error("unknown module(s): %s (installed: %s)", unknown, sorted(modules))
            return 1
        rows: list[ParameterRow] = []
        for module_id in selected:
            module_rows = load_parameter_rows(modules[module_id])
            logger.info("module %s: %d parameter row(s)", module_id, len(module_rows))
            rows.extend(module_rows)
    except ModuleManifestError as exc:
        logger.error("invalid module data: %s", exc)
        return 1

    if args.dry_run:
        logger.info("dry run complete — %d row(s) valid, database untouched", len(rows))
        return 0
    try:
        created, updated, unchanged = asyncio.run(_upsert(rows))
    except Exception as exc:  # report and exit non-zero; no partial-success claim
        logger.error("database seeding failed: %s", exc)
        return 2
    logger.info(
        "seed complete — %d created, %d updated, %d unchanged (%d rows)",
        created,
        updated,
        unchanged,
        len(rows),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
