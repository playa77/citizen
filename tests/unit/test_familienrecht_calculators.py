"""Literal statutory arithmetic and qualification refusals, without inference."""

from datetime import date
from pathlib import Path

import pytest
import yaml

ROOT = Path("modules/familienrecht")


def calc():
    assert (ROOT / "calculators.py").exists(), "Family calculators absent"
    from app.modules.content import import_module_file
    from app.modules.registry import default_modules_root, discover_modules

    return import_module_file(
        discover_modules(default_modules_root())["familienrecht"], "calculators"
    )


def rows():
    assert (ROOT / "parameters/maintenance.yaml").exists(), "Statutory parameters absent"
    return {
        r["key"]: {**r, "value": r["value_json"]}
        for r in yaml.safe_load((ROOT / "parameters/maintenance.yaml").read_text())["parameters"]
    }


def facts(kind="minimum_maintenance", **changes):
    f = {
        "calculation_type": kind,
        "as_of": "2026-11-27",
        "period_month": "2026-11-01",
        "age_at_month_end": 5,
        "applicability_confirmed": True,
        "current_regime_confirmed": True,
        "age_for_period_confirmed": True,
        "minor_entire_month_confirmed": True,
        "separate_households_confirmed": True,
        "one_parent_care_confirmed": True,
        "full_child_benefit_confirmed": True,
        "no_special_credit_confirmed": True,
        "uvg_eligibility_confirmed": True,
        "full_month_eligibility_confirmed": True,
        "stable_age_band_entire_month_confirmed": True,
        "no_section2_4_deductions_confirmed": True,
        "complete_income_confirmed": True,
        "additional_12_17_conditions_confirmed": True,
        "maintenance_received_cents": 0,
        "orphan_received_cents": 0,
    }
    f.update(changes)
    return f


def result(f, params=None):
    return calc().process_extraction(f, rows() if params is None else params)[0]


@pytest.mark.parametrize(
    "age,gross,net,uvg",
    [
        (0, 48600, 35650, 22700),
        (5, 48600, 35650, 22700),
        (6, 55800, 42850, 29900),
        (11, 55800, 42850, 29900),
        (12, 65300, 52350, 39400),
        (17, 65300, 52350, 39400),
    ],
)
def test_literal_statutory_age_bands_and_different_credit(age, gross, net, uvg):
    a = result(facts(age_at_month_end=age))
    b = result(facts("uvg_amount", age_at_month_end=age))
    assert a["status"] == b["status"] == "provisional"
    assert a["computed_values"]["minimum_cents"] == gross
    assert a["computed_values"]["amount_cents"] == net
    assert b["computed_values"]["amount_cents"] == uvg
    assert a["computed_values"]["child_benefit_credit_cents"] == 12950
    assert b["computed_values"]["child_benefit_credit_cents"] == 25900
    assert a["computed_values"]["deterministic_result"]["review_status"] == "proposed"


@pytest.mark.parametrize(
    "payments,orphan,expected", [(10001, 2000, 10699), (22700, 0, 0), (30000, 100, 0)]
)
def test_uvg_deducts_monthly_receipts_with_zero_floor(payments, orphan, expected):
    r = result(
        facts("uvg_amount", maintenance_received_cents=payments, orphan_received_cents=orphan)
    )
    assert r["computed_values"]["amount_cents"] == expected


@pytest.mark.parametrize(
    "kind,key,value",
    [
        ("minimum_maintenance", "age_at_month_end", True),
        ("minimum_maintenance", "age_at_month_end", 18),
        ("minimum_maintenance", "age_at_month_end", -1),
        ("minimum_maintenance", "age_at_month_end", 5.0),
        ("minimum_maintenance", "as_of", "2027-01-01"),
        ("minimum_maintenance", "period_month", "2025-11-01"),
        ("minimum_maintenance", "period_month", "2026-11-02"),
        ("minimum_maintenance", "period_month", "2026-12-01"),
        ("minimum_maintenance", "age_for_period_confirmed", None),
        ("minimum_maintenance", "minor_entire_month_confirmed", False),
        ("minimum_maintenance", "one_parent_care_confirmed", False),
        ("minimum_maintenance", "separate_households_confirmed", None),
        ("minimum_maintenance", "full_child_benefit_confirmed", False),
        ("minimum_maintenance", "no_special_credit_confirmed", False),
        ("minimum_maintenance", "current_regime_confirmed", "true"),
        ("minimum_maintenance", "applicability_confirmed", 1),
        ("uvg_amount", "uvg_eligibility_confirmed", None),
        ("uvg_amount", "full_month_eligibility_confirmed", False),
        ("uvg_amount", "stable_age_band_entire_month_confirmed", None),
        ("uvg_amount", "complete_income_confirmed", None),
        ("uvg_amount", "no_section2_4_deductions_confirmed", False),
        ("uvg_amount", "maintenance_received_cents", -1),
        ("uvg_amount", "orphan_received_cents", True),
        ("uvg_amount", "orphan_received_cents", 1.5),
        ("uvg_amount", "full_child_benefit_confirmed", False),
    ],
)
def test_unknown_or_unsupported_facts_never_guess(kind, key, value):
    r = result(facts(kind, **{key: value}))
    assert r["status"] == "unavailable"
    assert r["computed_values"]["deterministic_result"] is None
    assert "amount_cents" not in r["computed_values"]
    assert r["commentary"]


def test_uvg_older_children_require_additional_eligibility():
    assert (
        result(
            facts("uvg_amount", age_at_month_end=12, additional_12_17_conditions_confirmed=None)
        )["status"]
        == "unavailable"
    )
    assert (
        result(facts("uvg_amount", age_at_month_end=5, additional_12_17_conditions_confirmed=None))[
            "status"
        ]
        == "provisional"
    )


@pytest.mark.parametrize("event", ["information_request", "default", "lis_pendens"])
def test_qualified_1613_event_is_month_condition_not_filing_deadline(event):
    r = result(
        facts(
            "retroactive_maintenance",
            event_on="2026-10-23",
            event_basis=event,
            minor_child_regime_confirmed=True,
            event_legally_effective_confirmed=True,
            claim_existed_month_start_confirmed=True,
            no_special_retroactivity_confirmed=True,
        )
    )
    assert r["status"] == "provisional"
    assert r["computed_values"]["conditional_start_date"] == "2026-10-01"
    assert "frist_ende" not in r["computed_values"]
    assert "keine Ausschlussfrist" in r["commentary"]


def test_retroactivity_missing_or_future_event_is_unavailable():
    f = facts(
        "retroactive_maintenance",
        event_on="2026-10-23",
        event_basis="information_request",
        minor_child_regime_confirmed=True,
        event_legally_effective_confirmed=True,
        claim_existed_month_start_confirmed=True,
        no_special_retroactivity_confirmed=True,
    )
    for key, value in [
        ("claim_existed_month_start_confirmed", None),
        ("event_on", "2026-12-01"),
        ("event_on", "2025-12-31"),
        ("event_basis", "letter_written"),
        ("event_legally_effective_confirmed", False),
        ("no_special_retroactivity_confirmed", False),
    ]:
        assert result({**f, key: value})["status"] == "unavailable"


def test_no_parameters_or_out_of_period_parameter_row_never_falls_back():
    assert result(facts(), {})["status"] == "unavailable"
    p = rows()
    p["maintenance_rules"]["valid_to"] = date(2026, 10, 31)
    assert result(facts(), p)["status"] == "unavailable"
    assert calc().process_extraction({"calculation_type": "none"}, {}) == []


async def test_loader_preserves_parameter_provenance_without_requesting_unknown_types():
    class Source:
        def __init__(self):
            self.calls = []

        async def json(self, key, day):
            self.calls.append((key, day))
            return rows()[key]

    s = Source()
    loaded, meta = await calc().load_parameters(facts(), s)
    assert s.calls == [("maintenance_rules", date(2026, 11, 27))]
    assert loaded["maintenance_rules"] and meta["parameter_versions"] == [
        "maintenance_rules@2026-01-01"
    ]
    assert await calc().load_parameters({"calculation_type": "none"}, s) == ({}, None)
