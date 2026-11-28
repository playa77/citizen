"""Synthetic contract checks for bounded tax arithmetic."""

import importlib.util
import json
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


def module():
    spec = importlib.util.spec_from_file_location(
        "tax_calculators", ROOT / "modules/steuerrecht/calculators.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def parameters():
    row = yaml.safe_load((ROOT / "modules/steuerrecht/parameters/tax.yaml").read_text())[
        "parameters"
    ][0]
    return {"tax_rules": {**row, "value": row["value_json"]}}


def facts(**changes):
    return {
        "own_matter_confirmed": True,
        "calculation_type": "income_tax",
        "tax_year": 2026,
        "applicability_confirmed": True,
        "current_regime_confirmed": True,
        "taxable_income_confirmed": True,
        "no_special_tariff_confirmed": True,
        "taxable_income_cents": 1234800,
        "tariff": "basic",
        **changes,
    }


@pytest.mark.parametrize(
    ("income", "tax"),
    [
        (0, 0),
        (1234899, 0),
        (1234900, 0),
        (1779900, 103400),
        (1780000, 103500),
        (6987800, 1821300),
        (6987900, 1821300),
        (27782500, 10555000),
        (27782600, 10555100),
    ],
)
def test_statutory_boundaries(income, tax):
    result = module().process_extraction(facts(taxable_income_cents=income), parameters())[0]
    assert result["computed_values"]["tax_cents"] == tax
    assert result["status"] == "provisional"


def test_splitting_rounds_half_income_then_tax_before_doubling():
    result = module().process_extraction(
        facts(taxable_income_cents=3559999, tariff="splitting", joint_assessment_confirmed=True),
        parameters(),
    )[0]
    assert result["computed_values"]["tax_cents"] == 206800


@pytest.mark.parametrize(
    "change",
    [
        {"tax_year": 2025},
        {"no_special_tariff_confirmed": False},
        {"tariff": "splitting"},
        {"taxable_income_cents": True},
        {"taxable_income_cents": -1},
    ],
)
def test_unsupported_or_unqualified_is_unavailable(change):
    assert module().process_extraction(facts(**change), parameters())[0]["status"] == "unavailable"


@pytest.mark.parametrize(
    ("kind", "income", "joint", "expected"),
    [
        ("employee", 200000, False, 123000),
        ("employee", 5000, False, 5000),
        ("pensioner", 200000, False, 10200),
        ("pensioner", 100, False, 100),
        ("saver", 500000, False, 100000),
        ("saver", 500000, True, 200000),
    ],
)
def test_allowance_is_capped_by_qualified_income(kind, income, joint, expected):
    result = module().process_extraction(
        facts(
            calculation_type="allowance",
            allowance_type=kind,
            eligible_income_cents=income,
            joint_assessment_confirmed=joint,
            allowance_basis_confirmed=True,
            no_higher_expenses_confirmed=True,
        ),
        parameters(),
    )[0]
    assert result["computed_values"]["allowance_cents"] == expected


def test_comparison_exact_signed_cent_difference():
    result = module().process_extraction(
        facts(
            calculation_type="assessment_difference",
            assessed_cents=10001,
            declared_cents=10002,
            comparison_basis_confirmed=True,
        ),
        parameters(),
    )[0]
    assert result["computed_values"]["difference_cents"] == -1


@pytest.mark.parametrize(
    "payload",
    [
        None,
        {"tax_id": "not permitted"},
        {"tax_year": "2026"},
        {"taxable_income_cents": True},
        {"tariff": ["basic"]},
    ],
)
def test_cross_check_rejects_model_confirmation_and_invalid_explicit_payload(payload):
    mod = module()
    extracted = facts()
    document = (
        "ordinary prose" if payload is None else mod.EVIDENCE_MARKER + json.dumps(facts(**payload))
    )
    assert mod.cross_check_extraction(extracted, document)
    assert mod.process_extraction(extracted, parameters())[0]["status"] == "unavailable"


def test_explicit_source_replaces_model_and_summary_minimises():
    mod = module()
    extracted = {"tax_id": "private", "taxable_income_cents": 999999999}
    assert mod.cross_check_extraction(extracted, mod.EVIDENCE_MARKER + json.dumps(facts())) == []
    assert extracted == facts()
    assert "taxable_income_cents" not in mod.summarise_extraction(extracted)


def test_repeated_or_duplicate_json_fields_rejected():
    mod = module()
    for document in [
        mod.EVIDENCE_MARKER * 2,
        mod.EVIDENCE_MARKER + '{"tax_year":2025,"tax_year":2026}',
    ]:
        assert mod.cross_check_extraction(facts(), document)


def test_missing_parameters_never_uses_fallback_constants():
    assert module().process_extraction(facts(), {})[0]["status"] == "unavailable"


def test_summary_drops_unrecognised_values_even_on_allowlisted_keys():
    assert module().summarise_extraction({"tariff": "private narrative", "tax_year": True}) == {}


async def test_load_parameters_preserves_version_provenance():
    class Source:
        async def json(self, key, day):
            assert key == "tax_rules"
            assert day.isoformat() == "2026-01-01"
            return parameters()["tax_rules"]

    result, provenance = await module().load_parameters(facts(), Source())
    assert result["tax_rules"]["value"]["tax_year"] == 2026
    assert provenance["parameter_versions"] == ["tax_rules@2026-01-01"]
    assert await module().load_parameters(facts(tax_year=2025), Source()) == (
        {},
        {"missing_input": "supported_tax_year", "parameter_versions": []},
    )


def filing_facts(**changes):
    return facts(
        calculation_type="filing_deadline",
        bundesland="BE",
        mandatory_filing_confirmed=True,
        unadvised_confirmed=True,
        no_special_filing_regime_confirmed=True,
        no_individual_notice_or_extension_confirmed=True,
        filing_calendar_confirmed=True,
        **changes,
    )


def test_precomputed_ordinary_2026_filing_deadline():
    result = module().process_extraction(filing_facts(), parameters())[0]
    assert result["status"] == "provisional"
    assert result["computed_values"]["filing_deadline"] == "2027-08-02"
    assert result["computed_values"]["nominal_filing_deadline"] == "2027-07-31"
    assert "tax_cents" not in result["computed_values"]


@pytest.mark.parametrize(
    "key",
    [
        "mandatory_filing_confirmed",
        "unadvised_confirmed",
        "no_special_filing_regime_confirmed",
        "no_individual_notice_or_extension_confirmed",
        "filing_calendar_confirmed",
    ],
)
def test_filing_qualifications_required(key):
    f = filing_facts()
    f[key] = False
    assert module().process_extraction(f, parameters())[0]["status"] == "unavailable"
    del f[key]
    assert module().process_extraction(f, parameters())[0]["status"] == "unavailable"


@pytest.mark.parametrize("land", [None, "", "DE", True, ["BE"]])
def test_filing_requires_explicit_valid_state(land):
    f = filing_facts()
    f["bundesland"] = land
    assert module().process_extraction(f, parameters())[0]["status"] == "unavailable"


def test_filing_rejects_unsupported_year_and_accepts_explicit_source_only():
    mod = module()
    f = filing_facts()
    f["tax_year"] = 2025
    assert mod.process_extraction(f, parameters())[0]["status"] == "unavailable"
    extracted = {"calculation_type": "filing_deadline"}
    assert (
        mod.cross_check_extraction(extracted, mod.EVIDENCE_MARKER + json.dumps(filing_facts()))
        == []
    )
    assert (
        mod.process_extraction(extracted, parameters())[0]["computed_values"]["filing_deadline"]
        == "2027-08-02"
    )


@pytest.mark.parametrize(
    "assessed,declared,direction,count",
    [
        (12345, 10000, "zulasten", 1),
        (10000, 12345, "zugunsten", 1),
        (10000, 10000, "keine", 0),
    ],
)
def test_assessment_difference_reaches_harness_summary(assessed, declared, direction, count):
    from app.services.calculation import _build_overall_assessment

    entries = module().process_extraction(
        facts(
            calculation_type="assessment_difference",
            comparison_basis_confirmed=True,
            assessed_cents=assessed,
            declared_cents=declared,
        ),
        parameters(),
    )
    assert entries[0]["computed_values"]["difference_cents"] == assessed - declared
    result = _build_overall_assessment(entries, None)
    assert result["total_discrepancies"] == count
    assert result["direction"] == direction
    assert result["total_amount_eur"] == abs(assessed - declared) / 100
