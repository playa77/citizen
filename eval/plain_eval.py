"""Plain-language gate (WP-122/WP-123/WP-125, D-068).

Offline — no database, no LLM, no network. Checks a module's plain-language
copy and the core copy, then runs the module's plain goldset through the
deterministic chain (Fristen core → renderer):

* ``schema`` — every declared copy file validates (``citizen-plain-copy-v1.0``);
* ``coverage`` — ``de`` and ``en`` cover every finding category (prompt
  profile ``result_categories`` + ``einordnung_offen``) and every deadline
  spec with every status it can reach; ``de-LS`` covers every *critical*
  deadline (roadmap WP-122: Leichte Sprache for critical copy);
* ``placeholders`` — only whitelisted placeholders, never one a status
  cannot fill (``frist_ende`` in ``missing_input``/``not_applicable``);
* ``readability`` — no sentence over the register's word limit
  (``app/plain/languages.py``);
* ``duty_of_care`` — no discouraging phrase (``app/plain/checks.py``);
* ``goldset`` — every case's expected status, text key, dates, banner and
  ``contains``/``excludes`` strings;
* ``core`` — core copy structure and pins (disclaimer/disclosure version),
  readability and duty of care.

Human review (OQ-3) is reported, not gated: ``review_pending`` lists copy
whose ``review.status`` is still ``draft``. Exit code 1 when a check fails.

Usage::

    python -m eval.plain_eval --module sozialrecht [--save]
"""

# Version: 1.0.0 | 2026-11-17 — WP-122 initial.

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = PROJECT_ROOT / "eval" / "results" / "plain"
REPORT_FORMAT = "citizen-plain-eval-v1.0"
GOLDSET_FORMAT = "citizen-plain-goldset-v1.0"

#: Statuses a deadline spec can reach, and the placeholders each can fill.
_STATUS_FILLS: dict[str, set[str]] = {
    "computed": {"frist_ende", "bekanntgabe", "basis", "oq1_alternate_ende"},
    "provisional": {"frist_ende", "bekanntgabe", "basis", "oq1_alternate_ende"},
    "missing_input": {"basis"},
    "not_applicable": {"bekanntgabe", "basis"},
}


def _git_sha() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return out.stdout.strip() or None


def _reachable_texts(spec: Any) -> list[str]:
    """Text keys a spec needs (a ``<status>.<frist_typ>`` key may fall back to ``<status>``).

    Every status is reachable for every spec: ``missing_input`` without a
    letter date, ``not_applicable`` for a document that is no
    Verwaltungsakt. The ``.jahr`` refinements apply when the spec declares a
    longer period for a missing Rechtsbehelfsbelehrung.
    """
    needed = ["computed", "provisional", "missing_input", "not_applicable"]
    if getattr(spec, "missing_rechtsbehelfsbelehrung", None) is not None:
        needed += ["computed.jahr", "provisional.jahr"]
    return needed


def check_copy(module_id: str) -> tuple[dict[str, list[str]], dict[str, Any]]:
    """Static checks on the module copy. Returns ``(failures by check, info)``."""
    from app.modules.content import load_yaml
    from app.modules.runtime import deadline_specs, get_manifest
    from app.plain.checks import discouraging_hits, iter_texts, long_sentences
    from app.plain.copy import declared_copy_files, finding_categories, validate_copy
    from app.plain.languages import CRITICAL_LANGUAGE, REQUIRED_LANGUAGES, register_for
    from app.plain.render import DEADLINE_PLACEHOLDERS, placeholders

    failures: dict[str, list[str]] = {
        k: [] for k in ("schema", "coverage", "placeholders", "readability", "duty_of_care")
    }
    manifest = get_manifest(module_id)
    files = declared_copy_files(manifest)
    categories = [c.key for c in finding_categories(manifest)]
    specs = deadline_specs(module_id)
    review_pending: list[str] = []
    docs: dict[str, dict[str, Any]] = {}

    if not files:
        failures["coverage"].append("module declares no plain_language files")
    for language in REQUIRED_LANGUAGES:
        if language not in files:
            failures["coverage"].append(f"{language}: required language not declared")
    if any(s.severity == "critical" for s in specs) and CRITICAL_LANGUAGE not in files:
        failures["coverage"].append(f"{CRITICAL_LANGUAGE}: required for critical deadlines")

    for language, rel in files.items():
        doc = load_yaml(manifest, rel)
        errors = validate_copy(doc, manifest, language)
        if errors:
            failures["schema"].extend(f"{language}: {e}" for e in errors)
            continue
        docs[language] = doc
        if (doc.get("review") or {}).get("status") != "reviewed":
            review_pending.append(language)
        limit = register_for(language).max_sentence_words
        for path, text in iter_texts(doc):
            for n, sentence in long_sentences(text, limit):
                failures["readability"].append(
                    f"{language}:{path}: {n} words > {limit}: {sentence[:80]}"
                )
            for hit in discouraging_hits(text):
                failures["duty_of_care"].append(f"{language}:{path}: discouraging {hit!r}")
            for name in placeholders(text):
                if name not in DEADLINE_PLACEHOLDERS or not path.startswith("deadlines/"):
                    failures["placeholders"].append(f"{language}:{path}: {{{name}}} not allowed")

    for language, doc in docs.items():
        full = language in REQUIRED_LANGUAGES
        findings = doc.get("findings") or {}
        if full:
            for key in categories:
                if key not in findings:
                    failures["coverage"].append(f"{language}: finding {key!r} missing")
        for key in findings:
            if key not in categories:
                failures["coverage"].append(f"{language}: finding {key!r} is no category")
        deadlines = doc.get("deadlines") or {}
        spec_ids = {s.id for s in specs}
        for spec_id in deadlines:
            if spec_id not in spec_ids:
                failures["coverage"].append(f"{language}: deadline {spec_id!r} is no spec")
        for spec in specs:
            if not full and spec.severity != "critical":
                continue
            entry = deadlines.get(spec.id)
            if entry is None:
                failures["coverage"].append(f"{language}: deadline {spec.id!r} missing")
                continue
            texts = entry.get("texts") or {}
            for key in _reachable_texts(spec):
                if key not in texts and key.split(".")[0] not in texts:
                    failures["coverage"].append(f"{language}: {spec.id}.texts.{key} missing")
            for key, text in texts.items():
                status = key.split(".")[0]
                for name in placeholders(text):
                    if name == "oq1_alternate_ende" or name not in _STATUS_FILLS[status]:
                        failures["placeholders"].append(
                            f"{language}: {spec.id}.texts.{key}: {{{name}}} cannot be filled "
                            f"for status {status!r}"
                        )
    info = {
        "languages": sorted(files),
        "categories": categories,
        "deadline_specs": [s.id for s in specs],
        "review_pending": sorted(review_pending),
    }
    return failures, info


def check_core() -> tuple[list[str], list[str]]:
    """Core copy: structure, pins, readability, duty of care. ``(failures, review_pending)``."""
    from app.core.config import Settings
    from app.plain.checks import discouraging_hits, iter_texts, long_sentences
    from app.plain.core_copy import CORE_COPY_DIR, core_languages, structural_errors
    from app.plain.languages import CRITICAL_LANGUAGE, REQUIRED_LANGUAGES, register_for
    from app.services.disclosure import DISCLOSURE_VERSION

    failures: list[str] = []
    pending: list[str] = []
    expected_disclaimer = str(Settings.model_fields["DISCLAIMER_VERSION"].default)
    languages = core_languages()
    for language in (*REQUIRED_LANGUAGES, CRITICAL_LANGUAGE):
        if language not in languages:
            failures.append(f"core: language {language!r} missing")
    for language in languages:
        doc = yaml.safe_load((CORE_COPY_DIR / f"{language}.yaml").read_text(encoding="utf-8"))
        errors = structural_errors(doc, language)
        failures.extend(f"core:{language}: {e}" for e in errors)
        if errors:
            continue
        if doc.get("disclaimer_version") != expected_disclaimer:
            failures.append(
                f"core:{language}: pinned to disclaimer {doc.get('disclaimer_version')!r}, "
                f"current default is {expected_disclaimer!r}"
            )
        if str(doc.get("disclosure_version")) != DISCLOSURE_VERSION:
            failures.append(f"core:{language}: pinned to another disclosure version")
        if (doc.get("review") or {}).get("status") != "reviewed":
            pending.append(language)
        limit = register_for(language).max_sentence_words
        for path, text in iter_texts(doc):
            if path in ("disclaimer_version", "disclosure_version"):
                continue
            for n, sentence in long_sentences(text, limit):
                failures.append(f"core:{language}:{path}: {n} words > {limit}: {sentence[:80]}")
            for hit in discouraging_hits(text):
                failures.append(f"core:{language}:{path}: discouraging {hit!r}")
    return failures, sorted(pending)


def _case_item(module_id: str, case: dict[str, Any]) -> dict[str, Any]:
    from app.dossier.chronology import KIND_DOCUMENT_DATE, ChronologyEntry
    from app.dossier.deadlines import ModuleSpecs, compute_deadlines
    from app.modules.runtime import deadline_specs

    chronology = []
    if case.get("proposed_letter_date"):
        chronology.append(
            ChronologyEntry(
                entry_id="plain-goldset",
                date=date.fromisoformat(str(case["proposed_letter_date"])),
                kind=KIND_DOCUMENT_DATE,
                label_de="Datum des Schreibens",
                status="proposed",
                source={"document": "case_input"},
            )
        )
    section = compute_deadlines(
        [ModuleSpecs(module_id, deadline_specs(module_id))],
        dict(case.get("facts") or {}),
        chronology,
    )
    for item in section["items"]:
        if item["spec_id"] == case["spec_id"]:
            return dict(item)
    raise KeyError(f"{case['id']}: spec {case['spec_id']!r} produced no item")


def _check_strings(
    case_id: str, texts: dict[str, Any], expect: dict[str, Any], field_names: tuple[str, ...]
) -> list[str]:
    errors: list[str] = []
    for mode in ("contains", "excludes"):
        for language, needles in (expect.get(mode) or {}).items():
            block = texts.get(language)
            if block is None:
                errors.append(f"{case_id}: no {language} text")
                continue
            haystack = " ".join(str(block.get(f, "")) for f in field_names)
            for needle in needles:
                present = needle in haystack
                if mode == "contains" and not present:
                    errors.append(f"{case_id}/{language}: missing {needle!r}")
                if mode == "excludes" and present:
                    errors.append(f"{case_id}/{language}: must not contain {needle!r}")
    return errors


def run_goldset(module_id: str, case_ids: list[str] | None = None) -> tuple[list[dict], dict]:
    from app.modules.content import load_yaml
    from app.modules.runtime import get_manifest
    from app.plain.copy import copy_languages, plain_goldset_path
    from app.plain.render import deadline_banner, render_deadline, render_finding

    manifest = get_manifest(module_id)
    rel = plain_goldset_path(manifest)
    if rel is None:
        return [], {"error": "module declares no plain_language.goldset"}
    goldset = load_yaml(manifest, rel)
    if goldset.get("format") != GOLDSET_FORMAT or goldset.get("module") != module_id:
        return [], {"error": f"{rel}: not a {GOLDSET_FORMAT} goldset of {module_id!r}"}
    languages = copy_languages(manifest)
    results: list[dict[str, Any]] = []
    for case in goldset.get("cases") or []:
        if case_ids and case["id"] not in case_ids:
            continue
        expect = case.get("expect") or {}
        errors: list[str] = []
        if case["kind"] == "deadline":
            item = _case_item(module_id, case)
            rendered = render_deadline(manifest, item, languages)
            for key in ("status", "frist_ende"):
                if key in expect and rendered[key] != expect[key]:
                    errors.append(f"{key}: {rendered[key]!r} != {expect[key]!r}")
            if "text_key" in expect:
                for language, block in rendered["texts"].items():
                    if block["text_key"] != expect["text_key"]:
                        errors.append(f"{language}: text_key {block['text_key']!r}")
            if "banner" in expect:
                banner = deadline_banner([rendered])
                if bool(banner) != bool(expect["banner"]):
                    errors.append(f"banner: {banner!r}, expected {expect['banner']!r}")
            missing = list(rendered["missing_languages"])
            if missing and expect.get("status") != "not_applicable":
                # every declared language must render an actionable deadline
                errors.append(f"not rendered in: {missing}")
            errors += _check_strings(
                case["id"], rendered["texts"], expect, ("title", "text", "action")
            )
        elif case["kind"] == "finding":
            rendered = render_finding(manifest, case.get("ergebnis"), languages)
            for key in ("category", "category_source"):
                if key in expect and rendered[key] != expect[key]:
                    errors.append(f"{key}: {rendered[key]!r} != {expect[key]!r}")
            errors += _check_strings(
                case["id"], rendered["texts"], expect, ("title", "text", "next_step")
            )
        else:
            errors.append(f"unknown kind {case['kind']!r}")
        results.append(
            {"case_id": case["id"], "kind": case["kind"], "passed": not errors, "errors": errors}
        )
    return results, {"version": goldset.get("version"), "path": rel}


def evaluate(module_id: str, case_ids: list[str] | None = None) -> dict[str, Any]:
    """Run every check; the report dict (``gate_passed`` is None for a case subset)."""
    copy_failures, info = check_copy(module_id)
    core_failures, core_pending = check_core()
    cases, goldset_meta = run_goldset(module_id, case_ids)
    failures = {k: v for k, v in copy_failures.items() if v}
    if core_failures:
        failures["core"] = core_failures
    case_errors = [f"{c['case_id']}: {e}" for c in cases for e in c["errors"]]
    if "error" in goldset_meta:
        case_errors.append(goldset_meta["error"])
    if case_errors:
        failures["goldset"] = case_errors
    subset = bool(case_ids)
    return {
        "format": REPORT_FORMAT,
        "module": module_id,
        **info,
        "core_review_pending": core_pending,
        "goldset": goldset_meta,
        "cases_passed": sum(1 for c in cases if c["passed"]),
        "cases_total": len(cases),
        "cases": cases,
        "failures": failures,
        "subset": case_ids if subset else None,
        "gate_passed": None if subset else not failures,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Citizen plain-language gate (offline)")
    parser.add_argument("--module", default="sozialrecht")
    parser.add_argument("--case", action="append", help="run only these goldset case ids")
    parser.add_argument("--save", action="store_true", help="write a report to eval/results/plain/")
    args = parser.parse_args(argv)

    from app.core.config import get_app_version
    from app.modules.runtime import get_manifest

    started = datetime.now(UTC)
    print(f"[{started.isoformat(timespec='seconds')}] plain-language gate: module {args.module}")
    report = evaluate(args.module, args.case)
    for case in report["cases"]:
        mark = "ok" if case["passed"] else "FAIL"
        print(f"  {case['case_id']:<8} {case['kind']:<9} {mark}")
        for err in case["errors"]:
            print(f"      {err}")
    for check, items in report["failures"].items():
        if check == "goldset":
            continue
        print(f"  {check}: {len(items)} failure(s)")
        for item in items:
            print(f"      {item}")
    print(
        f"\nLanguages: {', '.join(report['languages'])} · goldset "
        f"{report['cases_passed']}/{report['cases_total']} · review pending (OQ-3): module "
        f"{report['review_pending'] or '—'}, core {report['core_review_pending'] or '—'}"
    )
    if report["gate_passed"] is None:
        print("Gate: not evaluated (--case subset)")
    else:
        print(
            "Gate: "
            + ("PASS" if report["gate_passed"] else "FAIL — " + ", ".join(report["failures"]))
        )

    if args.save:
        module_version = str(get_manifest(args.module).raw.get("version"))
        stamp = started.strftime("%Y%m%dT%H%M%SZ")
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        path = RESULTS_DIR / (
            f"{args.module}-plain-goldset-v{report['goldset'].get('version')}"
            f"-core{get_app_version()}-{args.module}{module_version}-{stamp}.json"
        )
        report = {
            **report,
            "module_version": module_version,
            "core_version": get_app_version(),
            "git_sha": _git_sha(),
            "run_timestamp": started.isoformat(),
        }
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Report saved: {path.relative_to(PROJECT_ROOT)}")
    return 0 if report["gate_passed"] in (True, None) else 1


if __name__ == "__main__":
    sys.exit(main())
