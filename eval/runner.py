# Version: 1.0.0 | 2026-07-12
"""CLI entry point for the Citizen eval harness.

Usage::

    python -m eval.runner eval/goldsets/goldset-v0.1.0.yaml \\
        [--case CASE_ID] [--save] [--baseline BASELINE_PATH]

Runs the full pipeline on each goldset case, computes metrics, and optionally
saves an ``EvalReport`` to ``eval/results/``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from eval.pipeline_adapter import PipelineOutput

from eval.extractors import (
    extract_assessment_from_pipeline,
    extract_calculation_values,
    extract_citations_from_pipeline,
    extract_issues_from_pipeline,
)
from eval.goldset_loader import (
    GoldsetCase,
    GoldsetDocument,
    audit_goldset,
    load_goldset,
)
from eval.metrics import (
    compute_assessment_match,
    compute_calculation_exact_match,
    compute_citation_precision,
    compute_frist_exact_match,
    compute_issue_recall,
    compute_leakage_rate,
    compute_over_redaction_count,
    compute_pii_precision,
    compute_pii_recall,
    compute_quote_verification_rate,
    compute_reinjection_integrity,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Fristen engine inputs for goldset cases (GS-001 through GS-010)
# ---------------------------------------------------------------------------

_FRISTEN_INPUTS: dict[str, dict[str, Any]] = {
    "GS-001": {
        "bescheid_datum": date(2026, 7, 6),
        "aufgabe_zur_post": date(2026, 7, 6),
        "rbb_status": "korrekt",
        "bundesland": "NW",
    },
    "GS-002": {
        "bescheid_datum": date(2026, 6, 15),
        "aufgabe_zur_post": date(2026, 6, 15),
        "rbb_status": "korrekt",
        "bundesland": "NW",
    },
    "GS-003": {
        "bescheid_datum": date(2026, 6, 8),
        "aufgabe_zur_post": date(2026, 6, 8),
        "rbb_status": "korrekt",
        "bundesland": "NW",
    },
    "GS-004": {
        "bescheid_datum": date(2026, 6, 22),
        "aufgabe_zur_post": date(2026, 6, 22),
        "rbb_status": "korrekt",
        "bundesland": "NW",
    },
    "GS-005": {
        "bescheid_datum": date(2026, 7, 9),
        "aufgabe_zur_post": date(2026, 7, 9),
        "rbb_status": "korrekt",
        "bundesland": "NW",
    },
    "GS-006": {
        "bescheid_datum": date(2026, 7, 6),
        "aufgabe_zur_post": date(2026, 7, 6),
        "rbb_status": "korrekt",
        "bundesland": "NW",
    },
    "GS-007": {
        "bescheid_datum": date(2026, 6, 29),
        "ist_verwaltungsakt": False,
        "bundesland": "NW",
    },
    "GS-008": {
        "bescheid_datum": date(2026, 6, 18),
        "aufgabe_zur_post": date(2026, 6, 18),
        "rbb_status": "korrekt",
        "bundesland": "NW",
    },
    "GS-009": {
        "bescheid_datum": date(2026, 6, 29),
        "aufgabe_zur_post": date(2026, 6, 29),
        "rbb_status": "korrekt",
        "bundesland": "NW",
    },
    "GS-010": {
        "bescheid_datum": date(2026, 2, 9),
        "aufgabe_zur_post": date(2026, 2, 9),
        "rbb_status": "fehlerhaft",
        "bundesland": "NW",
    },
}


# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Report data structures
# ---------------------------------------------------------------------------


@dataclass
class CaseMetrics:
    """Per-case evaluation metrics."""

    case_id: str
    issue_recall: float
    citation_precision: float
    calculation_exact_match: float | None  # None if no numeric expectations
    frist_exact_match: float | None  # WP-21: deterministic Fristen engine
    assessment_match: float | None  # None if expected_assessment is None
    quote_verification_rate: float  # WP-12: fraction of claims verified
    latency_ms: int
    errors: list[str] = field(default_factory=list)
    # PII metrics (WP-32), None when --pii-gate is off
    leakage_rate: float | None = None
    pii_recall: float | None = None
    pii_precision: float | None = None
    over_redaction_count: int | None = None
    reinjection_integrity: float | None = None


@dataclass
class EvalReport:
    """Full evaluation report for one run."""

    goldset_version: str
    goldset_path: str
    git_sha: str
    run_timestamp: str  # ISO 8601
    cases: list[CaseMetrics] = field(default_factory=list)
    aggregate: dict[str, float | None] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Git SHA helper
# ---------------------------------------------------------------------------


def _get_git_sha() -> str:
    """Return the short Git SHA of the current HEAD, or ``"unknown"``."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return "unknown"


# ---------------------------------------------------------------------------
# Aggregate computation
# ---------------------------------------------------------------------------


def _compute_aggregate(cases: list[CaseMetrics]) -> dict[str, float | None]:
    """Compute mean of each metric across all cases, excluding ``None`` values.

    If a metric is ``None`` for every case, the aggregate is ``None``.
    """
    keys = [
        "issue_recall",
        "citation_precision",
        "calculation_exact_match",
        "frist_exact_match",
        "assessment_match",
        "quote_verification_rate",
        "leakage_rate",
        "pii_recall",
        "pii_precision",
        "reinjection_integrity",
    ]
    aggregate: dict[str, float | None] = {}

    for key in keys:
        values = [getattr(c, key) for c in cases if getattr(c, key) is not None]
        if values:
            aggregate[key] = sum(values) / len(values)
        else:
            aggregate[key] = None

    # Additional aggregate: average latency
    latencies = [c.latency_ms for c in cases]
    aggregate["avg_latency_ms"] = round(sum(latencies) / len(latencies)) if latencies else None

    return aggregate


# ---------------------------------------------------------------------------
# Per-case metric computation
# ---------------------------------------------------------------------------


def _compute_case_metrics(
    case: GoldsetCase,
    output: PipelineOutput,
    *,
    pii_gate: bool = False,
) -> CaseMetrics:
    """Run all extractors and metrics for a single case."""
    # Extract
    pipeline_norms = extract_citations_from_pipeline(output)
    pipeline_issues_norm_sets = extract_issues_from_pipeline(output)
    pipeline_assessment = extract_assessment_from_pipeline(output)
    pipeline_calc_values = extract_calculation_values(output)

    # Compute metrics
    issue_recall = compute_issue_recall(
        pipeline_issues_norm_sets,
        case.expected.legal_issues,
    )
    citation_precision = compute_citation_precision(
        pipeline_norms,
        case.expected.citations,
    )
    calculation_exact_match = compute_calculation_exact_match(
        pipeline_calc_values,
        case.expected.calculation,
    )
    frist_exact_match = compute_frist_exact_match(case)
    # frist_exact_match is called via the metric function above
    assessment_match = compute_assessment_match(
        pipeline_assessment,
        case.expected.overall_assessment,
    )
    quote_verification_rate = compute_quote_verification_rate(
        output.verified_claims,
    )

    # PII metrics (optional, only when --pii-gate on)
    leakage_rate: float | None = None
    pii_recall: float | None = None
    pii_precision: float | None = None
    over_redaction_count: int | None = None
    reinjection_integrity: float | None = None

    if pii_gate:
        try:
            from app.services.pseudonymization import (
                depseudonymize_tolerant,
                pseudonymize,
            )

            original_text = case.input_document.text
            pseudo_text, mapping = pseudonymize(original_text)

            # Leakage rate
            leakage_rate = compute_leakage_rate(pseudo_text, mapping)

            # PII recall
            pii_recall = compute_pii_recall(original_text, case.pii_annotations, mapping)

            # PII precision
            pii_precision = compute_pii_precision(original_text, case.pii_annotations, mapping)

            # Over-redaction count
            over_redaction_count = compute_over_redaction_count(
                pseudo_text, original_text, case.negative_controls
            )

            # Reinjection integrity (roundtrip)
            depseudo_text, _warnings = depseudonymize_tolerant(pseudo_text, mapping)
            reinjection_integrity = compute_reinjection_integrity(
                original_text, pseudo_text, depseudo_text
            )
        except Exception as exc:
            logger.warning("PII metrics failed for %s: %s", case.id, exc)

    return CaseMetrics(
        case_id=case.id,
        issue_recall=issue_recall,
        citation_precision=citation_precision,
        calculation_exact_match=calculation_exact_match,
        frist_exact_match=frist_exact_match,
        assessment_match=assessment_match,
        quote_verification_rate=quote_verification_rate,
        latency_ms=output.latency_ms,
        errors=output.errors,
        leakage_rate=leakage_rate,
        pii_recall=pii_recall,
        pii_precision=pii_precision,
        over_redaction_count=over_redaction_count,
        reinjection_integrity=reinjection_integrity,
    )


# ---------------------------------------------------------------------------
# Pretty-printing
# ---------------------------------------------------------------------------


def _format_pct(value: float | None) -> str:
    """Format a float as a percentage string, or ``"N/A"`` if ``None``."""
    if value is None:
        return "   N/A"
    return f"{value * 100:6.1f}%"


def _print_per_case(case: GoldsetCase, metrics: CaseMetrics) -> None:
    """Print a single case's results in a compact table row."""
    errors_flag = " ⚠" if metrics.errors else ""
    pii_extra = ""
    if metrics.leakage_rate is not None:
        pii_extra = (
            f"  leak={metrics.leakage_rate:.0%}"
            f" r={metrics.pii_recall:.0%}"
            f" p={metrics.pii_precision:.0%}"
        )
        if metrics.over_redaction_count is not None:
            pii_extra += f" over={metrics.over_redaction_count}"
        if metrics.reinjection_integrity is not None:
            pii_extra += f" reinj={metrics.reinjection_integrity:.0%}"
    print(
        f"  {metrics.case_id:24s}"
        f"  {_format_pct(metrics.issue_recall)}"
        f"  {_format_pct(metrics.citation_precision)}"
        f"  {_format_pct(metrics.calculation_exact_match)}"
        f"  {_format_pct(metrics.frist_exact_match)}"
        f"  {_format_pct(metrics.assessment_match)}"
        f"  {_format_pct(metrics.quote_verification_rate)}"
        f"  {metrics.latency_ms:6d}ms"
        f"{errors_flag}"
        f"{pii_extra}"
    )


def _print_aggregate(aggregate: dict[str, float | None]) -> None:
    """Print the aggregate row."""
    print(
        f"  {'--- AGGREGATE ---':24s}"
        f"  {_format_pct(aggregate.get('issue_recall'))}"
        f"  {_format_pct(aggregate.get('citation_precision'))}"
        f"  {_format_pct(aggregate.get('calculation_exact_match'))}"
        f"  {_format_pct(aggregate.get('frist_exact_match'))}"
        f"  {_format_pct(aggregate.get('assessment_match'))}"
        f"  {_format_pct(aggregate.get('quote_verification_rate'))}"
        f"  {'':>6s}"
    )
    # Print PII aggregate on a separate line if present
    if aggregate.get("leakage_rate") is not None:
        print(
            f"  {'--- PII AGGREGATE ---':24s}"
            f"  leak={_format_pct(aggregate.get('leakage_rate'))}"
            f"  recall={_format_pct(aggregate.get('pii_recall'))}"
            f"  prec={_format_pct(aggregate.get('pii_precision'))}"
            f"  reinj={_format_pct(aggregate.get('reinjection_integrity'))}"
        )


# ---------------------------------------------------------------------------
# Report serialisation
# ---------------------------------------------------------------------------


def _save_report(report: EvalReport, goldset_path: str) -> Path:
    """Serialize an ``EvalReport`` to ``eval/results/<timestamp>-<sha>.json``.

    Returns the path to the saved file.
    """
    results_dir = Path(__file__).resolve().parent / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    sha = report.git_sha or "unknown"
    filename = f"{timestamp}-{sha}.json"
    path = results_dir / filename

    # Convert dataclasses to dicts
    report_dict: dict[str, Any] = {
        "goldset_version": report.goldset_version,
        "goldset_path": report.goldset_path,
        "git_sha": report.git_sha,
        "run_timestamp": report.run_timestamp,
        "cases": [asdict(c) for c in report.cases],
        "aggregate": report.aggregate,
    }

    path.write_text(
        json.dumps(report_dict, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info("Report saved to %s", path)
    return path


def _load_report(path_str: str) -> EvalReport:
    """Load an ``EvalReport`` from a JSON file."""
    path = Path(path_str)
    data = json.loads(path.read_text(encoding="utf-8"))

    cases = [CaseMetrics(**c) for c in data["cases"]]
    return EvalReport(
        goldset_version=data["goldset_version"],
        goldset_path=data["goldset_path"],
        git_sha=data["git_sha"],
        run_timestamp=data["run_timestamp"],
        cases=cases,
        aggregate=data["aggregate"],
    )


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------


async def run_eval(
    goldset_path: str,
    *,
    case_filter: str | None = None,
    save: bool = False,
    baseline_path: str | None = None,
    pii_gate: bool = False,
) -> EvalReport:
    """Run the full eval suite on a goldset file.

    Parameters
    ----------
    goldset_path :
        Path to the goldset YAML file.
    case_filter :
        If provided, only run the case with this ID.
    save :
        If ``True``, save the report to ``eval/results/``.
    baseline_path :
        If provided, run a regression gate against this baseline report.

    Returns
    -------
    EvalReport
        The full evaluation report with per-case metrics.
    """
    # ── Load goldset ───────────────────────────────────────────────────
    logger.info("Loading goldset from %s ...", goldset_path)
    doc: GoldsetDocument = load_goldset(goldset_path)
    logger.info(
        "Loaded: %s v%s — %d cases",
        doc.goldset.id,
        doc.goldset.version,
        len(doc.cases),
    )

    # ── Audit ──────────────────────────────────────────────────────────
    warnings = audit_goldset(doc)
    for w in warnings:
        logger.warning("Audit: %s", w)

    # ── Filter cases ───────────────────────────────────────────────────
    cases: list[GoldsetCase] = list(doc.cases)
    if case_filter:
        cases = [c for c in cases if c.id == case_filter]
        if not cases:
            logger.error("Case '%s' not found in goldset", case_filter)
            sys.exit(1)
        logger.info("Filtered to single case: %s", case_filter)

    # ── Print table header ─────────────────────────────────────────────
    print()
    header = (
        f"  {'Case ID':24s}"
        f"  {'Recall':>6s}"
        f"  {'Prec':>6s}"
        f"  {'Calc':>6s}"
        f"  {'Frist':>6s}"
        f"  {'Asses':>6s}"
        f"  {'Quote':>6s}"
        f"  {'Lat':>6s}"
    )
    print(header)
    print("-" * len(header))

    # ── Run each case ──────────────────────────────────────────────────
    all_metrics: list[CaseMetrics] = []
    for case in cases:
        logger.info("[%s] Running pipeline ...", case.id)
        print(f"  {case.id:24s}  Running...", end="\r")

        from eval.pipeline_adapter import run_pipeline_for_case

        output = await run_pipeline_for_case(case)
        metrics = _compute_case_metrics(case, output, pii_gate=pii_gate)
        all_metrics.append(metrics)

        _print_per_case(case, metrics)

    # ── Print aggregate ────────────────────────────────────────────────
    print("-" * len(header))
    aggregate = _compute_aggregate(all_metrics)
    _print_aggregate(aggregate)
    print()

    # ── Build report ───────────────────────────────────────────────────
    report = EvalReport(
        goldset_version=doc.goldset.version,
        goldset_path=goldset_path,
        git_sha=_get_git_sha(),
        run_timestamp=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        cases=all_metrics,
        aggregate=aggregate,
    )

    # ── Save if requested ──────────────────────────────────────────────
    if save:
        _save_report(report, goldset_path)

    # ── Run regression gate if baseline provided ───────────────────────
    if baseline_path:
        from eval.regression_gate import regression_gate

        baseline = _load_report(baseline_path)
        logger.info("Running regression gate against baseline: %s", baseline_path)

        gate_result = regression_gate(report, baseline)

        print("=" * 60)
        print("REGRESSION GATE RESULTS")
        print("=" * 60)

        if gate_result.deterministic_failures:
            print(f"\n❌ Deterministic failures ({len(gate_result.deterministic_failures)}):")
            for msg in gate_result.deterministic_failures:
                print(f"   • {msg}")

        if gate_result.llm_warnings:
            print(f"\n⚠ LLM regressions (warn-only, {len(gate_result.llm_warnings)}):")
            for msg in gate_result.llm_warnings:
                print(f"   • {msg}")

        if gate_result.passed:
            print("\n✓ Gate PASSED — no deterministic regressions.")
        else:
            print("\n❌ Gate FAILED — deterministic regressions detected.")
            # Signal failure via exit code is handled in main()

        print("=" * 60)

    return report


def _setup_logging() -> None:
    """Configure logging with ISO 8601 timestamps per project guidelines."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )


async def main() -> None:
    """CLI entry point."""
    _setup_logging()

    parser = argparse.ArgumentParser(description="Citizen Eval Runner")
    parser.add_argument("goldset", help="Path to goldset YAML file")
    parser.add_argument("--case", help="Run only a specific case ID")
    parser.add_argument("--save", action="store_true", help="Save report to eval/results/")
    parser.add_argument("--baseline", help="Path to baseline report for regression gate")
    parser.add_argument(
        "--pii-gate",
        choices=["on", "off"],
        default="off",
        help="Enable PII metric computation (default: off for backward compat)",
    )
    args = parser.parse_args()

    report = await run_eval(
        args.goldset,
        case_filter=args.case,
        save=args.save,
        baseline_path=args.baseline,
        pii_gate=(args.pii_gate == "on"),
    )

    # If we ran a regression gate and it failed, exit with code 1
    if args.baseline:
        from eval.regression_gate import regression_gate

        baseline = _load_report(args.baseline)
        gate_result = regression_gate(report, baseline)
        if not gate_result.passed:
            sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())
