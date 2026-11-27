"""Literal tenancy arithmetic and refusal contracts; no inference or database."""

import importlib.util
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


def calculator():
    path = ROOT / "modules/mietrecht/calculators.py"
    assert path.exists(), "WP-131 tenancy calculator has not been implemented"
    spec = importlib.util.spec_from_file_location("tenancy_calculators", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def params():
    rows = {}
    for path in (ROOT / "modules/mietrecht/parameters").glob("*.yaml"):
        for row in yaml.safe_load(path.read_text())["parameters"]:
            rows[row["key"]] = {**row, "value": row["value_json"]}
    return rows


def run(kind, **facts):
    return calculator().process_extraction(
        {"calculation_type": kind, "as_of": "2026-11-26", "applicability_confirmed": True, **facts},
        params(),
    )[0]


def increase(**updates):
    return {
        "bundesland": "BE",
        "municipality": "Berlin",
        "municipality_confirmed": True,
        "base_rent_cents": 60000,
        "current_rent_cents": 65000,
        "comparison_rent_cents": 80000,
        "requested_rent_cents": 70000,
        "baseline_confirmed": True,
        "stability_confirmed": True,
        "waiting_period_confirmed": True,
        "rent_regime": "ordinary",
        "subsidy_exception": False,
        **updates,
    }


def brake(**updates):
    return {
        "bundesland": "BE",
        "municipality": "Berlin",
        "municipality_confirmed": True,
        "comparison_rent_cents": 60001,
        "requested_rent_cents": 70000,
        "exceptions_checked": True,
        "new_build": False,
        "first_after_comprehensive_modernisation": False,
        "prior_rent_exception": False,
        "modernisation_exception": False,
        **updates,
    }


def test_cap_uses_three_year_baseline_not_current_rent():
    result = run("rent_increase", **increase())
    assert result["computed_values"]["amount_cents"] == 69000
    assert result["discrepancy_found"] is True
    assert result["status"] == "provisional"


def test_comparison_rent_is_independent_ceiling():
    assert (
        run("rent_increase", **increase(comparison_rent_cents=67000))["computed_values"][
            "amount_cents"
        ]
        == 67000
    )


@pytest.mark.parametrize(
    "updates",
    [
        {"municipality": "Potsdam"},
        {"bundesland": "HH", "municipality": "Hamburg"},
        {"municipality_confirmed": False},
        {"subsidy_exception": True},
        {"rent_regime": "index"},
        {"baseline_confirmed": False},
        {"stability_confirmed": None},
        {"as_of": "2028-05-11"},
    ],
)
def test_unknown_expired_or_unqualified_cap_never_defaults(updates):
    assert run("rent_increase", **increase(**updates))["status"] == "missing_input"


def test_rent_brake_rounds_qualified_ceiling_down_to_whole_cent():
    result = run("rent_brake", **brake())
    assert result["computed_values"]["amount_cents"] == 66001


@pytest.mark.parametrize(
    "key",
    [
        "new_build",
        "first_after_comprehensive_modernisation",
        "prior_rent_exception",
        "modernisation_exception",
    ],
)
def test_rent_brake_exceptions_require_separate_review(key):
    for value in [True, None]:
        assert run("rent_brake", **brake(**{key: value}))["status"] == "missing_input"


@pytest.mark.parametrize(
    "state,municipality,day,expected",
    [
        ("SN", "Leipzig", "2027-06-30", "provisional"),
        ("SN", "Leipzig", "2027-07-01", "missing_input"),
        ("HH", "Hamburg", "2029-12-31", "provisional"),
        ("HH", "Hamburg", "2030-01-01", "missing_input"),
        ("BE", "berlin", "2026-11-26", "missing_input"),
    ],
)
def test_regional_rules_match_exact_municipality_and_period(state, municipality, day, expected):
    assert (
        run("rent_brake", **brake(bundesland=state, municipality=municipality, as_of=day))["status"]
        == expected
    )


def test_operating_cost_allocation_and_advance_balance():
    result = run(
        "operating_costs",
        cost_category="operating",
        total_cost_cents=100001,
        tenant_units=1,
        total_units=3,
        advance_paid_cents=30000,
        allocation_confirmed=True,
        contract_allocation_confirmed=True,
        nonallocable_costs_present=False,
    )
    assert result["computed_values"]["amount_cents"] == 33334
    assert result["computed_values"]["balance_cents"] == 3334


def test_heating_combines_consumption_and_area_without_deducing_reduction():
    result = run(
        "operating_costs",
        cost_category="heating",
        total_cost_cents=100000,
        tenant_units=1,
        total_units=10,
        tenant_consumption_units=2,
        total_consumption_units=10,
        consumption_share_percent=70,
        heating_70_required=True,
        heating_exceptions=False,
        advance_paid_cents=0,
        allocation_confirmed=True,
        contract_allocation_confirmed=True,
        nonallocable_costs_present=False,
    )
    assert result["computed_values"]["amount_cents"] == 17000
    assert "reduction_percent" not in result["computed_values"]


@pytest.mark.parametrize(
    "updates",
    [
        {"total_units": 0},
        {"tenant_units": 11},
        {"consumption_share_percent": 49},
        {"consumption_share_percent": 60, "heating_70_required": True},
        {"heating_exceptions": True},
        {"nonallocable_costs_present": True},
    ],
)
def test_cost_allocation_refuses_unqualified_keys_and_nonallocable_items(updates):
    facts = {
        "cost_category": "heating",
        "total_cost_cents": 100000,
        "tenant_units": 1,
        "total_units": 10,
        "tenant_consumption_units": 2,
        "total_consumption_units": 10,
        "consumption_share_percent": 70,
        "heating_70_required": True,
        "heating_exceptions": False,
        "advance_paid_cents": 0,
        "allocation_confirmed": True,
        "contract_allocation_confirmed": True,
        "nonallocable_costs_present": False,
    }
    assert run("operating_costs", **{**facts, **updates})["status"] == "missing_input"


def termination(**updates):
    return {
        "actor": "tenant",
        "received_on": "2027-01-05",
        "bundesland": "BE",
        "ordinary_residential_confirmed": True,
        "special_contract": False,
        "feiertagskalender_bestaetigt": True,
        "feiertage_zusaetzlich": [],
        **updates,
    }


@pytest.mark.parametrize(
    "received,end",
    [
        ("2027-01-05", "2027-03-31"),
        ("2027-01-06", "2027-04-30"),
        ("2027-05-05", "2027-07-31"),
        ("2027-05-06", "2027-08-31"),
    ],
)
def test_termination_counts_saturday_but_not_holidays(received, end):
    assert (
        run("ordinary_termination", **termination(received_on=received))["computed_values"][
            "termination_date"
        ]
        == end
    )


@pytest.mark.parametrize(
    "handover,expected",
    [("2022-01-05", "2027-06-30"), ("2022-01-06", "2027-03-31"), ("2019-01-05", "2027-09-30")],
)
def test_landlord_notice_extends_at_five_and_eight_year_boundaries(handover, expected):
    result = run("ordinary_termination", **termination(actor="landlord", handed_over_on=handover))
    assert result["computed_values"]["termination_date"] == expected


def test_termination_requires_local_calendar_confirmation_and_special_review():
    assert (
        run("ordinary_termination", **termination(feiertagskalender_bestaetigt=False))["status"]
        == "missing_input"
    )
    assert (
        run("ordinary_termination", **termination(special_contract=True))["status"]
        == "missing_input"
    )


def test_deposit_cap_is_three_net_rents_and_not_payment_due():
    result = run(
        "deposit", net_rent_cents=65001, cash_deposit_confirmed=True, stated_amount_cents=200000
    )
    assert result["computed_values"]["amount_cents"] == 195003
    assert result["computed_values"]["instalments"] == 3
    assert result["discrepancy_found"] is True


@pytest.mark.parametrize("value", [True, 1.5, -1, None])
def test_monetary_input_must_be_nonnegative_integer_cents(value):
    assert (
        run("deposit", net_rent_cents=value, cash_deposit_confirmed=True)["status"]
        == "missing_input"
    )


def test_unavailable_result_has_no_partial_amount_or_success_flag():
    result = run("rent_increase", **increase(base_rent_cents=60000, comparison_rent_cents=None))
    assert result["computed_values"]["deterministic_result"] is None
    assert "amount_cents" not in result["computed_values"]
    assert result["discrepancy_found"] is False


@pytest.mark.parametrize(
    "received,expected", [("2027-07-05", "2027-09-30"), ("2027-07-06", "2027-10-31")]
)
def test_third_workday_on_saturday_extends_receipt_cutoff(received, expected):
    result = run("ordinary_termination", **termination(received_on=received))
    assert result["computed_values"]["termination_date"] == expected
    assert result["computed_values"]["third_workday"] == "2027-07-03"
    assert result["computed_values"]["receipt_cutoff"] == "2027-07-05"


def test_comparison_below_existing_rent_does_not_assert_rent_reduction():
    result = run("rent_increase", **increase(comparison_rent_cents=64000))
    assert result["computed_values"]["amount_cents"] == 65000
    assert result["computed_values"]["comparison_ceiling_cents"] == 64000


@pytest.mark.parametrize(
    "units,total,status,amount",
    [
        (55.5, 555.0, "provisional", 10000),
        (True, 555, "missing_input", None),
        (float("nan"), 555, "missing_input", None),
        (1, float("inf"), "missing_input", None),
        ("55.5", 555, "missing_input", None),
    ],
)
def test_fractional_allocation_units_follow_public_contract(units, total, status, amount):
    result = run(
        "operating_costs",
        cost_category="operating",
        total_cost_cents=100000,
        tenant_units=units,
        total_units=total,
        advance_paid_cents=0,
        allocation_confirmed=True,
        contract_allocation_confirmed=True,
        nonallocable_costs_present=False,
    )
    assert result["status"] == status
    assert result["computed_values"].get("amount_cents") == amount
