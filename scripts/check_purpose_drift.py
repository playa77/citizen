#!/usr/bin/env python3
"""Purpose-drift lint for Citizen documentation (WP-61; extended by WP-96).

Scans project documentation for authority-side phrasing that contradicts the
declared intended purpose (D-020, widened by D-035): Citizen is a citizen-side
self-help and appointment-preparation tool for natural persons in their own
legal matters — NOT a tool that an authority, court, law-enforcement or
migration body (or a contractor acting for one) uses to evaluate, decide on or
enforce against individuals (Annex III(5)(a), (6), (7) AI Act). The lint
guards the Annex III self-assessment in DISCLAIMER_*.md Part C against copy
drift.

Scan set (WP-96, closes C-3):
    core     README*.md, DISCLAIMER_*.md, ARCHITECTURE.md, docs/*.md —
             a core pattern without matches is reported as a warning
    modules  modules/*/copy/** (every file), modules/*/DISCLAIMER_ADDENDUM.md —
             optional: modules without copy or addendum are normal

Deny phrases = built-in defaults + every installed module's manifest
``compliance.purpose_drift_deny_file`` (JSON list of strings; the module ids
are listed as phrase sources) + ``--deny-phrase-file`` + ``--extra-deny``.
Module phrases apply to the whole scan set: core documents describe every
module, so a module's forbidden framing is forbidden everywhere.

A line that deliberately quotes deny phrases (e.g. a document describing this
lint) is exempted by the marker ``purpose-drift: allow`` on the SAME line, in
Markdown as an HTML comment ``<!-- purpose-drift: allow -->``. Exemptions are
counted in the summary so they stay auditable.

Exit codes:
    0  no drift found
    1  drift found (at least one deny phrase matched)
    2  operational error (missing file, invalid deny-phrase file, ...)

Usage:
    python scripts/check_purpose_drift.py [--repo-root DIR]
        [--files FILE[,FILE...]] [--extra-deny PHRASE]...
        [--deny-phrase-file FILE.json] [--list-phrases]
"""

# Version: 2.0.0 | 2026-11-16 — WP-96: extended scan set (DISCLAIMER_*.md,
# ARCHITECTURE.md, docs/*.md, module copy + addenda), dead globs dropped
# (STATEMENT.md, COMPLIANCE*.md, docs/pitch*), per-module deny phrases from
# manifests, same-line allow marker. Exit codes and CLI flags unchanged.
# 1.0.0 | 2026-08-07 — WP-61 initial.

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

import yaml

DEFAULT_REPO_ROOT = Path(__file__).resolve().parent.parent

# Core scan targets relative to the repo root; a pattern without matches is
# a warning (it signals a renamed/removed document the lint lost track of).
DEFAULT_TARGETS: tuple[str, ...] = (
    "README*.md",
    "DISCLAIMER_*.md",
    "ARCHITECTURE.md",
    "docs/*.md",
)

# Module scan targets: optional — most modules carry no copy or addendum yet,
# so an empty match is not reported.
MODULE_TARGETS: tuple[str, ...] = (
    "modules/*/copy/**/*",
    "modules/*/DISCLAIMER_ADDENDUM.md",
)

# Same-line exemption marker (see module docstring).
ALLOW_MARKER = "purpose-drift: allow"

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


def _read_phrase_file(path: Path, label: str) -> list[str]:
    """Read a JSON deny-phrase list; raise ValueError/FileNotFoundError."""
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise FileNotFoundError(f"{label} nicht lesbar: {path} ({exc})") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} ist kein gültiges JSON: {path} ({exc})") from exc
    if not isinstance(data, list) or not all(
        isinstance(item, str) and item.strip() for item in data
    ):
        raise ValueError(f"{label} muss eine Liste nicht-leerer Strings sein: {path}")
    return list(data)


def load_module_deny_phrases(repo_root: Path) -> list[tuple[str, list[str]]]:
    """``(module_id, phrases)`` for every module manifest declaring a deny file.

    Reads ``modules/*/module.yaml`` directly (no app import: the lint runs
    without application settings). A declared file that is missing, escapes
    the module directory or is malformed is an operational error — a module
    must never lose its deny phrases silently.
    """
    result: list[tuple[str, list[str]]] = []
    for manifest_path in sorted(repo_root.glob("modules/*/module.yaml")):
        try:
            manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            raise ValueError(f"Modul-Manifest nicht lesbar: {manifest_path} ({exc})") from exc
        if not isinstance(manifest, dict):
            raise ValueError(f"Modul-Manifest ist kein Mapping: {manifest_path}")
        compliance = manifest.get("compliance")
        relative = (
            compliance.get("purpose_drift_deny_file") if isinstance(compliance, dict) else None
        )
        if relative is None:
            continue
        module_dir = manifest_path.parent.resolve()
        path = (module_dir / str(relative)).resolve()
        if not path.is_relative_to(module_dir):
            raise ValueError(
                f"Deny-Phrase-Datei liegt außerhalb des Moduls: {manifest_path} → {relative}"
            )
        module_id = str(manifest.get("id") or manifest_path.parent.name)
        result.append((module_id, _read_phrase_file(path, f"Deny-Phrase-Datei ({module_id})")))
    return result


def load_deny_phrases(
    deny_phrase_file: str | None,
    extra_deny: Sequence[str],
    module_phrases: Sequence[tuple[str, Sequence[str]]] = (),
) -> list[str]:
    """Merge default, module, file-based and CLI deny phrases (ordered, unique)."""
    phrases: list[str] = []
    seen: set[str] = set()

    def _add(phrase: str) -> None:
        key = phrase.casefold()
        if key not in seen:
            phrases.append(phrase)
            seen.add(key)

    for phrase in DEFAULT_DENY_PHRASES:
        _add(phrase)

    for _module_id, module_list in module_phrases:
        for phrase in module_list:
            _add(phrase)

    if deny_phrase_file:
        for phrase in _read_phrase_file(Path(deny_phrase_file), "Deny-Phrase-Datei"):
            _add(phrase)

    for phrase in extra_deny:
        _add(phrase)

    return phrases


def resolve_targets(
    repo_root: Path, explicit_files: Sequence[str] | None
) -> tuple[list[Path], list[str]]:
    """Resolve scan targets.

    Explicitly requested files must exist (missing -> FileNotFoundError).
    Default patterns are globs; core patterns without matches produce
    warnings, module patterns (``MODULE_TARGETS``) are optional.
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
        patterns = [(p, True) for p in DEFAULT_TARGETS] + [(p, False) for p in MODULE_TARGETS]
        for pattern, required in patterns:
            matches = sorted(p for p in repo_root.glob(pattern) if p.is_file())
            if not matches and required:
                warnings.append(f"Muster ohne Treffer (übersprungen): {pattern}")
            for path in matches:
                resolved = path.resolve()
                if resolved not in seen:
                    targets.append(resolved)
                    seen.add(resolved)

    return targets, warnings


def scan_file(path: Path, phrases: Sequence[str]) -> tuple[list[tuple[int, int, str, str]], int]:
    """Return ``(matches, allowed)``.

    ``matches``: (line_no, column, phrase, line_excerpt) for every match on a
    line without the allow marker; ``allowed``: number of lines that matched
    but carry the marker (exempted, counted for the summary).
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise OSError(f"Datei nicht lesbar: {path} ({exc})") from exc

    needles = [(phrase, phrase.casefold()) for phrase in phrases]
    matches: list[tuple[int, int, str, str]] = []
    allowed = 0
    for line_no, line in enumerate(text.splitlines(), start=1):
        haystack = line.casefold()
        if ALLOW_MARKER in haystack:
            if any(needle in haystack for _, needle in needles):
                allowed += 1
            continue
        for phrase, needle in needles:
            start = 0
            while True:
                pos = haystack.find(needle, start)
                if pos < 0:
                    break
                matches.append((line_no, pos + 1, phrase, line.strip()))
                start = pos + max(1, len(needle))
    return matches, allowed


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="check_purpose_drift",
        description="Purpose-drift lint for Citizen docs (WP-61/WP-96, D-020/D-035).",
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
        "Replaces the default target patterns (module deny phrases still apply).",
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

        module_phrases = load_module_deny_phrases(repo_root)
        phrases = load_deny_phrases(args.deny_phrase_file, args.extra_deny, module_phrases)

        if args.list_phrases:
            for phrase in phrases:
                print(phrase)
            return 0

        explicit_files: list[str] = []
        for group in args.files:
            explicit_files.extend(part.strip() for part in group.split(",") if part.strip())

        targets, warnings = resolve_targets(repo_root, explicit_files or None)

        for warning in warnings:
            print(f"WARNUNG: {warning}", file=sys.stderr)

        if not targets:
            print("FEHLER: Keine Dateien zu prüfen.", file=sys.stderr)
            return 2

        drift: list[tuple[Path, int, int, str, str]] = []
        allowed_total = 0
        for target in targets:
            matches, allowed = scan_file(target, phrases)
            allowed_total += allowed
            for line_no, col, phrase, excerpt in matches:
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

        sources = ", ".join(mid for mid, _ in module_phrases) or "keine"
        print(
            f"OK — kein Zweckdrift in {len(targets)} Datei(en) gefunden "
            f"({len(phrases)} Deny-Phrasen; Modul-Phrasen: {sources}; "
            f"per Marker ausgenommene Zeilen: {allowed_total})."
        )
        return 0

    except (FileNotFoundError, NotADirectoryError, ValueError, OSError) as exc:
        print(f"FEHLER: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
