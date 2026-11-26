"""Approved D-071 service triggers: never substitute a letter date for service."""

from datetime import date

import pytest

from app.dossier.deadlines import ModuleSpecs, compute_deadlines, validate_facts
from app.fristen.evaluator import FristInput, evaluate_spec
from app.fristen.specs import load_specs


@pytest.fixture
def service_spec(tmp_path):
    path = tmp_path / "fristen.yaml"
    path.write_text("""
- id: court_response
  label_de: Reaktionsfrist
  trigger: zustellung
  duration: {days: 14}
  rollover: zpo_222
  basis: "§ 339 Abs. 1 ZPO"
  fristbeginn_basis: "§ 222 Abs. 1 ZPO, § 187 Abs. 1 BGB"
  severity: critical
  applies_when: {document_type: vollstreckungsbescheid, zustellungsart: inland}
""")
    return load_specs(path)[0]


@pytest.mark.parametrize(
    ("served", "expected"),
    [
        ("2026-11-02", "2026-11-16"),
        ("2026-11-07", "2026-11-23"),
        ("2026-12-11", "2026-12-28"),
        ("2024-02-16", "2024-03-01"),
    ],
)
def test_confirmed_service_drives_end_and_rollover(service_spec, served, expected):
    result = evaluate_spec(
        service_spec,
        FristInput(
            bescheid_datum=date(2020, 1, 1),
            zustellung_tatsaechlich=date.fromisoformat(served),
            document_type="vollstreckungsbescheid",
            zustellungsart="inland",
            rbb_status="fehlt",
            bundesland="NW",
        ),
    )
    assert result.frist_ende == date.fromisoformat(expected)
    assert result.bekanntgabe == date.fromisoformat(served)
    assert "2020" not in result.explanation_de
    assert "Jahresfrist" not in result.explanation_de


def test_service_is_required_even_when_letter_date_is_known(service_spec):
    section = compute_deadlines(
        [ModuleSpecs("debt", (service_spec,))],
        {
            "bescheid_datum": "2026-11-02",
            "document_type": "vollstreckungsbescheid",
            "zustellungsart": "inland",
        },
        [],
    )
    assert section["items"][0]["status"] == "missing_input"
    assert section["items"][0]["frist_ende"] is None


@pytest.mark.parametrize("mode", [None, "ausland", "oeffentlich"])
def test_unreviewed_service_mode_does_not_assert_domestic_end(service_spec, mode):
    facts = {"zustellung_tatsaechlich": "2026-11-02", "document_type": "vollstreckungsbescheid"}
    if mode:
        facts["zustellungsart"] = mode
    item = compute_deadlines([ModuleSpecs("debt", (service_spec,))], facts, [])["items"][0]
    assert item["status"] == "missing_input"
    assert item["frist_ende"] is None


def test_service_facts_work_without_letter_and_independently_of_va_flag(service_spec):
    facts = validate_facts(
        {
            "zustellung_tatsaechlich": "2026-11-02",
            "document_type": "vollstreckungsbescheid",
            "zustellungsart": "inland",
            "ist_verwaltungsakt": False,
            "bundesland": "NW",
        }
    )
    item = compute_deadlines([ModuleSpecs("debt", (service_spec,))], facts, [])["items"][0]
    assert item["status"] == "computed"
    assert item["frist_ende"] == "2026-11-16"


def test_service_holiday_rollover_requires_explicit_region(service_spec):
    item = compute_deadlines(
        [ModuleSpecs("debt", (service_spec,))],
        {
            "zustellung_tatsaechlich": "2026-05-21",
            "document_type": "vollstreckungsbescheid",
            "zustellungsart": "inland",
        },
        [],
    )["items"][0]
    assert item["status"] == "missing_input"
    assert item["frist_ende"] is None
    assert item["inputs"]["bundesland"] is None


def test_document_type_selects_only_matching_rule(service_spec):
    item = compute_deadlines(
        [ModuleSpecs("debt", (service_spec,))],
        {
            "zustellung_tatsaechlich": "2026-11-02",
            "document_type": "inkassoschreiben",
            "zustellungsart": "inland",
        },
        [],
    )["items"][0]
    assert item["status"] == "not_applicable"
    assert item["frist_ende"] is None


@pytest.mark.parametrize(
    "facts",
    [
        {"zustellung_tatsaechlich": "not-a-date"},
        {"zustellungsart": "unknown"},
        {"document_type": True},
    ],
)
def test_service_facts_reject_invalid_inputs(facts):
    with pytest.raises(ValueError):
        validate_facts(facts)
