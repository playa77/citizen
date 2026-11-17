#!/usr/bin/env python3
"""Scaffold a new Citizen module (WP-115 authoring kit).

Usage::

    python -m scripts.new_module <id> --title-de "Mietrecht" --title-en "Tenancy law"
    python -m scripts.new_module <id> --title-de … --title-en … --out-of-tree DIR

In-tree (default) writes ``modules/<id>/`` at tier ``experimental``;
``--out-of-tree DIR`` writes an installable package under DIR whose
``citizen.modules`` entry point the core discovers (tier ``community``,
WP-112). The new module is validated right away; the area-key ``order`` is
the next free value above every installed module's.

Exit codes: 0 scaffolded and valid, 1 scaffolded but validation failed,
2 refused (bad id, existing target, …).
"""

# Version: 2026-11-17.1 (WP-115)

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.modules.registry import default_modules_root
from app.modules.scaffold import (
    LAYOUT_IN_TREE,
    LAYOUT_OUT_OF_TREE,
    ScaffoldError,
    scaffold_module,
)
from app.modules.validate import validate_module_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("module_id")
    parser.add_argument("--title-de", required=True)
    parser.add_argument("--title-en", required=True)
    parser.add_argument("--out-of-tree", metavar="DIR", type=Path, default=None)
    parser.add_argument(
        "--modules-root", type=Path, default=None, help="in-tree modules directory (default: repo)"
    )
    args = parser.parse_args(argv)

    modules_root = args.modules_root or default_modules_root()
    try:
        result = scaffold_module(
            args.module_id,
            title_de=args.title_de,
            title_en=args.title_en,
            dest=args.out_of_tree or modules_root,
            layout=LAYOUT_OUT_OF_TREE if args.out_of_tree else LAYOUT_IN_TREE,
            modules_root=modules_root,
        )
    except ScaffoldError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    print(f"scaffolded {len(result.files)} file(s) in {result.package_dir or result.module_dir}")
    report = validate_module_dir(result.module_dir, modules_root)
    for error in report.errors:
        print(f"  ERROR   {error}")
    for warning in report.warnings:
        print(f"  warning {warning}")
    print("validation: " + ("ok" if report.ok else f"FAILED ({len(report.errors)} error(s))"))
    if not args.out_of_tree:
        print(
            "next: fill the TODO placeholders, add the addendum to DISCLAIMER_DE/EN.md Part D,\n"
            "      bump DISCLAIMER_VERSION (tests/unit/test_disclaimer_addenda.py), see\n"
            "      docs/MODULE-AUTHORING.md"
        )
    else:
        print("next: pip install -e <package dir>, then enable it via ENABLED_MODULES")
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
