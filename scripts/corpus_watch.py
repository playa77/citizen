#!/usr/bin/env python3
"""Daily corpus change detection and case-law ingestion (WP-113).

Usage::

    python -m scripts.corpus_watch                      # watch the effective corpus sources
    python -m scripts.corpus_watch --sources sgb2,sgbx --json
    python -m scripts.corpus_watch --ingest             # re-ingest changed statutes
    python -m scripts.corpus_watch --case-law bsg       # ingest declared case law

Watches the statute sources of the effective corpus selection (or
``--sources``) against ``gii-toc.xml`` and each source's XML archive
validators; results are stored in ``corpus_source_watch`` and printed (one
line per source, or JSON). ``--ingest`` re-ingests ``changed`` sources (the
first run only records a baseline). ``--case-law`` ingests the case law that
verified modules declare in ``corpus.yaml`` (``case_law``).

Schedule it daily with cron or a systemd timer (``DEPLOYMENT.md``). Exit
codes: 0 run completed (changes are reported, not errors), 1 at least one
source could not be checked or ingested, 2 fatal (configuration, database).
"""

# Version: 2026-11-17.1 (WP-113)

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from typing import Any

logger = logging.getLogger("corpus_watch")


async def _run(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    from app.db.session import async_session_factory
    from app.services.corpus import (
        CASE_LAW_SOURCE_TYPES,
        get_effective_corpus_sources,
        gii_source_slugs,
    )
    from app.services.corpus_watch import ingest_sources, run_watch

    slugs = gii_source_slugs()
    if args.sources:
        sources = [s.strip() for s in args.sources.split(",") if s.strip()]
    else:
        sources = [s for s in await get_effective_corpus_sources() if s in slugs]
    report: dict[str, Any] = {"watched": [], "ingested": {}, "case_law": {}}
    failures = 0
    if sources:
        async with async_session_factory() as session:
            results = await run_watch(session, sources)
            await session.commit()
        report["watched"] = [r.as_dict() for r in results]
        failures += sum(r.status == "error" for r in results)
        changed = [r.source_type for r in results if r.status == "changed"]
        if args.ingest and changed:
            try:
                report["ingested"] = await ingest_sources(changed)
            except Exception as exc:
                logger.error("re-ingestion failed: %s", exc)
                failures += 1
    if args.case_law:
        wanted = [s.strip() for s in args.case_law.split(",") if s.strip()]
        unknown = [s for s in wanted if s not in CASE_LAW_SOURCE_TYPES]
        if unknown:
            raise ValueError(f"not case-law source types: {unknown}")
        try:
            report["case_law"] = await ingest_sources(wanted)
        except Exception as exc:
            logger.error("case-law ingestion failed: %s", exc)
            failures += 1
    return report, failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--sources", help="comma-separated statute source types")
    parser.add_argument("--ingest", action="store_true", help="re-ingest changed sources")
    parser.add_argument("--case-law", help="comma-separated case-law source types to ingest")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )
    try:
        report, failures = asyncio.run(_run(args))
    except Exception as exc:
        logger.error("corpus watch aborted: %s: %s", type(exc).__name__, exc)
        return 2
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        for entry in report["watched"]:
            extra = f" ({', '.join(entry['changed_fields'])})" if entry["changed_fields"] else ""
            error = f" — {entry['error']}" if entry["error"] else ""
            print(f"{entry['source_type']:<10} {entry['status']}{extra}{error}")
        for key in ("ingested", "case_law"):
            for source_type, count in report[key].items():
                print(f"{source_type:<10} {key}: {count} chunk(s)")
        statuses = [e["status"] for e in report["watched"]]
        print(
            f"summary: {len(statuses)} watched, {statuses.count('changed')} changed, "
            f"{statuses.count('new')} new, {statuses.count('error')} error(s)"
        )
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
