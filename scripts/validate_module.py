#!/usr/bin/env python3
"""Validate Citizen modules (WP-115 authoring kit; ``app.modules.validate``).

Usage::

    python -m scripts.validate_module modules/mietrecht [PATH ...]
    python -m scripts.validate_module --module sozialrecht   # installed id (also out-of-tree)
    python -m scripts.validate_module --all [--json]

Runs offline (no database, no API key). Exit codes: 0 every module valid
(warnings allowed), 1 at least one module has errors, 2 nothing to validate.
"""

# Version: 2026-11-17.1 (WP-115)

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.modules.registry import default_modules_root, discover_installed_modules
from app.modules.validate import ValidationReport, validate_module_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("paths", nargs="*", type=Path, help="module directories")
    parser.add_argument("--module", action="append", default=[], help="installed module id")
    parser.add_argument("--all", action="store_true", help="every installed module")
    parser.add_argument("--json", action="store_true", help="machine-readable report")
    args = parser.parse_args(argv)

    root = default_modules_root()
    targets: list[Path] = list(args.paths)
    if args.module or args.all:
        installed, rejected = discover_installed_modules(root)
        for name, reason in sorted(rejected.items()):
            print(f"out-of-tree entry point {name!r} rejected: {reason}", file=sys.stderr)
        unknown = [m for m in args.module if m not in installed]
        if unknown:
            print(f"unknown module(s): {unknown} (installed: {sorted(installed)})", file=sys.stderr)
            return 2
        ids = sorted(installed) if args.all else args.module
        targets.extend(installed[m].path for m in ids)
    if not targets:
        parser.print_usage(sys.stderr)
        return 2

    reports: list[ValidationReport] = [validate_module_dir(t, root) for t in targets]
    if args.json:
        print(json.dumps([r.as_dict() for r in reports], indent=2, ensure_ascii=False))
    else:
        for r in reports:
            status = "ok" if r.ok else "FAILED"
            print(f"{r.module_id or r.path} {r.version or ''} ({r.tier or '?'}): {status}")
            for error in r.errors:
                print(f"  ERROR   {error}")
            for warning in r.warnings:
                print(f"  warning {warning}")
        failed = sum(not r.ok for r in reports)
        print(f"{len(reports)} module(s) checked, {failed} with errors")
    return 1 if any(not r.ok for r in reports) else 0


if __name__ == "__main__":
    sys.exit(main())
