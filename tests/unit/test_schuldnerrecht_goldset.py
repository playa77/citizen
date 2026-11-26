"""Offline structural and deterministic contracts for synthetic debt fixtures."""

from datetime import date
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[2] / "modules/schuldnerrecht"


def load(name):
    return yaml.safe_load((ROOT / name).read_text(encoding="utf-8"))


def test_base_and_dossier_cases_are_complete_and_synthetic():
    from eval.goldset_loader import GoldsetDocument, audit_goldset

    base = load("goldset/goldset-v0.2.0.yaml")
    parsed = GoldsetDocument(**base)
    assert parsed.goldset.provenance == "synthetic"
    assert not audit_goldset(parsed)
    assert len(parsed.cases) >= 15
    ids = {case.id for case in parsed.cases}
    assert len(ids) == parsed.goldset.case_count
    assert all(case.expected.legal_issues and case.negative_controls for case in parsed.cases)
    dossier = load("goldset/dossier-goldset-v1.0.0.yaml")
    assert {case["id"] for case in dossier["cases"]} == ids
    for case in dossier["cases"]:
        assert len(case["expected"]["checklist"]) >= 4
        assert case["expected"]["chronology"] == [{"date": "2026-11-02", "kind": "document_date"}]


def test_intake_schema_keeps_legal_confirmation_explicit():
    schema = load("intake-schema.yaml")
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    valid = {
        "own_matter_confirmed": True,
        "synthetic_data_confirmed": True,
        "document_type": "mahnbescheid",
        "zustellungsart": "inland",
        "zustellung_tatsaechlich": "2026-11-02",
        "service_date_confirmed": True,
    }
    assert not list(validator.iter_errors(valid))
    for patch in (
        {"own_matter_confirmed": False},
        {"zustellung_tatsaechlich": "2026-02-30"},
        {"zustellungsart": "postal_guess"},
        {"service_date_confirmed": False},
    ):
        assert list(validator.iter_errors(valid | patch)), patch
    assert list(validator.iter_errors({"own_matter_confirmed": False}))


def test_plain_goldset_covers_court_service_failures_and_findings():
    cases = load("goldset/plain-v1.0.0.yaml")["cases"]
    findings = {c["expect"].get("category") for c in cases if c["kind"] == "finding"}
    assert findings == {
        "forderung_pruefen",
        "kosten_pruefen",
        "frist_pruefen",
        "beratung_erforderlich",
        "einordnung_offen",
    }
    deadlines = [c for c in cases if c["kind"] == "deadline"]
    for spec in ("widerspruch_mahnbescheid", "einspruch_vollstreckungsbescheid"):
        relevant = [c for c in deadlines if c["spec_id"] == spec]
        assert {c["expect"]["status"] for c in relevant} >= {
            "computed",
            "missing_input",
            "not_applicable",
        }
        for mode in ("ausland", "oeffentlich"):
            assert any(
                c["facts"].get("zustellungsart") == mode
                and c["expect"]["status"] == "missing_input"
                for c in relevant
            )


@pytest.mark.parametrize("case", range(6))
def test_arithmetic_fixtures_use_module_engine(case):
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "debt_fixture_calculator", ROOT / "calculators.py"
    )
    calculator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(calculator)
    fixture = load("goldset/arithmetic-v1.0.0.yaml")["cases"][case]
    extraction = fixture["extraction"]
    rows = load("parameters/attachment.yaml")["parameters"]
    as_of = date.fromisoformat(extraction["as_of"])
    row = next(row for row in rows if row["valid_from"] <= as_of <= row["valid_to"])
    parameters = {
        row["key"]: {
            "value": row["value_json"],
            "valid_from": row["valid_from"],
            "valid_to": row["valid_to"],
        }
    }
    result = calculator.process_extraction(extraction, parameters)[0]
    assert result["status"] == fixture["expect"]["status"]
    for key, expected in fixture["expect"].get("computed_values", {}).items():
        assert result["computed_values"][key] == expected
