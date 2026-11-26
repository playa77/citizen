"""Synthetic contracts for module-local debt arithmetic; no inference."""

import importlib.util
from datetime import date
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "debt_calculators", ROOT / "modules/schuldnerrecht/calculators.py"
)
assert spec and spec.loader
calc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(calc)


def params(kind="attachment_monthly", as_of="2026-07-01"):
    for path in (ROOT / "modules/schuldnerrecht/parameters").glob("*.yaml"):
        for row in yaml.safe_load(path.read_text())["parameters"]:
            if row["key"] == kind and str(row["valid_from"]) <= as_of <= str(row["valid_to"]):
                return {kind: {**row, "value": row["value_json"]}}
    return {}


def run(kind, **facts):
    extraction = {"calculation_type": kind, "as_of": "2026-07-01", **facts}
    return calc.process_extraction(extraction, params())[0]


@pytest.mark.parametrize(
    "income,expected",
    [(158999, 0), (159000, 182), (159999, 182), (160000, 882), (486630, 229082), (486631, 229083)],
)
def test_wage_monthly_cent_boundaries(income, expected):
    result = run(
        "wage_attachment",
        net_income_cents=income,
        dependants=0,
        dependants_confirmed=True,
        ordinary_claim=True,
        monthly=True,
        special_order=False,
    )
    assert result["computed_values"]["amount_cents"] == expected


@pytest.mark.parametrize(
    "field,value",
    [
        ("net_income_cents", True),
        ("net_income_cents", -1),
        ("net_income_cents", None),
        ("dependants", True),
        ("dependants", -1),
        ("dependants", 6),
        ("ordinary_claim", False),
        ("special_order", True),
        ("dependants_confirmed", False),
    ],
)
def test_wage_refuses_unsupported_facts(field, value):
    facts = {
        "net_income_cents": 200000,
        "dependants": 0,
        "dependants_confirmed": True,
        "ordinary_claim": True,
        "monthly": True,
        "special_order": False,
    }
    facts[field] = value
    assert run("wage_attachment", **facts)["status"] == "missing_input"


def test_p_account_requires_actual_support_and_reviews_other_increases():
    facts = {
        "dependants": 2,
        "dependants_confirmed": True,
        "actual_support": True,
        "special_order": False,
        "other_increases": False,
    }
    assert run("p_account", **facts)["computed_values"]["amount_cents"] == 252025
    facts["actual_support"] = False
    assert run("p_account", **facts)["status"] == "missing_input"
    facts["actual_support"] = True
    facts["other_increases"] = True
    assert run("p_account", **facts)["status"] == "missing_input"


def test_missing_and_wrong_period_parameters_never_fallback():
    facts = {
        "calculation_type": "p_account",
        "as_of": "2027-07-01",
        "dependants": 0,
        "dependants_confirmed": True,
        "actual_support": True,
        "special_order": False,
        "other_increases": False,
    }
    assert calc.process_extraction(facts, params())[0]["status"] == "missing_input"
    assert calc.process_extraction(facts, None)[0]["status"] == "missing_input"


def test_july_parameter_rollover():
    facts = {
        "calculation_type": "p_account",
        "dependants": 0,
        "dependants_confirmed": True,
        "actual_support": True,
        "special_order": False,
        "other_increases": False,
    }
    for day, expected in [("2026-06-30", 156000), ("2026-07-01", 159000)]:
        assert (
            calc.process_extraction({**facts, "as_of": day}, params(as_of=day))[0][
                "computed_values"
            ]["amount_cents"]
            == expected
        )


def test_limitation_explicit_ordinary_and_review_flags():
    facts = {
        "calculation_type": "limitation",
        "as_of": "2026-11-26",
        "claim_class": "ordinary",
        "applicability_confirmed": True,
        "arisen_on": "2023-03-02",
        "knowledge_on": "2023-06-01",
        "suspension": False,
        "restart": False,
        "special_limitation": False,
        "calendar_confirmed": True,
        "holiday_dates": [],
    }
    result = calc.process_extraction(facts, params("limitation_rules", "2026-11-26"))[0]
    assert result["computed_values"]["expiry_date"] == "2026-12-31"
    for field in ("suspension", "restart", "special_limitation"):
        assert (
            calc.process_extraction(
                {**facts, field: True}, params("limitation_rules", "2026-11-26")
            )[0]["status"]
            == "missing_input"
        )
    assert (
        calc.process_extraction(
            {**facts, "claim_class": "unknown"}, params("limitation_rules", "2026-11-26")
        )[0]["status"]
        == "missing_input"
    )


def test_collection_ceiling_uses_qualified_fee_not_flat_cap():
    facts = {
        "calculation_type": "collection_costs",
        "as_of": "2026-11-26",
        "principal_cents": 50000,
        "undisputed": True,
        "titled": False,
        "default_confirmed": True,
        "fee_case": "normal",
        "transition_confirmed": True,
        "duplicate_fees": False,
        "vat_recoverable": False,
        "claimed_costs_cents": 8000,
    }
    result = calc.process_extraction(facts, params("collection_rvg", "2026-11-26"))[0]
    assert result["computed_values"]["amount_cents"] == 5562
    assert result["discrepancy_found"] is True
    assert (
        calc.process_extraction(
            {**facts, "undisputed": False}, params("collection_rvg", "2026-11-26")
        )[0]["status"]
        == "missing_input"
    )


@pytest.mark.parametrize(
    "n,expected", [(0, 98882), (1, 40759), (2, 19294), (3, 4486), (4, 0), (5, 0)]
)
def test_dependant_table_columns(n, expected):
    result = run(
        "wage_attachment",
        net_income_cents=300000,
        dependants=n,
        dependants_confirmed=True,
        ordinary_claim=True,
        monthly=True,
        special_order=False,
    )
    assert result["computed_values"]["amount_cents"] == expected


def test_titled_claim_rejects_recurring_payments_and_rolls_calendar():
    facts = {
        "calculation_type": "limitation",
        "as_of": "2026-11-26",
        "claim_class": "titled",
        "applicability_confirmed": True,
        "arisen_on": "2000-01-01",
        "title_effective_on": "2000-06-01",
        "title_start_confirmed": True,
        "recurring_future_payments": False,
        "suspension": False,
        "restart": False,
        "special_limitation": False,
        "calendar_confirmed": True,
        "holiday_dates": ["2030-06-03"],
    }
    result = calc.process_extraction(facts, params("limitation_rules", "2026-11-26"))[0]
    assert result["computed_values"]["unadjusted_expiry_date"] == "2030-06-01"
    assert result["computed_values"]["expiry_date"] == "2030-06-04"
    assert (
        calc.process_extraction(
            {**facts, "recurring_future_payments": True}, params("limitation_rules", "2026-11-26")
        )[0]["status"]
        == "missing_input"
    )


async def test_parameter_loader_uses_explicit_date_and_records_unreviewed_snapshot():
    class Source:
        def __init__(self):
            self.calls = []

        async def json(self, key, as_of):
            self.calls.append((key, as_of))
            return params()[key]

    source = Source()
    overrides, snapshot = await calc.load_parameters(
        {"calculation_type": "wage_attachment", "as_of": "2026-07-01"}, source
    )
    assert source.calls == [("attachment_monthly", date(2026, 7, 1))]
    assert snapshot["parameters"]["attachment_monthly"]["review_status"] == "proposed"
    assert overrides["attachment_monthly"]["value"]["base_cents"] == 158740
    await calc.load_parameters({"calculation_type": "wage_attachment"}, source)
    assert len(source.calls) == 1


@pytest.mark.parametrize(
    "principal,fee",
    [
        (1, 3150),
        (5000, 3150),
        (5001, 5150),
        (50000, 5150),
        (50001, 9300),
        (200000, 17600),
        (200001, 23550),
    ],
)
def test_rvg_band_boundaries(principal, fee):
    p = params("collection_rvg", "2026-11-26")["collection_rvg"]["value"]
    result = calc._collection(
        {
            "principal_cents": principal,
            "undisputed": True,
            "titled": False,
            "default_confirmed": True,
            "transition_confirmed": True,
            "duplicate_fees": False,
            "vat_recoverable": False,
            "fee_case": "normal",
        },
        p,
    )
    assert result["business_fee_cents"] == (fee * 9 + 5) // 10


@pytest.mark.parametrize("principal", [None, True, -1, 0, 1.0])
def test_collection_rejects_missing_boolean_and_negative_amounts(principal):
    facts = {
        "calculation_type": "collection_costs",
        "as_of": "2026-11-26",
        "principal_cents": principal,
        "undisputed": True,
        "titled": False,
        "default_confirmed": True,
        "transition_confirmed": True,
        "duplicate_fees": False,
        "vat_recoverable": False,
        "fee_case": "normal",
    }
    assert (
        calc.process_extraction(facts, params("collection_rvg", "2026-11-26"))[0]["status"]
        == "missing_input"
    )


def test_law_snapshot_is_not_artificially_expired_after_retrieval_day():
    facts = {
        "calculation_type": "collection_costs",
        "as_of": "2026-11-27",
        "principal_cents": 50000,
        "undisputed": True,
        "titled": False,
        "default_confirmed": True,
        "transition_confirmed": True,
        "duplicate_fees": False,
        "vat_recoverable": False,
        "fee_case": "normal",
    }
    assert (
        calc.process_extraction(facts, params("collection_rvg", "2026-11-27"))[0][
            "computed_values"
        ]["amount_cents"]
        == 5562
    )


def test_qualified_recoverable_vat_uses_sourced_rate():
    p = params("collection_rvg", "2026-11-26")["collection_rvg"]["value"]
    facts = {
        "principal_cents": 50000,
        "undisputed": True,
        "titled": False,
        "default_confirmed": True,
        "transition_confirmed": True,
        "duplicate_fees": False,
        "vat_recoverable": True,
        "fee_case": "normal",
    }
    assert calc._collection(facts, p)["amount_cents"] == 6619


def test_parameter_yaml_loads_through_real_module_contract():
    from app.modules.parameters import load_parameter_rows
    from app.modules.registry import discover_modules

    manifest = discover_modules(ROOT / "modules")["schuldnerrecht"]
    rows = load_parameter_rows(manifest)
    assert len(rows) == 4
    assert all(isinstance(row.valid_from, date) for row in rows)
    assert all(row.valid_to is None or isinstance(row.valid_to, date) for row in rows)
    assert {row.key for row in rows} == {"attachment_monthly", "limitation_rules", "collection_rvg"}


@pytest.mark.parametrize("stated,direction", [(158000, "zulasten"), (160000, "zugunsten")])
def test_p_account_discrepancy_direction_tracks_protected_allowance(stated, direction):
    result = run(
        "p_account",
        dependants=0,
        dependants_confirmed=True,
        special_order=False,
        other_increases=False,
        stated_amount_cents=stated,
    )
    assert result["computed_values"]["amount_cents"] == 159000
    assert result["status"] == "provisional"
    assert result["discrepancy_found"] is True
    assert result["discrepancy_amount_eur"] == 10
    assert result["discrepancy_direction"] == direction
