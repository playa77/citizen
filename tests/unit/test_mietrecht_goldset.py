"""Module-level synthetic evidence and explicit tenancy dispatch contracts."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2] / "modules/mietrecht"


def test_synthetic_tenancy_cases_are_auditable():
    from eval.goldset_loader import GoldsetDocument, audit_goldset

    doc = GoldsetDocument(**yaml.safe_load((ROOT / "goldset/goldset-v0.2.0.yaml").read_text()))
    assert doc.goldset.provenance == "synthetic"
    assert len(doc.cases) >= 15
    assert not audit_goldset(doc)
    assert all(case.expected.legal_issues and case.negative_controls for case in doc.cases)
    dossier = yaml.safe_load((ROOT / "goldset/dossier-goldset-v1.0.0.yaml").read_text())
    assert {case.id for case in doc.cases} == {case["id"] for case in dossier["cases"]}


def test_tenancy_uses_dedicated_profile_and_expanded_sources():
    from app.services.corpus import _infer_legal_area_for_bgb
    from app.services.corpus_readiness import AREA_TO_SOURCE_TYPES
    from app.services.prompts import get_prompts

    prompts = get_prompts(["mietrecht"])
    assert "Wohnraummiete" in prompts["classification"]
    assert set(AREA_TO_SOURCE_TYPES["mietrecht"]) == {
        "bgb",
        "zpo",
        "betrkv",
        "heizkostenv",
        "landes_mietrecht",
    }
    assert _infer_legal_area_for_bgb("BGB > § 558") == "mietrecht"
    assert _infer_legal_area_for_bgb("BGB > § 580a") == "mietrecht"
    assert _infer_legal_area_for_bgb("BGB > § 581") is None


def test_actual_intake_schema_accepts_explicit_fractional_area():
    from jsonschema import Draft202012Validator, FormatChecker

    schema = yaml.safe_load((ROOT / "intake-schema.yaml").read_text())
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    assert not list(
        validator.iter_errors(
            {"own_matter_confirmed": True, "tenant_units": 55.5, "total_units": 555.0}
        )
    )
    assert list(validator.iter_errors({"own_matter_confirmed": False}))


def test_schema_valid_heating_input_reaches_real_calculator():
    import importlib.util

    from jsonschema import Draft202012Validator

    facts = {
        "own_matter_confirmed": True,
        "calculation_type": "operating_costs",
        "as_of": "2026-11-26",
        "applicability_confirmed": True,
        "cost_category": "heating",
        "total_cost_cents": 100000,
        "tenant_units": 55.5,
        "total_units": 555.0,
        "tenant_consumption_units": 20.5,
        "total_consumption_units": 102.5,
        "consumption_share_percent": 70,
        "heating_70_required": True,
        "heating_exceptions": False,
        "advance_paid_cents": 0,
        "allocation_confirmed": True,
        "contract_allocation_confirmed": True,
        "nonallocable_costs_present": False,
    }
    schema = yaml.safe_load((ROOT / "intake-schema.yaml").read_text())
    assert not list(Draft202012Validator(schema).iter_errors(facts))
    spec = importlib.util.spec_from_file_location(
        "tenancy_schema_contract", ROOT / "calculators.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    params = {
        row["key"]: {**row, "value": row["value_json"]}
        for path in (ROOT / "parameters").glob("*.yaml")
        for row in yaml.safe_load(path.read_text())["parameters"]
    }
    result = module.process_extraction(facts, params)[0]
    assert result["status"] == "provisional"
    assert result["computed_values"]["amount_cents"] == 17000


def test_nullable_form_qualifications_remain_missing_not_confirmed():
    from jsonschema import Draft202012Validator

    from app.dossier.deadlines import ModuleSpecs, compute_deadlines, validate_facts
    from app.fristen.specs import load_specs

    schema = yaml.safe_load((ROOT / "intake-schema.yaml").read_text())
    supplied = {
        "own_matter_confirmed": True,
        "document_type": "kuendigung",
        "ereignis_datum": "2027-03-31",
        "feiertagskalender_bestaetigt": None,
        "qualifikationen": {
            "ordentliche_kuendigung": None,
            "widerspruchshinweis_rechtzeitig": True,
        },
    }
    assert not list(Draft202012Validator(schema).iter_errors(supplied))
    facts = validate_facts(
        {key: value for key, value in supplied.items() if key != "own_matter_confirmed"}
    )
    rule = next(s for s in load_specs(ROOT / "fristen.yaml") if s.id == "miet_sozialwiderspruch")
    item = compute_deadlines([ModuleSpecs("mietrecht", (rule,))], facts, [])["items"][0]
    assert item["status"] == "missing_input"
    assert "ordentliche_kuendigung" not in facts["qualifikationen"]
    assert "feiertagskalender_bestaetigt" not in facts
