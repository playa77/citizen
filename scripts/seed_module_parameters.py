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

# Version: 2026-11-17.1 (WP-111: shared upsert, feed-written rows are kept)
# 2026-11-16.1 (WP-93; supersedes seed_legal_parameters.py 1.0.0)

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from app.modules.parameters import ParameterRow, load_parameter_rows
from app.modules.registry import (
    ModuleManifestError,
    default_modules_root,
    discover_installed_modules,
)

logger = logging.getLogger("seed_module_parameters")


async def _upsert(rows: list[ParameterRow]) -> tuple[int, int, int, int]:
    """Upsert *rows*; return (created, updated, unchanged, kept-from-feed)."""
    from app.db.session import async_session_factory
    from app.modules.parameter_seed import upsert_parameter_rows
    from app.services.parameter_store import reload_parameter_cache
    from app.updates.ledger import feed_owned_parameters

    async with async_session_factory() as session:
        # WP-111: identities a signed update feed wrote are not reverted by
        # module files that predate the correction.
        protected = await feed_owned_parameters(session)
        result = await upsert_parameter_rows(session, rows, protected=protected)
        await session.commit()
        # Make the new values visible to the sync param() cache immediately.
        await reload_parameter_cache(session)
    return len(result.created), len(result.updated), len(result.unchanged), len(result.protected)


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
        modules, _rejected = discover_installed_modules(default_modules_root())
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
        created, updated, unchanged, kept = asyncio.run(_upsert(rows))
    except Exception as exc:  # report and exit non-zero; no partial-success claim
        logger.error("database seeding failed: %s", exc)
        return 2
    logger.info(
        "seed complete — %d created, %d updated, %d unchanged, %d kept from update feeds "
        "(%d rows)",
        created,
        updated,
        unchanged,
        kept,
        len(rows),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
