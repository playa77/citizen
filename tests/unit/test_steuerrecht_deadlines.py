"""Qualified AO notification and objection regressions (synthetic dates)."""

from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from app.dossier.deadlines import ModuleSpecs, compute_deadlines
from app.fristen.evaluator import FristInput, evaluate_spec
from app.fristen.specs import load_specs


def spec():
    return load_specs(Path("modules/steuerrecht/fristen.yaml"))[0]


def facts():
    return FristInput(
        bescheid_datum=date(2026, 1, 1),
        aufgabe_zur_post=date(2026, 1, 28),
        document_type="steuerbescheid",
        zustellungsart="inland",
        bundesland="NW",
        feiertagskalender_bestaetigt=True,
        qualifikationen={key: True for key in spec().requires_confirmed},
    )


def test_four_day_presumption_rolls_sunday_and_month_end():
    result = evaluate_spec(spec(), facts(), "steuerrecht")
    assert result.bekanntgabe == date(2026, 2, 2)
    assert result.frist_ende == date(2026, 3, 2)
    assert not result.oq1_flag


def test_early_receipt_does_not_shorten_presumption():
    result = evaluate_spec(spec(), replace(facts(), bekanntgabe_tatsaechlich=date(2026, 1, 29)))
    assert result.bekanntgabe == date(2026, 2, 2)


@pytest.mark.parametrize(
    "changes",
    [
        {"aufgabe_zur_post": None},
        {"aufgabe_zur_post": date(2024, 12, 30)},
        {"bekanntgabe_tatsaechlich": date(2026, 2, 3)},
        {"qualifikationen": {}},
        {"zustellungsart": "ausland"},
        {"feiertagskalender_bestaetigt": False},
    ],
)
def test_unsupported_facts_never_produce_definite_date(changes):
    with pytest.raises(ValueError):
        evaluate_spec(spec(), replace(facts(), **changes))


def test_missing_instruction_year_and_saturday_rollover():
    result = evaluate_spec(
        spec(), replace(facts(), aufgabe_zur_post=date(2026, 1, 2), rbb_status="fehlt")
    )
    assert result.bekanntgabe == date(2026, 1, 6)
    assert result.frist_ende == date(2027, 1, 6)
    result = evaluate_spec(spec(), replace(facts(), aufgabe_zur_post=date(2026, 1, 3)))
    assert result.frist_ende == date(2026, 2, 9)


def test_dossier_missing_dispatch_has_no_date_or_issue_date_fallback():
    section = compute_deadlines(
        [ModuleSpecs("steuerrecht", (spec(),))], {"bescheid_datum": "2026-01-01"}, []
    )
    assert section["items"][0]["status"] == "missing_input"
    assert section["items"][0]["frist_ende"] is None
    assert not any("angenommen: Datum" in a for a in section["items"][0]["assumptions"])


def test_dossier_confirmed_facts_and_late_receipt():
    raw = dict(vars(facts()))
    raw = {k: (v.isoformat() if isinstance(v, date) else v) for k, v in raw.items()}
    section = compute_deadlines([ModuleSpecs("steuerrecht", (spec(),))], raw, [])
    assert section["items"][0]["frist_ende"] == "2026-03-02"
    raw["bekanntgabe_tatsaechlich"] = "2026-02-03"
    section = compute_deadlines([ModuleSpecs("steuerrecht", (spec(),))], raw, [])
    assert section["items"][0]["frist_ende"] is None


@pytest.mark.parametrize(
    "key",
    [
        "ao_receipt_disputed",
        "ao_nonreceipt",
        "ao_special_regime",
        "ao_356_exception",
    ],
)
def test_excluded_regimes_are_guarded_in_engine_and_dossier(key):
    given = facts()
    qualifications = dict(given.qualifikationen, **{key: True})
    with pytest.raises(ValueError):
        evaluate_spec(spec(), replace(given, qualifikationen=qualifications))
    raw = dict(vars(replace(given, qualifikationen=qualifications)))
    raw = {k: (v.isoformat() if isinstance(v, date) else v) for k, v in raw.items()}
    section = compute_deadlines([ModuleSpecs("steuerrecht", (spec(),))], raw, [])
    assert section["items"][0]["frist_ende"] is None


def test_calendar_month_end_and_confirmed_local_holiday():
    result = evaluate_spec(spec(), replace(facts(), aufgabe_zur_post=date(2026, 1, 27)))
    # Four-day date is Saturday, so notification rolls to Monday, not January 31.
    assert result.bekanntgabe == date(2026, 2, 2)
    result = evaluate_spec(spec(), replace(facts(), aufgabe_zur_post=date(2026, 2, 23)))
    assert result.bekanntgabe == date(2026, 2, 27)
    assert result.frist_ende == date(2026, 3, 27)
    result = evaluate_spec(
        spec(),
        replace(
            facts(),
            aufgabe_zur_post=date(2026, 1, 28),
            feiertage_zusaetzlich=(date(2026, 2, 2), date(2026, 3, 3)),
        ),
    )
    assert result.bekanntgabe == date(2026, 2, 3)
    assert result.frist_ende == date(2026, 3, 4)


@pytest.mark.parametrize("rbb", ["fehlt", "fehlerhaft"])
def test_year_deadline_requires_exclusion_of_356_exceptions(rbb):
    given = facts()
    qualifications = dict(given.qualifikationen)
    qualifications.pop("ao_356_exceptions_excluded")
    with pytest.raises(ValueError):
        evaluate_spec(spec(), replace(given, qualifikationen=qualifications, rbb_status=rbb))


def test_short_month_and_leap_year_substitute():
    result = evaluate_spec(spec(), replace(facts(), aufgabe_zur_post=date(2026, 1, 26)))
    assert result.bekanntgabe == date(2026, 1, 30)
    assert result.frist_ende == date(2026, 3, 2)  # February 28 is Saturday.
    result = evaluate_spec(
        spec(), replace(facts(), aufgabe_zur_post=date(2028, 2, 25), rbb_status="fehlerhaft")
    )
    assert result.bekanntgabe == date(2028, 2, 29)
    assert result.frist_ende == date(2029, 2, 28)
