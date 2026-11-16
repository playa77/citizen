# Version: 1.2.0 | 2026-11-16 — WP-97 follow-up: a sourced quote rate that
# has no denominator in the current run (zero sourced claims) is reported as
# "undefined (no sourced claims)", never confused with a measured 0 %.
# 1.1.0 | 2026-11-16 — CR-09/CR-13: warns when baseline and run used
# different prompt sets; sourced quote verification compared (warn-only).
# 1.0.0 | 2026-07-12
"""Per-case monotonic regression gate (D-6).

Compares a current eval run against a baseline report and determines whether
deterministic metrics have regressed. LLM-dependent metrics are reported as
warnings but do not fail the gate.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from eval.runner import EvalReport

logger = logging.getLogger(__name__)


@dataclass
class GateResult:
    """Result of a regression gate comparison."""

    passed: bool
    deterministic_failures: list[str] = field(default_factory=list)
    llm_warnings: list[str] = field(default_factory=list)


def regression_gate(current: EvalReport, baseline: EvalReport) -> GateResult:
    """Per-case monotonic regression gate.

    Compares each case in the baseline report against the current run:

    * **Deterministic metrics** (``calculation_exact_match``,
      ``frist_exact_match``, ``quote_verification_rate``): strict fail — if
      any case degrades (float decreases or goes from present to absent), it
      is recorded as a deterministic failure.
    * **LLM-dependent metrics** (``issue_recall``, ``citation_precision``,
      ``assessment_match``): warn-only — degradation is reported but does
      not fail the gate.
    * Cases present in the baseline but **missing** from the current run
      are counted as deterministic failures.

    This implements decision **D-6**: deterministic regressions block the
    deployment; LLM regressions are surfaced for human review.

    Parameters
    ----------
    current :
        The current eval run report.
    baseline :
        The baseline (reference) eval run report.

    Returns
    -------
    GateResult
        With ``passed`` set to ``True`` only if there are zero deterministic
        failures.
    """
    failures: list[str] = []
    warnings: list[str] = []

    # CR-09: a baseline from another prompt set (or one recorded before prompt
    # identities existed) is still compared, but the reader is told.
    base_ps = (getattr(baseline, "prompt_set", None) or {}).get("version")
    curr_ps = (getattr(current, "prompt_set", None) or {}).get("version")
    if base_ps != curr_ps:
        warnings.append(
            f"prompt set differs: baseline={base_ps or 'unrecorded'}, "
            f"current={curr_ps or 'unrecorded'} — LLM metric changes are expected"
        )

    # Build lookup dicts by case_id
    current_by_id: dict[str, Any] = {c.case_id: c for c in current.cases}
    baseline_by_id: dict[str, Any] = {c.case_id: c for c in baseline.cases}

    all_case_ids = set(baseline_by_id.keys()) | set(current_by_id.keys())

    for case_id in sorted(all_case_ids):
        base = baseline_by_id.get(case_id)
        curr = current_by_id.get(case_id)

        # Case missing from current run
        if base is not None and curr is None:
            msg = f"Case {case_id}: present in baseline but missing from current run"
            failures.append(msg)
            logger.warning("REGRESSION: %s", msg)
            continue

        # Case present in current but not in baseline (new case — skip)
        if curr is not None and base is None:
            logger.info("Case %s: new in current run — no baseline to compare", case_id)
            continue

        # Both present: compare metrics
        if base is None or curr is None:
            continue

        # --- Deterministic metrics (strict) ---

        # calculation_exact_match
        _compare_metric(
            case_id,
            "calculation_exact_match",
            base.calculation_exact_match,
            curr.calculation_exact_match,
            strict=True,
            failures=failures,
            warnings=warnings,
        )

        # frist_exact_match — always None until WP-21, skip
        if base.frist_exact_match is not None or curr.frist_exact_match is not None:
            _compare_metric(
                case_id,
                "frist_exact_match",
                base.frist_exact_match,
                curr.frist_exact_match,
                strict=True,
                failures=failures,
                warnings=warnings,
            )

        # quote_verification_rate — deterministic (WP-12)
        _compare_metric(
            case_id,
            "quote_verification_rate",
            base.quote_verification_rate,
            curr.quote_verification_rate,
            strict=True,
            failures=failures,
            warnings=warnings,
        )

        # leakage_rate — deterministic (WP-32), must not increase
        if base.leakage_rate is not None or curr.leakage_rate is not None:
            _compare_metric(
                case_id,
                "leakage_rate",
                base.leakage_rate,
                curr.leakage_rate,
                strict=True,
                failures=failures,
                warnings=warnings,
            )

        # --- LLM-dependent metrics (warn-only) ---

        # quote_verification_rate_sourced (1.1.0) — only when the baseline has it
        if getattr(base, "quote_verification_rate_sourced", None) is not None:
            _compare_metric(
                case_id,
                "quote_verification_rate_sourced",
                base.quote_verification_rate_sourced,
                curr.quote_verification_rate_sourced,
                strict=False,
                failures=failures,
                warnings=warnings,
                undefined_label="undefined (no sourced claims)",
            )

        # issue_recall
        _compare_metric(
            case_id,
            "issue_recall",
            base.issue_recall,
            curr.issue_recall,
            strict=False,
            failures=failures,
            warnings=warnings,
        )

        # citation_precision
        _compare_metric(
            case_id,
            "citation_precision",
            base.citation_precision,
            curr.citation_precision,
            strict=False,
            failures=failures,
            warnings=warnings,
        )

        # assessment_match
        _compare_metric(
            case_id,
            "assessment_match",
            base.assessment_match,
            curr.assessment_match,
            strict=False,
            failures=failures,
            warnings=warnings,
        )

        # pii_recall — LLM-dependent (warn-only)
        if base.pii_recall is not None or curr.pii_recall is not None:
            _compare_metric(
                case_id,
                "pii_recall",
                base.pii_recall,
                curr.pii_recall,
                strict=False,
                failures=failures,
                warnings=warnings,
            )

        # pii_precision — LLM-dependent (warn-only)
        if base.pii_precision is not None or curr.pii_precision is not None:
            _compare_metric(
                case_id,
                "pii_precision",
                base.pii_precision,
                curr.pii_precision,
                strict=False,
                failures=failures,
                warnings=warnings,
            )

    passed = len(failures) == 0
    return GateResult(passed=passed, deterministic_failures=failures, llm_warnings=warnings)


def _compare_metric(
    case_id: str,
    metric_name: str,
    base_val: float | None,
    curr_val: float | None,
    *,
    strict: bool,
    failures: list[str],
    warnings: list[str],
    undefined_label: str = "None",
) -> None:
    """Compare a single metric between baseline and current.

    Parameters
    ----------
    case_id :
        Case identifier for log messages.
    metric_name :
        Human-readable metric name.
    base_val :
        Baseline value (``None`` means not applicable).
    curr_val :
        Current value (``None`` means not applicable).
    strict :
        If ``True``, degradation is recorded as a failure; otherwise as a
        warning.
    failures :
        List to which deterministic failure messages are appended.
    warnings :
        List to which LLM warning messages are appended.
    undefined_label :
        How a ``None`` current value is rendered. For ratio metrics whose
        denominator can legitimately be empty (``quote_verification_rate_sourced``
        with zero sourced claims) this names the cause, so the reader does not
        mistake "no denominator" for a measured 0 %.
    """
    # Both None → skip (metric not applicable in either run)
    if base_val is None and curr_val is None:
        return

    # Baseline has a value but current doesn't → regression
    if base_val is not None and curr_val is None:
        msg = (
            f"Case {case_id} — {metric_name}: baseline={base_val:.4f}, "
            f"current={undefined_label}"
        )
        if strict:
            failures.append(msg)
            logger.warning("REGRESSION: %s", msg)
        else:
            warnings.append(msg)
            logger.warning("LLM regression (warn): %s", msg)
        return

    # Current has a value but baseline doesn't → improvement, not regression
    if base_val is None and curr_val is not None:
        logger.info("Case %s — %s: N/A → %.4f (improvement)", case_id, metric_name, curr_val)
        return

    # Both have values: check for degradation
    if base_val is not None and curr_val is not None and curr_val < base_val:
        msg = (
            f"Case {case_id} — {metric_name}: baseline={base_val:.4f}, "
            f"current={curr_val:.4f} (Δ={curr_val - base_val:+.4f})"
        )
        if strict:
            failures.append(msg)
            logger.warning("REGRESSION: %s", msg)
        else:
            warnings.append(msg)
            logger.warning("LLM regression (warn): %s", msg)
