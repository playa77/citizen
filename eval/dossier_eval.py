"""Dossier goldset evaluation (WP-104; roadmap P10 exit gate).

Builds the appointment dossier for every case of a module's dossier goldset
from the base goldset's input text and the case's confirmed ``facts`` —
offline: no database, no LLM, no network. Sections that need a live
analysis (evidence, calculations) are therefore empty here; what this gate
measures is the deterministic part every dossier relies on.

Usage::

    python -m eval.dossier_eval --module sozialrecht [--save]
        [--case GS-001] [--pdf-dir DIR [--pdf-case GS-001 …]]

Metrics per case, then averaged:

* ``schema_valid`` — the dossier validates against ``citizen-dossier-v1.0``;
* ``deadline_completeness`` — share of expected deadlines present with the
  expected Fristende (``kein_verwaltungsakt`` = spec reported not
  applicable with frist_typ ``kein_va``);
* ``checklist_recall`` — share of expected checklist ids produced;
* ``chronology_accuracy`` — Jaccard overlap of (date, kind) pairs between
  produced chronology proposals and the expected chronology.

The gate thresholds come from the module's ``dossier.yaml`` ``goldset.gate``;
every dossier must be schema-valid. Exit code 1 when the gate fails.
"""

# Version: 1.0.0 | 2026-11-16 — WP-104 initial.

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = PROJECT_ROOT / "eval" / "results" / "dossier"
REPORT_FORMAT = "citizen-dossier-eval-v1.0"


@dataclass
class DossierCaseMetrics:
    case_id: str
    schema_valid: bool
    deadline_completeness: float
    checklist_recall: float
    chronology_accuracy: float
    missing_deadlines: list[str] = field(default_factory=list)
    missing_checklist: list[str] = field(default_factory=list)
    chronology_missing: list[str] = field(default_factory=list)
    chronology_extra: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _git_sha() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=PROJECT_ROOT,
        )
        return result.stdout.strip() if result.returncode == 0 else "unknown"
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"


def deadline_completeness(
    expected: list[dict[str, Any]], produced: list[dict[str, Any]]
) -> tuple[float, list[str]]:
    """Share of expected deadlines produced with the expected outcome."""
    if not expected:
        return 1.0, []
    missing: list[str] = []
    for exp in expected:
        candidates = [d for d in produced if d["spec_id"] == exp["spec_id"]]
        want = str(exp["frist_ende"])
        if want == "kein_verwaltungsakt":
            ok = any(
                d["status"] == "not_applicable" and d["frist_typ"] == "kein_va" for d in candidates
            )
        else:
            ok = any(
                d["frist_ende"] == want and d["status"] in ("computed", "provisional")
                for d in candidates
            )
        if not ok:
            got = [(d["status"], d["frist_ende"]) for d in candidates]
            missing.append(f"{exp['spec_id']}: expected {want}, got {got}")
    return (len(expected) - len(missing)) / len(expected), missing


def checklist_recall(expected: list[str], produced: list[str]) -> tuple[float, list[str]]:
    if not expected:
        return 1.0, []
    missing = [i for i in expected if i not in produced]
    return (len(expected) - len(missing)) / len(expected), missing


def chronology_accuracy(
    expected: list[dict[str, Any]], produced: list[dict[str, Any]]
) -> tuple[float, list[str], list[str]]:
    want = {(str(e["date"]), str(e["kind"])) for e in expected}
    got = {(str(e["date"]), str(e["kind"])) for e in produced}
    union = want | got
    score = len(want & got) / len(union) if union else 1.0
    return (
        score,
        sorted(f"{d} {k}" for d, k in want - got),
        sorted(f"{d} {k}" for d, k in got - want),
    )


def _load_cases(module_id: str) -> tuple[Any, dict[str, Any], dict[str, Any]]:
    from app.dossier.module_content import module_dossier
    from app.modules.content import module_path
    from app.modules.runtime import get_manifest

    content = module_dossier(module_id)
    if content is None or content.goldset_path is None:
        raise SystemExit(f"module {module_id!r} declares no dossier goldset")
    goldset = yaml.safe_load(content.goldset_path.read_text(encoding="utf-8"))
    base_rel = goldset["dossier_goldset"]["base_goldset"]
    base = yaml.safe_load(
        module_path(get_manifest(module_id), base_rel).read_text(encoding="utf-8")
    )
    base_cases = {c["id"]: c for c in base["cases"]}
    return content, goldset, base_cases


class _UnconfiguredSettings:
    """Stand-in when no deployment configuration exists: every attribute read
    raises, so provenance fields fall back to "unknown" (disclosure.py)."""

    def __getattr__(self, name: str) -> Any:
        raise RuntimeError(f"setting {name} unavailable: eval runs unconfigured")


def _settings() -> Any:
    """Live settings, or a stand-in: this eval makes no LLM calls and must not
    require an API key to run."""
    from app.core import config

    try:
        return config._get_settings()
    except Exception:
        return _UnconfiguredSettings()


def _disclaimer_version() -> str:
    from app.core.config import Settings

    try:
        return str(_settings().DISCLAIMER_VERSION)
    except Exception:
        return str(Settings.model_fields["DISCLAIMER_VERSION"].default)


def _draft_factory(module_id: str) -> Any:
    """The real draft annex when settings load; ``None`` (no annex) otherwise.

    The draft renderer reads settings at import time, so an unconfigured run
    (no ``.env``) evaluates everything except the annex — reported as
    ``drafts_included: false``.
    """
    if isinstance(_settings(), _UnconfiguredSettings):
        return None
    from app.dossier.drafts import make_draft_factory

    return make_draft_factory(module_id)


def build_case_dossier(
    module_id: str, case: dict[str, Any], base_case: dict[str, Any]
) -> dict[str, Any]:
    """Build the dossier the generator produces for one goldset case."""
    from app.dossier.builder import DossierInputs, build_dossier
    from app.dossier.chronology import SourceText
    from app.dossier.deadlines import validate_facts
    from app.services.disclosure import build_disclosure_and_provenance

    disclosure, provenance = build_disclosure_and_provenance(_settings(), [module_id])
    inputs = DossierInputs(
        case_id=case["id"],
        title=str(base_case.get("title", case["id"])),
        created_at=None,
        legal_areas=[module_id],
        module_ids=[module_id],
        sources=[SourceText("case_input", "Eingabetext", base_case["input_document"]["text"])],
        facts=validate_facts(case.get("facts") or {}),
        generated_at=datetime.now(UTC).isoformat(),
        disclosure=disclosure.model_dump(mode="json"),
        provenance=provenance.model_dump(mode="json"),
        disclaimer_version=_disclaimer_version(),
    )
    return build_dossier(inputs, _draft_factory(module_id))


def evaluate_case(
    module_id: str, case: dict[str, Any], base_case: dict[str, Any]
) -> tuple[DossierCaseMetrics, dict[str, Any] | None]:
    import jsonschema

    expected = case["expected"]
    try:
        dossier = build_case_dossier(module_id, case, base_case)
    except jsonschema.ValidationError as exc:
        return (
            DossierCaseMetrics(case["id"], False, 0.0, 0.0, 0.0, errors=[f"schema: {exc.message}"]),
            None,
        )
    sections = dossier["sections"]
    dl, dl_missing = deadline_completeness(
        expected.get("deadlines", []), sections["deadlines"]["items"]
    )
    cl, cl_missing = checklist_recall(
        expected.get("checklist", []), [i["id"] for i in sections["document_checklist"]["items"]]
    )
    ch, ch_missing, ch_extra = chronology_accuracy(
        expected.get("chronology", []), sections["chronology"]["entries"]
    )
    return (
        DossierCaseMetrics(
            case_id=case["id"],
            schema_valid=True,
            deadline_completeness=dl,
            checklist_recall=cl,
            chronology_accuracy=ch,
            missing_deadlines=dl_missing,
            missing_checklist=cl_missing,
            chronology_missing=ch_missing,
            chronology_extra=ch_extra,
        ),
        dossier,
    )


def aggregate(cases: list[DossierCaseMetrics]) -> dict[str, float]:
    n = len(cases) or 1
    return {
        "schema_valid_rate": sum(c.schema_valid for c in cases) / n,
        "deadline_completeness": sum(c.deadline_completeness for c in cases) / n,
        "checklist_recall": sum(c.checklist_recall for c in cases) / n,
        "chronology_accuracy": sum(c.chronology_accuracy for c in cases) / n,
    }


def gate(agg: dict[str, float], thresholds: dict[str, float]) -> list[str]:
    """Return the list of gate failures (empty = pass)."""
    failures = []
    if agg["schema_valid_rate"] < 1.0:
        failures.append(f"schema_valid_rate {agg['schema_valid_rate']:.3f} < 1.000")
    for metric in ("deadline_completeness", "checklist_recall", "chronology_accuracy"):
        minimum = thresholds.get(f"{metric}_min")
        if minimum is not None and agg[metric] < minimum:
            failures.append(f"{metric} {agg[metric]:.3f} < {minimum:.3f}")
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Citizen dossier goldset evaluation (offline)")
    parser.add_argument("--module", default="sozialrecht")
    parser.add_argument("--case", action="append", help="evaluate only these case ids")
    parser.add_argument(
        "--save", action="store_true", help="write a report to eval/results/dossier/"
    )
    parser.add_argument("--pdf-dir", type=Path, help="write rendered PDFs to this directory")
    parser.add_argument("--pdf-case", action="append", help="limit --pdf-dir to these case ids")
    args = parser.parse_args(argv)

    from app.core.config import get_app_version
    from app.dossier.pdf import render_pdf
    from app.modules.runtime import get_manifest

    content, goldset, base_cases = _load_cases(args.module)
    cases = [c for c in goldset["cases"] if not args.case or c["id"] in args.case]
    if not cases:
        print("no matching cases", file=sys.stderr)
        return 2

    results: list[DossierCaseMetrics] = []
    started = datetime.now(UTC)
    for index, case in enumerate(cases, start=1):
        base_case = base_cases.get(case["id"])
        if base_case is None:
            print(f"[{index}/{len(cases)}] {case['id']}: not in base goldset", file=sys.stderr)
            return 2
        metrics, dossier = evaluate_case(args.module, case, base_case)
        results.append(metrics)
        print(
            f"[{index}/{len(cases)}] {case['id']}: "
            f"schema={'ok' if metrics.schema_valid else 'FAIL'} "
            f"deadlines={metrics.deadline_completeness:.2f} "
            f"checklist={metrics.checklist_recall:.2f} chronology={metrics.chronology_accuracy:.2f}"
        )
        for line in (
            metrics.errors
            + [f"deadline: {m}" for m in metrics.missing_deadlines]
            + [f"checklist missing: {m}" for m in metrics.missing_checklist]
            + [f"chronology missing: {m}" for m in metrics.chronology_missing]
            + [f"chronology extra: {m}" for m in metrics.chronology_extra]
        ):
            print(f"      {line}")
        if (
            args.pdf_dir
            and dossier is not None
            and (not args.pdf_case or case["id"] in args.pdf_case)
        ):
            args.pdf_dir.mkdir(parents=True, exist_ok=True)
            target = args.pdf_dir / f"dossier-{args.module}-{case['id']}.pdf"
            target.write_bytes(render_pdf(dossier))
            print(f"      PDF written: {target}")

    if isinstance(_settings(), _UnconfiguredSettings):
        print("note: settings unavailable (no .env) — draft annex not built in this run")
    agg = aggregate(results)
    failures = gate(agg, content.gate)
    print("\nAggregate: " + ", ".join(f"{k}={v:.3f}" for k, v in agg.items()))
    print("Gate: " + ("PASS" if not failures else "FAIL — " + "; ".join(failures)))

    if args.save:
        module_version = str(get_manifest(args.module).raw.get("version"))
        meta = goldset["dossier_goldset"]
        stamp = started.strftime("%Y%m%dT%H%M%SZ")
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        path = RESULTS_DIR / (
            f"{args.module}-dossier-goldset-v{meta['version']}-core{get_app_version()}"
            f"-{args.module}{module_version}-{stamp}.json"
        )
        report = {
            "format": REPORT_FORMAT,
            "module": args.module,
            "module_version": module_version,
            "core_version": get_app_version(),
            "dossier_goldset_version": meta["version"],
            "base_goldset_version": meta["base_goldset_version"],
            "dossier_schema": meta["dossier_schema"],
            "git_sha": _git_sha(),
            "run_timestamp": started.isoformat(),
            "drafts_included": not isinstance(_settings(), _UnconfiguredSettings),
            "gate_thresholds": content.gate,
            "gate_passed": not failures,
            "gate_failures": failures,
            "aggregate": agg,
            "cases": [asdict(c) for c in results],
        }
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Report saved: {path.relative_to(PROJECT_ROOT)}")

    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
