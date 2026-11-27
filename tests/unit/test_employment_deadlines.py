"""Employment dates must be confirmed separately from receipt and letter dates."""

from datetime import date
from pathlib import Path

import pytest

from app.dossier.deadlines import ModuleSpecs, compute_deadlines, validate_facts
from app.fristen.evaluator import FristInput, evaluate_spec
from app.fristen.specs import load_specs


def knowledge_rule(tmp_path):
    path = tmp_path / "knowledge.yaml"
    path.write_text("""- id: knowledge
  label_de: Melden
  trigger: kenntnis
  duration: {days: 3}
  basis: § 38 SGB III
  severity: critical
  applies_when: {document_type: beendigung}
""")
    return load_specs(path)[0]


def test_confirmed_knowledge_is_independent_from_receipt(tmp_path):
    rule = knowledge_rule(tmp_path)
    facts = validate_facts(
        {
            "kenntnis_datum": "2026-11-02",
            "zugang_tatsaechlich": "2026-10-01",
            "document_type": "beendigung",
        }
    )
    item = compute_deadlines([ModuleSpecs("employment", (rule,))], facts, [])["items"][0]
    assert item["frist_ende"] == "2026-11-05"
    assert item["bekanntgabe"] == "2026-11-02"
    assert item["inputs"]["kenntnis_datum"] == "2026-11-02"
    assert item["assumptions"] == []


@pytest.mark.parametrize("key", ["zugang_tatsaechlich", "ereignis_datum", "bescheid_datum"])
def test_knowledge_never_borrows_other_dates(tmp_path, key):
    rule = knowledge_rule(tmp_path)
    item = compute_deadlines(
        [ModuleSpecs("employment", (rule,))], {key: "2026-11-02", "document_type": "beendigung"}, []
    )["items"][0]
    assert item["status"] == "missing_input"
    assert item["frist_ende"] is None


def test_engine_knowledge_requires_explicit_date(tmp_path):
    rule = knowledge_rule(tmp_path)
    with pytest.raises(ValueError, match="confirmed"):
        evaluate_spec(rule, FristInput(bescheid_datum=date(2026, 11, 2)))
    result = evaluate_spec(
        rule,
        FristInput(
            bescheid_datum=date(2000, 1, 1),
            kenntnis_datum=date(2026, 11, 2),
            document_type="beendigung",
        ),
    )
    assert result.frist_ende == date(2026, 11, 5)
    assert "Kenntnis" in result.explanation_de


def test_invalid_knowledge_date_rejected():
    with pytest.raises(ValueError, match="kenntnis_datum"):
        validate_facts({"kenntnis_datum": "2026-02-30"})


@pytest.mark.parametrize("document_type", ["kuendigung", "arbeitsvertrag", "aufhebungsvertrag"])
def test_registration_reminder_is_not_suppressed_by_document_label(document_type):
    rules = load_specs(Path(__file__).resolve().parents[2] / "modules/arbeitsrecht/fristen.yaml")
    short = next(rule for rule in rules if rule.id == "ar_arbeitsuchend_kurz")
    item = compute_deadlines(
        [ModuleSpecs("arbeitsrecht", (short,))],
        {
            "document_type": document_type,
            "kenntnis_datum": "2026-11-02",
            "bundesland": "NW",
            "feiertagskalender_bestaetigt": True,
            "qualifikationen": {"meldepflicht_bestaetigt": True, "weniger_als_drei_monate": True},
        },
        [],
    )["items"][0]
    assert item["status"] == "computed"
    assert item["frist_ende"] == "2026-11-05"


def test_dismissal_keeps_both_action_and_registration_deadlines():
    rules = load_specs(Path(__file__).resolve().parents[2] / "modules/arbeitsrecht/fristen.yaml")
    section = compute_deadlines(
        [ModuleSpecs("arbeitsrecht", tuple(rules))],
        {
            "document_type": "kuendigung",
            "zugang_tatsaechlich": "2026-11-02",
            "kenntnis_datum": "2026-11-03",
            "bundesland": "NW",
            "feiertagskalender_bestaetigt": True,
            "qualifikationen": {
                "schriftliche_arbeitgeberkuendigung": True,
                "kein_behoerdlicher_zustimmungsvorbehalt": True,
                "meldepflicht_bestaetigt": True,
                "weniger_als_drei_monate": True,
            },
        },
        [],
    )
    computed = {
        item["spec_id"]: item["frist_ende"]
        for item in section["items"]
        if item["status"] == "computed"
    }
    assert computed == {"ar_kuendigungsschutz": "2026-11-23", "ar_arbeitsuchend_kurz": "2026-11-06"}


def test_unqualified_event_without_document_selector_is_rejected(tmp_path):
    path = tmp_path / "unsafe.yaml"
    path.write_text(
        "- id: unsafe\n  label_de: Unsafe\n  trigger: ereignis\n"
        "  duration: {days: 3}\n  severity: high\n  basis: Test\n"
    )
    with pytest.raises(ValueError, match="selector or qualifications"):
        load_specs(path)
