"""Employment content keeps urgent review and evidence qualifications visible."""

from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

from app.dossier.deadlines import ModuleSpecs, compute_deadlines
from app.fristen.specs import load_specs

ROOT = Path(__file__).resolve().parents[2] / "modules/arbeitsrecht"


def _specs():
    return [ModuleSpecs("arbeitsrecht", tuple(load_specs(ROOT / "fristen.yaml")))]


def test_unknown_receipt_or_consent_keeps_critical_banner():
    section = compute_deadlines(_specs(), {"document_type": "kuendigung"}, [])
    item = next(i for i in section["items"] if i["spec_id"] == "ar_kuendigungsschutz")
    assert item["status"] == "missing_input"
    assert item["severity"] == "critical"
    assert item["frist_ende"] is None


@pytest.mark.parametrize("case_id", ["AR-003", "AR-004"])
def test_small_employer_and_short_service_do_not_skip_dismissal(case_id):
    cases = yaml.safe_load((ROOT / "goldset/dossier-goldset-v1.0.0.yaml").read_text())["cases"]
    case = next(c for c in cases if c["id"] == case_id)
    section = compute_deadlines(_specs(), case["facts"], [])
    item = next(i for i in section["items"] if i["spec_id"] == "ar_kuendigungsschutz")
    assert item["severity"] == "critical"
    assert item["status"] == "computed"
    assert item["frist_ende"] == "2026-11-23"


def test_long_registration_requires_qualified_workday_target():
    section = compute_deadlines(
        _specs(),
        {
            "document_type": "beendigung",
            "ereignis_datum": "2027-05-31",
            "qualifikationen": {"meldepflicht_bestaetigt": True, "mindestens_drei_monate": True},
        },
        [],
    )
    item = next(i for i in section["items"] if i["spec_id"] == "ar_arbeitsuchend_lang")
    assert item["status"] == "missing_input"
    assert item["frist_ende"] is None


def test_all_templates_keep_factual_guards_and_no_automatic_filing():
    templates = yaml.safe_load((ROOT / "documents/templates.yaml").read_text())
    assert set(templates["templates"]) == {
        "pruefhinweise",
        "lohn_geltendmachung",
        "zeugnisberichtigung",
        "klage_checkliste",
    }
    for entry in templates["templates"].values():
        text = "\n".join(part["text"] for part in entry["parts"])
        assert "[BITTE PRÜFEN:" in text
        assert "Entwurf" in text
        assert "Keine automatische Versendung oder gerichtliche Einreichung." in text
    wage = str(templates["templates"]["lohn_geltendmachung"])
    assert "jede Stufe und Frist einer wirksamen Ausschlussklausel" in wage
    assert "wahrt nicht automatisch jede Ausschlussfrist" in wage


def test_public_schema_accepts_unknown_and_rejects_invalid_calculator_facts():
    schema = yaml.safe_load((ROOT / "intake-schema.yaml").read_text())
    validator = Draft202012Validator(schema)
    facts = {
        "own_matter_confirmed": True,
        "calculation_type": "minimum_wage",
        "as_of": "2026-11-27",
        "applicability_confirmed": None,
        "milog_coverage_confirmed": None,
        "remuneration_basis_confirmed": None,
        "working_minutes": 60,
        "eligible_pay_cents": 1000,
        "period_start": "2026-11-27",
        "period_end": "2026-11-27",
    }
    assert not list(validator.iter_errors(facts))
    for key, value in [
        ("working_minutes", 0),
        ("eligible_pay_cents", -1),
        ("eligible_pay_cents", 10.5),
        ("milog_coverage_confirmed", "yes"),
    ]:
        assert list(validator.iter_errors({**facts, key: value}))
    assert list(validator.iter_errors({"own_matter_confirmed": False}))
    assert list(validator.iter_errors({"own_matter_confirmed": True, "working_days_per_week": 7}))


def test_no_generic_clause_duration_or_validity_rule():
    specs = yaml.safe_load((ROOT / "fristen.yaml").read_text())
    assert {s["id"] for s in specs} == {
        "ar_kuendigungsschutz",
        "ar_arbeitsuchend_kurz",
        "ar_arbeitsuchend_lang",
    }
    profile = yaml.safe_load((ROOT / "prompts/profile.yaml").read_text())
    assert any("keine pauschale Wirksamkeit" in term for term in profile["issue_terms"])
