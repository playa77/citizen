"""Qualified contract arithmetic: literal amounts, deadlines and refusal boundaries."""

import importlib.util
from datetime import date
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


def calculator():
    path = ROOT / "modules/vertragsrecht/calculators.py"
    assert path.exists(), "Contract calculator missing"
    spec = importlib.util.spec_from_file_location("contract_checks", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def rows(day="2026-11-27"):
    result = {}
    for path in (ROOT / "modules/vertragsrecht/parameters").glob("*.yaml"):
        for row in yaml.safe_load(path.read_text())["parameters"]:
            if str(row["valid_from"]) <= day <= str(row["valid_to"]):
                result[row["key"]] = {**row, "value": row["value_json"]}
    return result


def run(kind, **facts):
    data = {
        "calculation_type": kind,
        "as_of": "2026-11-27",
        "applicability_confirmed": True,
        **facts,
    }
    return calculator().process_extraction(data, rows(data["as_of"]))[0]


def interest(**updates):
    return dict(
        principal_cents=100000,
        period_start="2026-06-30",
        period_end="2026-07-01",
        default_confirmed=True,
        principal_constant_confirmed=True,
        no_compounding_confirmed=True,
        consumer_involved=True,
        **updates,
    )


def withdrawal(**updates):
    return dict(
        regime="goods",
        trigger_on="2026-11-01",
        trigger_confirmed=True,
        exceptions_excluded_confirmed=True,
        notice_status="adequate",
        notice_on="2026-10-31",
        calendar_confirmed=True,
        holiday_dates=[],
        **updates,
    )


def flight(**updates):
    result = {
        "distance_km": 1500,
        "intra_eu": False,
        "eu261_scope_confirmed": True,
        "entitlement_confirmed": True,
        "claim_basis": "cancellation",
        "reduction_confirmed": False,
        "extraordinary_circumstances_excluded_confirmed": True,
    }
    result.update(updates)
    return result


def test_interest_splits_rate_change_and_rounds_once():
    result = run("default_interest", **interest())
    assert result["status"] == "provisional"
    assert result["computed_values"]["amount_cents"] == 35
    assert [x["annual_rate_basis_points"] for x in result["computed_values"]["segments"]] == [
        627,
        652,
    ]


@pytest.mark.parametrize(
    "field,value",
    [
        ("consumer_involved", None),
        ("principal_cents", True),
        ("period_end", "2027-01-01"),
        ("default_confirmed", False),
    ],
)
def test_interest_refuses_unqualified_or_uncovered_period(field, value):
    facts = interest()
    facts[field] = value
    assert run("default_interest", **facts)["status"] == "unavailable"


def test_interest_nonconsumer_rate_requires_payment_claim():
    facts = interest()
    facts["consumer_involved"] = False
    assert run("default_interest", **facts)["status"] == "unavailable"
    facts["payment_claim_confirmed"] = True
    assert run("default_interest", **facts)["computed_values"]["amount_cents"] == 57


def test_withdrawal_weekend_rollover():
    assert run("withdrawal", **withdrawal())["computed_values"]["expiry_date"] == "2026-11-16"


def test_missing_notice_outer_cap_and_late_notice_minimum():
    facts = withdrawal()
    facts.update(
        trigger_on="2025-11-01", notice_status="absent", outer_limit_rollover_confirmed=True
    )
    assert run("withdrawal", **facts)["computed_values"]["expiry_date"] == "2026-11-16"
    facts.update(notice_status="late", notice_on="2026-11-10")
    assert run("withdrawal", **facts)["computed_values"]["expiry_date"] == "2026-11-16"


@pytest.mark.parametrize(
    "field,value",
    [
        ("trigger_confirmed", False),
        ("regime", "digital"),
        ("notice_status", None),
        ("calendar_confirmed", False),
    ],
)
def test_withdrawal_refuses_missing_qualifications(field, value):
    facts = withdrawal()
    facts[field] = value
    assert run("withdrawal", **facts)["status"] == "unavailable"


@pytest.mark.parametrize(
    "distance,intra,amount",
    [
        (1500, False, 25000),
        (1501, False, 40000),
        (3500, False, 40000),
        (3501, False, 60000),
        (5000, True, 40000),
    ],
)
def test_flight_bands(distance, intra, amount):
    assert (
        run("flight_compensation", **flight(distance_km=distance, intra_eu=intra))[
            "computed_values"
        ]["amount_cents"]
        == amount
    )


def test_flight_reduction_requires_legal_confirmation():
    assert run("flight_compensation", **flight(reduction_confirmed=None))["status"] == "unavailable"
    assert (
        run("flight_compensation", **flight(reduction_confirmed=True))["computed_values"][
            "amount_cents"
        ]
        == 12500
    )
    assert (
        run("flight_compensation", **flight(entitlement_confirmed=False))["status"] == "unavailable"
    )


def test_missing_parameters_and_unknown_kind_never_fallback():
    module = calculator()
    assert (
        module.process_extraction(
            {
                "calculation_type": "withdrawal",
                "as_of": "2026-11-27",
                "applicability_confirmed": True,
            },
            {},
        )[0]["status"]
        == "unavailable"
    )
    assert run("unknown")["status"] == "unavailable"
    assert module.process_extraction({"calculation_type": "none"}) == []


def test_withdrawal_leap_anniversary_and_confirmed_holiday():
    facts = withdrawal()
    facts.update(
        trigger_on="2024-02-29",
        notice_status="absent",
        holiday_dates=["2025-03-14"],
        outer_limit_rollover_confirmed=True,
    )
    assert run("withdrawal", **facts)["computed_values"]["expiry_date"] == "2025-03-17"


def test_interest_leap_year_and_uncovered_historical_period():
    facts = interest()
    facts.update(period_start="2024-02-29", period_end="2024-02-29")
    assert run("default_interest", **facts)["status"] == "unavailable"
    parameters = rows()
    parameters["default_interest_rates"]["value"]["segments"] = [
        {"start": "2024-01-01", "end": "2024-12-31", "basis_points": 362}
    ]
    extraction = {
        "calculation_type": "default_interest",
        "as_of": "2026-11-27",
        "applicability_confirmed": True,
        **facts,
    }
    result = calculator().process_extraction(extraction, parameters)[0]
    assert result["computed_values"]["amount_cents"] == 24
    assert result["computed_values"]["segments"][0]["year_days"] == 366


def test_expired_parameter_snapshot_refused():
    assert run("flight_compensation", as_of="2027-01-01", **flight())["status"] == "unavailable"


async def test_loader_snapshot_retains_parameter_identity():
    class Source:
        async def json(self, key, day):
            assert day == date(2026, 11, 27)
            return rows()[key]

    loaded, snapshot = await calculator().load_parameters(
        {"calculation_type": "withdrawal", "as_of": "2026-11-27"}, Source()
    )
    assert (
        calculator().process_extraction(
            {
                "calculation_type": "withdrawal",
                "as_of": "2026-11-27",
                "applicability_confirmed": True,
                **withdrawal(),
            },
            loaded,
        )[0]["computed_values"]["expiry_date"]
        == "2026-11-16"
    )
    assert snapshot["parameter_versions"] == ["contract_rules@2026-11-27"]


def test_outer_cap_weekend_requires_separate_legal_rollover_confirmation():
    facts = withdrawal()
    facts.update(trigger_on="2025-11-01", notice_status="absent")
    assert run("withdrawal", **facts)["status"] == "unavailable"
    facts["outer_limit_rollover_confirmed"] = True
    assert run("withdrawal", **facts)["computed_values"]["expiry_date"] == "2026-11-16"


@pytest.mark.parametrize(
    "kind,key,facts",
    [
        (
            "withdrawal",
            "withdrawal_outer_months",
            {**withdrawal(), "notice_status": "absent", "outer_limit_rollover_confirmed": True},
        ),
        ("flight_compensation", "flight_reduction_divisor", flight(reduction_confirmed=True)),
    ],
)
def test_missing_statutory_rule_parameter_has_no_code_default(kind, key, facts):
    parameters = rows()
    parameters["contract_rules"]["value"].pop(key, None)
    result = calculator().process_extraction(
        {"calculation_type": kind, "as_of": "2026-11-27", "applicability_confirmed": True, **facts},
        parameters,
    )[0]
    assert result["status"] == "unavailable"
