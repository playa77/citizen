"""Fail closed on unsupported residence regimes; arithmetic never establishes status."""

import importlib.util
from pathlib import Path

import pytest
import yaml

ROOT = Path("modules/aufenthaltsrecht")


def calculate(facts, parameters=None):
    path = ROOT / "calculators.py"
    assert path.exists(), "Residence calculator missing"
    spec = importlib.util.spec_from_file_location("residence_test_calc", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    params_path = ROOT / "parameters/residence.yaml"
    assert params_path.exists()
    row = yaml.safe_load(params_path.read_text())["parameters"][0]
    override = {
        "residence_rules": {
            "value": row["value_json"],
            "valid_from": str(row["valid_from"]),
            "valid_to": str(row["valid_to"]),
        }
    }
    result = mod.process_extraction(facts, override if parameters is None else parameters)[0]
    return result


def common(kind):
    return dict(
        calculation_type=kind,
        as_of="2026-11-27",
        applicability_confirmed=True,
        current_regime_confirmed=True,
    )


def test_title_expiry_requires_actual_received_application_and_no_status_decision():
    f = common("title_expiry") | dict(
        title_expires_on="2026-11-30",
        application_received_on="2026-11-27",
        title_and_expiry_confirmed=True,
        application_receipt_confirmed=True,
        section81_4_regime_confirmed=True,
        no_schengen_visa_confirmed=True,
        no_authority_decision_confirmed=True,
    )
    r = calculate(f)
    v = r["computed_values"]["deterministic_result"]
    assert r["status"] == "provisional"
    assert v["days_until_expiry"] == 3
    assert v["application_before_expiry"] is True
    assert "status_granted" not in v
    f["application_received_on"] = "2026-12-01"
    f["as_of"] = "2026-12-02"
    assert calculate(f)["status"] == "unavailable"
    f["application_received_on"] = "2026-11-27"
    f.pop("no_schengen_visa_confirmed")
    assert calculate(f)["status"] == "unavailable"


def test_future_application_is_not_actual_receipt():
    f = common("title_expiry") | dict(
        title_expires_on="2026-11-30",
        application_received_on="2026-11-28",
        title_and_expiry_confirmed=True,
        application_receipt_confirmed=True,
        section81_4_regime_confirmed=True,
        no_schengen_visa_confirmed=True,
        no_authority_decision_confirmed=True,
    )
    assert calculate(f)["status"] == "unavailable"


@pytest.mark.parametrize(
    "start,anniversary",
    [("2021-11-27", "2026-11-27"), ("2021-11-28", "2026-11-28"), ("2020-02-29", "2025-02-28")],
)
def test_five_year_residence_arithmetic_not_naturalisation_eligibility(start, anniversary):
    f = common("residence_period") | dict(
        lawful_residence_started_on=start,
        continuous_lawful_ordinary_residence_confirmed=True,
        no_credit_or_interruption_confirmed=True,
        standard_section10_regime_confirmed=True,
    )
    r = calculate(f)
    assert r["status"] == "provisional"
    v = r["computed_values"]["deterministic_result"]
    assert v["five_year_anniversary"] == anniversary
    assert v["period_reached"] is (anniversary <= "2026-11-27")
    assert "eligible" not in v
    for key in (
        "continuous_lawful_ordinary_residence_confirmed",
        "no_credit_or_interruption_confirmed",
        "standard_section10_regime_confirmed",
    ):
        missing = f.copy()
        missing.pop(key)
        assert calculate(missing)["status"] == "unavailable"


def test_livelihood_only_uses_confirmed_cent_inputs_and_includes_insurance():
    f = common("livelihood_budget") | dict(
        eligible_income_cents=150001,
        confirmed_need_cents=120000,
        insurance_cost_cents=15000,
        need_and_income_basis_confirmed=True,
        insurance_coverage_confirmed=True,
        complete_household_confirmed=True,
        no_special_livelihood_regime_confirmed=True,
    )
    r = calculate(f)
    assert r["status"] == "provisional"
    v = r["computed_values"]["deterministic_result"]
    assert r["correct_calculation"] == "150.01 EUR"
    assert v["budget_balance_cents"] == 15001
    assert v["total_need_cents"] == 135000
    assert "secured" not in v and "eligible" not in v
    for key in ("eligible_income_cents", "confirmed_need_cents", "insurance_cost_cents"):
        for value in (True, -1, 1.1, "15000", None):
            bad = f | {key: value}
            assert calculate(bad)["status"] == "unavailable"
    f["eligible_income_cents"] = 1
    assert (
        calculate(f)["computed_values"]["deterministic_result"]["budget_balance_cents"] == -134999
    )


def test_no_parameters_or_expired_regime_never_uses_defaults():
    f = common("residence_period") | dict(
        lawful_residence_started_on="2021-11-27",
        continuous_lawful_ordinary_residence_confirmed=True,
        no_credit_or_interruption_confirmed=True,
        standard_section10_regime_confirmed=True,
    )
    assert calculate(f, {})["status"] == "unavailable"
    assert calculate(f | {"as_of": "2027-01-01"})["status"] == "unavailable"
    assert calculate(f | {"current_regime_confirmed": "true"})["status"] == "unavailable"
    assert calculate(f | {"lawful_residence_started_on": "2027-01-01"})["status"] == "unavailable"


async def test_model_only_confirmations_cannot_produce_residence_arithmetic(monkeypatch):
    import json
    from unittest.mock import AsyncMock
    from app.services.calculation import _llm_extract

    path = ROOT / "calculators.py"
    spec = importlib.util.spec_from_file_location("residence_evidence_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    hallucinated = common("residence_period") | {
        "lawful_residence_started_on": "2021-11-27",
        "continuous_lawful_ordinary_residence_confirmed": True,
        "no_credit_or_interruption_confirmed": True,
        "standard_section10_regime_confirmed": True,
        "persecution_story": "PRIVATE MODEL INVENTION",
    }
    client = AsyncMock()
    client.chat_completion.return_value = json.dumps(hallucinated)
    extracted = await _llm_extract(
        client,
        "## DOKUMENT\nNur eine allgemeine Beratungsfrage.",
        model="offline-mock",
        timeout=1,
        calculator=mod.RESIDENCE_CALCULATOR,
    )
    assert "persecution_story" not in mod.RESIDENCE_CALCULATOR.summarise_extraction(extracted)
    assert calculate(extracted)["status"] == "unavailable"


def test_only_explicit_minimised_source_block_can_supply_qualified_inputs():
    import json

    spec = importlib.util.spec_from_file_location("residence_bound_inputs", ROOT / "calculators.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    f = common("residence_period") | {
        "own_matter_confirmed": True,
        "lawful_residence_started_on": "2021-11-27",
        "continuous_lawful_ordinary_residence_confirmed": True,
        "no_credit_or_interruption_confirmed": True,
        "standard_section10_regime_confirmed": True,
    }
    extraction = {"calculation_type": "livelihood_budget", "persecution_story": "PRIVATE"}
    warnings = mod.cross_check_extraction(extraction, mod.EVIDENCE_MARKER + " " + json.dumps(f))
    assert warnings == [] and extraction == f
    assert (
        calculate(extraction)["computed_values"]["deterministic_result"]["period_reached"] is True
    )
    for bad in (
        f | {"religion": "PRIVATE"},
        f | {"own_matter_confirmed": False},
        f | {"current_regime_confirmed": "true"},
    ):
        extraction = {"calculation_type": "residence_period"}
        assert mod.cross_check_extraction(extraction, mod.EVIDENCE_MARKER + " " + json.dumps(bad))
        assert calculate(extraction)["status"] == "unavailable"


async def test_parameter_loader_uses_only_requested_dated_module_source():
    from unittest.mock import AsyncMock

    spec = importlib.util.spec_from_file_location(
        "residence_parameter_test", ROOT / "calculators.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    source = AsyncMock()
    source.json.return_value = {
        "value": {"standard_residence_years": 5},
        "valid_from": "2026-11-27",
        "valid_to": "2026-12-31",
        "review_status": "proposed",
    }
    overrides, snapshot = await mod.load_parameters(common("residence_period"), source)
    from datetime import date

    source.json.assert_awaited_once_with("residence_rules", date(2026, 11, 27))
    assert overrides["residence_rules"]["value"]["standard_residence_years"] == 5
    assert snapshot["parameter_versions"] == ["residence_rules@2026-11-27"]
    source.reset_mock()
    assert await mod.load_parameters({"calculation_type": "none"}, source) == ({}, None)
    assert not source.json.called
