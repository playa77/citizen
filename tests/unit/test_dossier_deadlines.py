"""WP-103 — Fristen banner of the dossier (app/dossier/deadlines.py).

Deadlines come only from the Fristen core; the dossier decides which inputs
it may use (confirmed vs. proposed letter date) and states its assumptions.
"""

# Semantic Version: 1.0.0 | 2026-11-16 — P10

from __future__ import annotations

from datetime import date

import pytest

from app.dossier.chronology import (
    KIND_DOCUMENT_DATE,
    STATUS_CONFIRMED,
    STATUS_PROPOSED,
    ChronologyEntry,
)
from app.dossier.deadlines import (
    ModuleSpecs,
    compute_deadlines,
    frist_result_for_drafts,
    validate_facts,
)
from app.modules.runtime import deadline_specs

SPECS = [ModuleSpecs("sozialrecht", deadline_specs("sozialrecht"))]


def _letter(day: date, status: str) -> ChronologyEntry:
    return ChronologyEntry(
        entry_id="chr-000000000001",
        date=day,
        kind=KIND_DOCUMENT_DATE,
        label_de="Datum des Schreibens",
        status=status,
        source={"document": "case_input", "label": "t", "line": 1, "excerpt": ""},
    )


def _item(section: dict[str, object]) -> dict[str, object]:
    items = section["items"]
    assert isinstance(items, list) and len(items) == 1
    item: dict[str, object] = items[0]
    return item


def test_confirmed_letter_date_gives_computed_deadline() -> None:
    section = compute_deadlines(SPECS, {}, [_letter(date(2026, 7, 6), STATUS_CONFIRMED)])
    item = _item(section)
    assert (item["status"], item["frist_ende"]) == ("computed", "2026-08-10")
    assert section["earliest_frist_ende"] == "2026-08-10"
    # Conservative defaults are disclosed, never silent.
    assert len(item["assumptions"]) == 4  # type: ignore[arg-type]


def test_proposed_letter_date_is_provisional() -> None:
    item = _item(compute_deadlines(SPECS, {}, [_letter(date(2026, 7, 6), STATUS_PROPOSED)]))
    assert (item["status"], item["frist_ende"]) == ("provisional", "2026-08-10")


def test_no_letter_date_is_missing_input() -> None:
    item = _item(compute_deadlines(SPECS, {}, []))
    assert (item["status"], item["frist_ende"]) == ("missing_input", None)


def test_explicit_facts_win_and_remove_assumptions() -> None:
    facts = validate_facts(
        {
            "bescheid_datum": "2026-02-09",
            "aufgabe_zur_post": "2026-02-09",
            "rbb_status": "fehlerhaft",
            "ist_verwaltungsakt": True,
            "bundesland": "NW",
        }
    )
    item = _item(compute_deadlines(SPECS, facts, [_letter(date(2026, 7, 6), STATUS_CONFIRMED)]))
    assert (item["status"], item["frist_ende"], item["frist_typ"]) == (
        "computed",
        "2027-02-15",
        "jahr",
    )
    assert item["assumptions"] == []


def test_not_a_verwaltungsakt() -> None:
    facts = validate_facts({"bescheid_datum": "2026-06-29", "ist_verwaltungsakt": False})
    section = compute_deadlines(SPECS, facts, [])
    item = _item(section)
    assert (item["status"], item["frist_typ"], item["frist_ende"]) == (
        "not_applicable",
        "kein_va",
        None,
    )
    assert section["earliest_frist_ende"] is None
    result = frist_result_for_drafts(section)
    assert result is not None and result.frist_typ == "kein_va"


def test_draft_frist_result_round_trip() -> None:
    section = compute_deadlines(SPECS, {}, [_letter(date(2026, 7, 6), STATUS_CONFIRMED)])
    result = frist_result_for_drafts(section)
    assert result is not None
    assert (result.frist_ende, result.spec_id) == (date(2026, 8, 10), "widerspruch_sgg_84")
    assert frist_result_for_drafts(compute_deadlines(SPECS, {}, [])) is None


@pytest.mark.parametrize(
    "raw, message",
    [
        ("x", "object"),
        ({"foo": 1}, "unknown facts"),
        ({"bescheid_datum": "06.07.2026"}, "ISO"),
        ({"rbb_status": "falsch"}, "rbb_status"),
        ({"ist_verwaltungsakt": "ja"}, "boolean"),
        ({"bundesland": "XX"}, "bundesland"),
    ],
)
def test_invalid_facts(raw: object, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        validate_facts(raw)


def test_dossier_deadline_for_a_2024_letter() -> None:
    """2024 dispatch → three-day fiction (D-065): 03.05.2024 → Fristende 06.06.2024."""
    facts = validate_facts({"bescheid_datum": "2024-05-03", "bundesland": "BE"})
    assert _item(compute_deadlines(SPECS, facts, []))["frist_ende"] == "2024-06-06"
