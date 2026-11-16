"""Contract tests for the eval regression gate (``eval/regression_gate.py``).

Pins the D-6 split (deterministic metrics fail, LLM metrics warn), the CR-09
prompt-set warning and the 1.2.0 rule that an undefined sourced quote rate
(no sourced claims) is labelled as such rather than as a number.
"""

# Semantic Version: 1.0.0 | 2026-11-16 — WP-97 follow-up (gate 1.2.0).

from __future__ import annotations

from typing import Any

from eval.regression_gate import regression_gate
from eval.runner import CaseMetrics, EvalReport


def _case(case_id: str = "GS-001", **overrides: Any) -> CaseMetrics:
    values: dict[str, Any] = {
        "case_id": case_id,
        "issue_recall": 0.5,
        "citation_precision": 0.5,
        "calculation_exact_match": 1.0,
        "frist_exact_match": 1.0,
        "assessment_match": 1.0,
        "quote_verification_rate": 0.5,
        "latency_ms": 1000,
        "quote_verification_rate_sourced": 1.0,
    }
    values.update(overrides)
    return CaseMetrics(**values)


def _report(*cases: CaseMetrics, prompt_set: str = "3.0.1") -> EvalReport:
    return EvalReport(
        goldset_version="0.2.0",
        goldset_path="modules/sozialrecht/goldset/goldset-v0.2.0.yaml",
        git_sha="0000000",
        run_timestamp="2026-11-16T00:00:00Z",
        cases=list(cases),
        aggregate={},
        prompt_set={"version": prompt_set},
    )


def test_identical_runs_pass_without_warnings() -> None:
    result = regression_gate(_report(_case()), _report(_case()))
    assert result.passed
    assert result.deterministic_failures == []
    assert result.llm_warnings == []


def test_quote_verification_drop_fails_the_gate() -> None:
    result = regression_gate(
        _report(_case(quote_verification_rate=0.0)), _report(_case(quote_verification_rate=0.5))
    )
    assert not result.passed
    assert len(result.deterministic_failures) == 1
    assert "quote_verification_rate" in result.deterministic_failures[0]


def test_llm_metric_drop_only_warns() -> None:
    result = regression_gate(_report(_case(issue_recall=0.0)), _report(_case(issue_recall=0.5)))
    assert result.passed
    assert any("issue_recall" in w for w in result.llm_warnings)


def test_missing_case_fails_the_gate() -> None:
    result = regression_gate(_report(_case("GS-001")), _report(_case("GS-001"), _case("GS-002")))
    assert not result.passed
    assert any("GS-002" in f for f in result.deterministic_failures)


def test_prompt_set_difference_is_reported() -> None:
    result = regression_gate(
        _report(_case(), prompt_set="3.0.1"), _report(_case(), prompt_set="2.0.0")
    )
    assert result.passed
    assert result.llm_warnings[0].startswith("prompt set differs: baseline=2.0.0, current=3.0.1")


def test_undefined_sourced_rate_is_not_rendered_as_a_number() -> None:
    """Zero sourced claims means no denominator — not a measured 0 % (open item 3)."""
    result = regression_gate(
        _report(_case(quote_verification_rate_sourced=None)),
        _report(_case(quote_verification_rate_sourced=1.0)),
    )
    assert result.passed  # warn-only metric
    (warning,) = (w for w in result.llm_warnings if "quote_verification_rate_sourced" in w)
    assert warning.endswith("current=undefined (no sourced claims)")


def test_measured_zero_sourced_rate_is_a_numeric_regression() -> None:
    result = regression_gate(
        _report(_case(quote_verification_rate_sourced=0.0)),
        _report(_case(quote_verification_rate_sourced=1.0)),
    )
    (warning,) = (w for w in result.llm_warnings if "quote_verification_rate_sourced" in w)
    assert "current=0.0000" in warning
