"""Receipt/event rules must use their real trigger and calendar semantics."""

from datetime import date
from pathlib import Path

import pytest

from app.dossier.deadlines import ModuleSpecs, compute_deadlines, validate_facts
from app.fristen.evaluator import FristInput, evaluate_spec
from app.fristen.specs import load_specs

ROOT = Path(__file__).resolve().parents[2]


def spec(tmp_path, *, trigger="zugang", months=2, anchor="month_end", required=""):
    path = tmp_path / "rule.yaml"
    path.write_text(f"""- id: tenant_response
  label_de: Antwort
  trigger: {trigger}
  duration: {{months: {months}}}
  anchor: {anchor}
  basis: Testbasis
  severity: critical
  applies_when: {{document_type: notice}}
{required}""")
    return load_specs(path)[0]


@pytest.mark.parametrize(
    ("received", "end"),
    [
        ("2026-11-01", "2027-01-31"),
        ("2023-12-31", "2024-02-29"),
        ("2024-12-15", "2025-02-28"),
        ("2026-01-31", "2026-03-31"),
    ],
)
def test_receipt_month_end_uses_calendar_months(tmp_path, received, end):
    rule = spec(tmp_path)
    result = evaluate_spec(
        rule,
        FristInput(
            bescheid_datum=date(2000, 1, 1),
            document_type="notice",
            zugang_tatsaechlich=date.fromisoformat(received),
        ),
    )
    assert result.frist_ende.isoformat() == end
    assert result.bekanntgabe.isoformat() == received
    assert "2000" not in result.explanation_de


def test_billing_objection_is_end_of_twelfth_month(tmp_path):
    rule = spec(tmp_path, months=12)
    item = compute_deadlines(
        [ModuleSpecs("tenancy", (rule,))],
        {"zugang_tatsaechlich": "2026-03-04", "document_type": "notice"},
        [],
    )["items"][0]
    assert item["frist_ende"] == "2027-03-31"
    assert item["assumptions"] == []


@pytest.mark.parametrize(
    "facts",
    [
        {"bescheid_datum": "2026-01-01", "document_type": "notice"},
        {"bekanntgabe_tatsaechlich": "2026-01-01", "document_type": "notice"},
        {"zugang_tatsaechlich": "2026-01-01"},
    ],
)
def test_receipt_cannot_borrow_administrative_or_letter_dates(tmp_path, facts):
    item = compute_deadlines([ModuleSpecs("tenancy", (spec(tmp_path),))], facts, [])["items"][0]
    assert item["status"] == "missing_input"
    assert item["frist_ende"] is None


def test_different_document_is_not_applicable(tmp_path):
    item = compute_deadlines(
        [ModuleSpecs("tenancy", (spec(tmp_path),))],
        {"zugang_tatsaechlich": "2026-01-01", "document_type": "other"},
        [],
    )["items"][0]
    assert item["status"] == "not_applicable"


def test_backward_event_no_forward_weekend_rollover(tmp_path):
    rule = spec(
        tmp_path,
        trigger="ereignis",
        months=-2,
        anchor="same_day",
        required="  requires_confirmed: [notice_explained]",
    )
    facts = validate_facts(
        {
            "ereignis_datum": "2026-11-30",
            "document_type": "notice",
            "qualifikationen": {"notice_explained": True},
        }
    )
    item = compute_deadlines([ModuleSpecs("tenancy", (rule,))], facts, [])["items"][0]
    assert item["status"] == "computed"
    assert item["frist_ende"] == "2026-09-30"
    assert item["rollover_applied"] is False


@pytest.mark.parametrize("qualification", [None, False])
def test_missing_or_false_qualification_refuses_date(tmp_path, qualification):
    rule = spec(
        tmp_path,
        trigger="ereignis",
        months=-2,
        anchor="same_day",
        required="  requires_confirmed: [notice_explained]",
    )
    facts = {"ereignis_datum": "2026-11-30", "document_type": "notice"}
    if qualification is not None:
        facts["qualifikationen"] = {"notice_explained": qualification}
    item = compute_deadlines([ModuleSpecs("tenancy", (rule,))], facts, [])["items"][0]
    assert item["status"] == "missing_input"
    assert item["frist_ende"] is None


@pytest.mark.parametrize(
    "facts",
    [
        {"qualifikationen": {"x": "true"}},
        {"qualifikationen": []},
        {"qualifikationen": {"bad key": True}},
        {"ereignis_datum": "bad"},
        {"feiertagskalender_bestaetigt": "true"},
        {"feiertage_zusaetzlich": ["bad"]},
    ],
)
def test_new_fact_validation_rejects_invalid_types(facts):
    with pytest.raises(ValueError):
        validate_facts(facts)


def test_backward_rollover_spec_rejected(tmp_path):
    with pytest.raises(ValueError, match="backward"):
        spec(
            tmp_path,
            trigger="ereignis",
            months=-2,
            anchor="same_day",
            required="  rollover: bgb_193",
        )


def test_month_anchor_typo_rejected(tmp_path):
    with pytest.raises(ValueError, match="anchor"):
        spec(tmp_path, anchor="month_typo")


@pytest.mark.parametrize("received", ["2023-01-01", "9999-12-30"])
def test_unsupported_civil_date_is_missing_input_not_server_error(received):
    rule = next(
        s for s in load_specs(ROOT / "modules/mietrecht/fristen.yaml") if s.id == "miet_zustimmung"
    )
    item = compute_deadlines(
        [ModuleSpecs("mietrecht", (rule,))],
        {
            "zugang_tatsaechlich": received,
            "document_type": "mieterhoehung",
            "bundesland": "BE",
            "feiertagskalender_bestaetigt": True,
            "feiertage_zusaetzlich": [],
        },
        [],
    )["items"][0]
    assert item["status"] == "missing_input"
    assert item["frist_ende"] is None


def test_service_cure_requires_every_qualification():
    rule = next(
        s for s in load_specs(ROOT / "modules/mietrecht/fristen.yaml") if s.id == "miet_schonfrist"
    )
    base = {
        "zustellung_tatsaechlich": "2026-11-30",
        "document_type": "raeumungsklage",
        "bundesland": "BE",
        "zustellungsart": "inland",
        "feiertagskalender_bestaetigt": True,
        "qualifikationen": {
            "zahlungsverzug": True,
            "keine_schonfrist_letzte_zwei_jahre": True,
            "rechtshaengigkeit_bestaetigt": True,
        },
    }
    ready = compute_deadlines([ModuleSpecs("mietrecht", (rule,))], base, [])["items"][0]
    assert ready["frist_ende"] == "2027-02-01"
    for flag in base["qualifikationen"]:
        facts = {**base, "qualifikationen": {**base["qualifikationen"], flag: False}}
        item = compute_deadlines([ModuleSpecs("mietrecht", (rule,))], facts, [])["items"][0]
        assert item["status"] == "missing_input"


def test_dossier_facts_used_retains_explicit_receipt_and_qualifications():
    rules = load_specs(ROOT / "modules/mietrecht/fristen.yaml")
    facts = {
        "document_type": "mieterhoehung",
        "zugang_tatsaechlich": "2026-11-02",
        "qualifikationen": {"ordentliche_kuendigung": False},
        "bundesland": "BE",
        "feiertagskalender_bestaetigt": True,
        "feiertage_zusaetzlich": [],
    }
    section = compute_deadlines([ModuleSpecs("mietrecht", tuple(rules))], facts, [])
    for key, value in facts.items():
        assert section["facts_used"][key] == value
