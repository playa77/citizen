"""Literal employee-side statutory arithmetic, qualified facts and refusal behavior."""

import importlib.util
from datetime import date
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


def calculator():
    path = ROOT / "modules/arbeitsrecht/calculators.py"
    assert path.exists(), "Employment calculator missing"
    spec = importlib.util.spec_from_file_location("employment_checks", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def rows(as_of):
    day = date.fromisoformat(as_of)
    result = {}
    for path in (ROOT / "modules/arbeitsrecht/parameters").glob("*.yaml"):
        for row in yaml.safe_load(path.read_text())["parameters"]:
            start = date.fromisoformat(str(row["valid_from"]))
            end = date.fromisoformat(str(row["valid_to"])) if row.get("valid_to") else date.max
            if start <= day <= end:
                result[row["key"]] = {**row, "value": row["value_json"]}
    return result


def run(kind, **facts):
    extraction = {
        "calculation_type": kind,
        "as_of": "2026-11-27",
        "applicability_confirmed": True,
        **facts,
    }
    return calculator().process_extraction(extraction, rows(extraction["as_of"]))[0]


def notice(**updates):
    return {
        "employment_start": "2020-11-27",
        "received_on": "2026-11-27",
        "actor": "employer",
        "probation": False,
        "statutory_notice_confirmed": True,
        "special_regime_excluded": True,
        **updates,
    }


@pytest.mark.parametrize(
    "start,expected",
    [
        ("2024-11-28", "2026-12-31"),
        ("2024-11-27", "2026-12-31"),
        ("2021-11-27", "2027-01-31"),
        ("2018-11-27", "2027-02-28"),
        ("2006-11-27", "2027-06-30"),
    ],
)
def test_employer_notice_thresholds(start, expected):
    result = run("notice", **notice(employment_start=start))
    assert result["status"] == "provisional"
    assert result["computed_values"]["termination_date"] == expected


def test_employee_four_weeks_not_one_month_and_probation():
    assert (
        run("notice", **notice(actor="employee"))["computed_values"]["termination_date"]
        == "2026-12-31"
    )
    assert (
        run("notice", **notice(probation=True, employment_start="2026-09-01"))["computed_values"][
            "termination_date"
        ]
        == "2026-12-11"
    )
    assert run("notice", **notice(probation=True))["status"] == "unavailable"


@pytest.mark.parametrize("end,years", [("2026-06-30", 6), ("2026-07-01", 7), ("2026-12-31", 7)])
def test_severance_strictly_more_than_six_months(end, years):
    result = run(
        "severance",
        employment_start="2020-01-01",
        employment_end=end,
        monthly_earnings_cents=300001,
        section_1a_confirmed=True,
    )
    assert result["computed_values"]["employment_years"] == years
    assert result["computed_values"]["amount_cents"] == (300001 * years + 1) // 2


def test_severance_does_not_assume_universal_entitlement():
    assert (
        run(
            "severance",
            employment_start="2020-01-01",
            employment_end="2026-12-31",
            monthly_earnings_cents=300000,
        )["status"]
        == "unavailable"
    )


@pytest.mark.parametrize(
    "start,end,expected_num,expected_den",
    [
        ("2020-01-01", "2026-06-30", 10, 1),
        ("2020-01-01", "2026-07-01", 20, 1),
        ("2026-10-01", "2026-12-31", 5, 1),
        ("2026-11-01", "2026-12-31", 10, 3),
        ("2026-12-01", "2026-12-31", 2, 1),
    ],
)
def test_statutory_leave_preserves_fractions_and_partial_rounding(
    start, end, expected_num, expected_den
):
    result = run(
        "leave",
        employment_start=start,
        employment_end=end,
        working_days_per_week=5,
        leave_taken_days=0,
        statutory_leave_only_confirmed=True,
        termination_confirmed=True,
        no_prior_employer_leave_confirmed=True,
    )
    assert result["status"] == "provisional"
    assert result["computed_values"]["entitlement_days"] == {
        "numerator": expected_num,
        "denominator": expected_den,
    }


def test_leave_compensation_uses_confirmed_13_week_basis():
    result = run(
        "leave_compensation",
        leave_days="3.5",
        working_days_per_week=5,
        earnings_13_weeks_cents=900001,
        compensation_conditions_confirmed=True,
        remuneration_basis_confirmed=True,
    )
    assert result["computed_values"]["amount_cents"] == 48462
    assert (
        run(
            "leave_compensation",
            leave_days="3.5",
            working_days_per_week=5,
            earnings_13_weeks_cents=900001,
        )["status"]
        == "unavailable"
    )


@pytest.mark.parametrize(
    "day,rate", [("2025-12-31", 1282), ("2026-01-01", 1390), ("2027-01-01", 1460)]
)
def test_minimum_wage_effective_dates_and_fractional_cent_ceiling(day, rate):
    result = run(
        "minimum_wage",
        as_of=day,
        period_start=day,
        period_end=day,
        working_minutes=61,
        eligible_pay_cents=1000,
        milog_coverage_confirmed=True,
        remuneration_basis_confirmed=True,
    )
    assert result["computed_values"]["hourly_rate_cents"] == rate
    assert result["computed_values"]["amount_cents"] == (rate * 61 + 59) // 60
    assert result["discrepancy_found"] is True


def test_wage_period_cannot_cross_rate_boundary():
    assert (
        run(
            "minimum_wage",
            as_of="2026-12-31",
            period_start="2026-12-31",
            period_end="2027-01-01",
            working_minutes=60,
            eligible_pay_cents=1390,
            milog_coverage_confirmed=True,
            remuneration_basis_confirmed=True,
        )["status"]
        == "unavailable"
    )


@pytest.mark.parametrize(
    "updates",
    [
        {"applicability_confirmed": None},
        {"special_regime_excluded": None},
        {"received_on": "bad"},
        {"employment_start": "2027-01-01"},
        {"probation": "false"},
        {"as_of": "2020-01-01"},
    ],
)
def test_unknown_facts_and_out_of_snapshot_dates_refuse_arithmetic(updates):
    assert run("notice", **notice(**updates))["status"] == "unavailable"


def test_missing_parameters_never_fall_back_to_embedded_values():
    result = calculator().process_extraction(
        {
            "calculation_type": "notice",
            "as_of": "2026-11-27",
            "applicability_confirmed": True,
            **notice(),
        },
        {},
    )[0]
    assert result["status"] == "unavailable"


@pytest.mark.parametrize("value", [True, -1, 1.5, "1000"])
def test_money_must_be_nonnegative_integer_cents(value):
    assert (
        run(
            "severance",
            employment_start="2020-01-01",
            employment_end="2026-12-31",
            monthly_earnings_cents=value,
            section_1a_confirmed=True,
        )["status"]
        == "unavailable"
    )


def test_short_month_is_not_complete_before_last_day():
    result = run(
        "leave",
        employment_start="2027-01-31",
        employment_end="2027-02-27",
        working_days_per_week=5,
        leave_taken_days=0,
        statutory_leave_only_confirmed=True,
        termination_confirmed=True,
        no_prior_employer_leave_confirmed=True,
    )
    assert result["computed_values"]["entitlement_days"] == {"numerator": 0, "denominator": 1}


def test_leap_day_service_year_does_not_finish_one_day_early():
    result = run(
        "severance",
        employment_start="2020-02-29",
        employment_end="2026-08-27",
        monthly_earnings_cents=300000,
        section_1a_confirmed=True,
    )
    assert result["computed_values"]["employment_years"] == 6


def test_waiting_period_does_not_finish_before_clamped_month_end():
    result = run(
        "leave",
        employment_start="2027-03-31",
        employment_end="2027-09-29",
        working_days_per_week=5,
        leave_taken_days=0,
        statutory_leave_only_confirmed=True,
        termination_confirmed=True,
        no_prior_employer_leave_confirmed=True,
    )
    assert result["computed_values"]["entitlement_days"] == {"numerator": 25, "denominator": 3}


def test_severance_clamped_residual_is_exactly_six_months():
    result = run(
        "severance",
        employment_start="2020-08-31",
        employment_end="2027-02-28",
        monthly_earnings_cents=300000,
        section_1a_confirmed=True,
    )
    assert result["computed_values"]["employment_years"] == 6


def test_severance_residual_starts_after_clamped_year_expiry():
    result = run(
        "severance",
        employment_start="2020-02-29",
        employment_end="2026-08-31",
        monthly_earnings_cents=300000,
        section_1a_confirmed=True,
    )
    assert result["computed_values"]["employment_years"] == 6


def test_probation_includes_last_day_of_clamped_sixth_month():
    result = run(
        "notice",
        **notice(
            as_of="2027-02-28",
            received_on="2027-02-28",
            employment_start="2026-08-31",
            probation=True,
        ),
    )
    assert result["computed_values"]["termination_date"] == "2027-03-14"
