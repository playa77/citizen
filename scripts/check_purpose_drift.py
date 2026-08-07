#!/usr/bin/env python3
"""Purpose-drift lint for Citizen documentation (WP-61, Roadmap v2.0.0).

Scans project documentation for authority-side phrasing that contradicts the
declared intended purpose (D-020): Citizen is a claimant-side self-help and
advisor-assistance tool — NOT a tool used by or on behalf of an authority to
evaluate benefit eligibility (Annex III(5)(a) AI Act). The lint enforces the
Annex III high-risk self-assessment in COMPLIANCE.md against copy drift.

Exit codes:
    0  no drift found
    1  drift found (at least one deny phrase matched)
    2  operational error (missing file, invalid deny-phrase file, ...)

Usage:
    python scripts/check_purpose_drift.py [--repo-root DIR]
        [--files FILE[,FILE...]] [--extra-deny PHRASE]...
        [--deny-phrase-file FILE.json] [--list-phrases]
"""

# Version: 1.0.0 | 2026-08-07

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

DEFAULT_REPO_ROOT = Path(__file__).resolve().parent.parent

# Scan targets relative to the repo root. "docs/pitch*" catches pitch decks
# and one-pagers; add more patterns here if the documentation grows.
DEFAULT_TARGETS: tuple[str, ...] = (
    "README*.md",
    "STATEMENT.md",
    "COMPLIANCE*.md",
    "docs/pitch*",
)

# Deny phrases for authority-side framing, matched case-insensitively.
# Deliberately NOT included: negated formulations such as "nicht zur
# behördenseitigen Bewertung" (COMPLIANCE.md) — the lint targets positive
# claims; semantic review of negations remains a human task.
DEFAULT_DENY_PHRASES: tuple[str, ...] = (
    # German
    "für jobcenter",
    "für das jobcenter",
    "für behörden",
    "für die behörde",
    "für behördliche",
    "für sozialämter",
    "für das sozialamt",
    "für die verwaltung",
    "für verwaltungszwecke",
    "für gerichte",
    "im auftrag der verwaltung",
    "im auftrag der behörde",
    "im auftrag von behörden",
    "im auftrag des jobcenters",
    "im auftrag des sozialamts",
    # English
    "for job centers",
    "for job centres",
    "for jobcenter",
    "for jobcenters",
    "for the job center",
    "for the job centre",
    "for authorities",
    "for public authorities",
    "for the authority",
    "for government agencies",
    "for the administration",
    "on behalf of the administration",
    "on behalf of authorities",
    "on behalf of an authority",
    "on behalf of public authorities",
    "on behalf of government agencies",
    "on behalf of the job center",
    "on behalf of the job centre",
    "on behalf of a job center",
    "on behalf of a job centre",
)


def load_deny_phrases(
    deny_phrase_file: str | None,
    extra_deny: Sequence[str],
) -> list[str]:
    """Merge default, file-based and CLI deny phrases into an ordered list."""
    phrases: list[str] = []
    seen: set[str] = set()

    def _add(phrase: str) -> None:
        key = phrase.casefold()
        if key not in seen:
            phrases.append(phrase)
            seen.add(key)

    for phrase in DEFAULT_DENY_PHRASES:
        _add(phrase)

    if deny_phrase_file:
        path = Path(deny_phrase_file)
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise FileNotFoundError(
                f"Deny-Phrase-Datei nicht lesbar: {path} ({exc})"
            ) from exc
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Deny-Phrase-Datei ist kein gültiges JSON: {path} ({exc})"
            ) from exc
        if not isinstance(data, list) or not all(
            isinstance(item, str) and item.strip() for item in data
        ):
            raise ValueError(
                f"Deny-Phrase-Datei muss eine Liste nicht-leerer Strings sein: {path}"
            )
        for phrase in data:
            _add(phrase)

    for phrase in extra_deny:
        _add(phrase)

    return phrases


def resolve_targets(
    repo_root: Path, explicit_files: Sequence[str] | None
) -> tuple[list[Path], list[str]]:
    """Resolve scan targets.

    Explicitly requested files must exist (missing -> FileNotFoundError).
    Default patterns are globs; patterns without matches produce warnings.
    """
    targets: list[Path] = []
    warnings: list[str] = []
    seen: set[Path] = set()

    if explicit_files:
        for name in explicit_files:
            path = (repo_root / name).resolve()
            if not path.is_file():
                raise FileNotFoundError(f"Angefragte Datei nicht gefunden: {name}")
            if path not in seen:
                targets.append(path)
                seen.add(path)
    else:
        for pattern in DEFAULT_TARGETS:
            matches = sorted(repo_root.glob(pattern))
            if not matches:
                warnings.append(f"Muster ohne Treffer (übersprungen): {pattern}")
            for path in matches:
                resolved = path.resolve()
                if resolved not in seen:
                    targets.append(resolved)
                    seen.add(resolved)

    return targets, warnings


def scan_file(
    path: Path, phrases: Sequence[str]
) -> list[tuple[int, int, str, str]]:
    """Return (line_no, column, phrase, line_excerpt) for every match."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise OSError(f"Datei nicht lesbar: {path} ({exc})") from exc

    needles = [(phrase, phrase.casefold()) for phrase in phrases]
    matches: list[tuple[int, int, str, str]] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        haystack = line.casefold()
        for phrase, needle in needles:
            start = 0
            while True:
                pos = haystack.find(needle, start)
                if pos < 0:
                    break
                matches.append((line_no, pos + 1, phrase, line.strip()))
                start = pos + max(1, len(needle))
    return matches


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="check_purpose_drift",
        description="Purpose-drift lint for Citizen docs (WP-61, D-020).",
    )
    parser.add_argument(
        "--repo-root",
        default=str(DEFAULT_REPO_ROOT),
        help="Repository root (default: derived from script location).",
    )
    parser.add_argument(
        "--files",
        action="append",
        default=[],
        help="Comma-separated files to scan, relative to repo root. "
        "Replaces the default target patterns.",
    )
    parser.add_argument(
        "--extra-deny",
        action="append",
        default=[],
        help="Additional deny phrase (repeatable).",
    )
    parser.add_argument(
        "--deny-phrase-file",
        default=None,
        metavar="FILE",
        help="JSON file containing a list of additional deny phrases.",
    )
    parser.add_argument(
        "--list-phrases",
        action="store_true",
        help="Print the effective deny-phrase list and exit.",
    )
    args = parser.parse_args(argv)

    try:
        repo_root = Path(args.repo_root).expanduser().resolve()
        if not repo_root.is_dir():
            raise NotADirectoryError(f"Repo-Root nicht gefunden: {repo_root}")

        phrases = load_deny_phrases(args.deny_phrase_file, args.extra_deny)

        if args.list_phrases:
            for phrase in phrases:
                print(phrase)
            return 0

        explicit_files: list[str] = []
        for group in args.files:
            explicit_files.extend(
                part.strip() for part in group.split(",") if part.strip()
            )

        targets, warnings = resolve_targets(repo_root, explicit_files or None)

        for warning in warnings:
            print(f"WARNUNG: {warning}", file=sys.stderr)

        if not targets:
            print("FEHLER: Keine Dateien zu prüfen.", file=sys.stderr)
            return 2

        drift: list[tuple[Path, int, int, str, str]] = []
        for target in targets:
            for line_no, col, phrase, excerpt in scan_file(target, phrases):
                rel = target.relative_to(repo_root)
                drift.append((target, line_no, col, phrase, excerpt))
                print(f'{rel}:{line_no}:{col}: Deny-Phrase "{phrase}" gefunden')
                print(f"  → {excerpt}")

        if drift:
            files_with_drift = {path for path, *_ in drift}
            print(
                f"ZWECKDRIFT GEFUNDEN: {len(drift)} Treffer in "
                f"{len(files_with_drift)} Datei(en).",
                file=sys.stderr,
            )
            return 1

        print(f"OK — kein Zweckdrift in {len(targets)} Datei(en) gefunden.")
        return 0

    except (FileNotFoundError, NotADirectoryError, ValueError, OSError) as exc:
        print(f"FEHLER: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
