"""Unavailable arithmetic must not be reported as a successful check."""

from typing import Any

import pytest

from app.services.calculation import (
    _build_overall_assessment,
    _merge_explanations,
    _summarise_engine_output,
)


def _entry(status: str | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "label": "Pfändungsschutz",
        "computed_values": {
            "deterministic_result": None,
            "computation_detail": "Das bestätigte Bezugsdatum fehlt.",
        },
        "commentary": "Das bestätigte Bezugsdatum fehlt.",
        "discrepancy_found": False,
        "discrepancy_amount_eur": 0,
        "discrepancy_direction": "keine",
    }
    if status is not None:
        result["status"] = status
    return result


@pytest.mark.parametrize(
    "explanation",
    [
        None,
        {
            "overall_assessment": {
                "summary": "Alle Berechnungen sind korrekt.",
                "recommended_action": "Keine Prüfung nötig.",
            }
        },
    ],
)
def test_all_missing_inputs_require_review_instead_of_claiming_success(
    explanation: dict[str, Any] | None,
) -> None:
    result = _build_overall_assessment(
        [_entry("missing_input")], explanation, referral_hint="Schuldnerberatung kontaktieren."
    )
    assert "nicht möglich" in result["summary"]
    assert "fehl" in result["summary"].lower()
    assert result["recommended_action"] == "Schuldnerberatung kontaktieren."
    assert result["total_discrepancies"] == 0


@pytest.mark.parametrize("status", ["missing_input", "provisional"])
def test_explanation_context_and_assembled_entries_keep_qualified_status(status: str) -> None:
    entry = _entry(status)
    context = _summarise_engine_output([entry])
    assert context[0]["status"] == status
    merged = _merge_explanations(
        [entry], {"enriched_calculations": [{"index": 0, "commentary": "Zusätzliche Erläuterung."}]}
    )
    assert merged[0]["status"] == status


def test_legacy_calculations_keep_their_summary_and_explanation_context() -> None:
    entry = _entry()
    explanation = {
        "overall_assessment": {
            "summary": "Legacy-Ergebnis",
            "recommended_action": "Legacy-Empfehlung",
        }
    }
    result = _build_overall_assessment([entry], explanation)
    assert result["summary"] == "Legacy-Ergebnis"
    assert result["recommended_action"] == "Legacy-Empfehlung"
    assert "status" not in _summarise_engine_output([entry])[0]


def test_provisional_date_result_is_not_mistaken_for_missing_arithmetic() -> None:
    entry = _entry("provisional")
    entry["computed_values"]["expiry_date"] = "2030-12-31"
    result = _build_overall_assessment(
        [entry],
        {
            "overall_assessment": {
                "summary": "Vorläufiges Datum unter bestätigten Annahmen.",
            }
        },
    )
    assert result["summary"] == "Vorläufiges Datum unter bestätigten Annahmen."


@pytest.mark.parametrize(
    "explanation",
    [
        None,
        {
            "overall_assessment": {
                "summary": "Alles richtig; Sie dürfen fahren.",
                "recommended_action": "Keine Prüfung nötig.",
            },
            "enriched_calculations": [{"index": 0, "commentary": "Verjährung ist eingetreten."}],
        },
    ],
)
def test_unavailable_traffic_result_cannot_be_explained_as_success(explanation):
    entry = _entry("unavailable")
    assessment = _build_overall_assessment(
        [entry], explanation, referral_hint="Akte prüfen lassen."
    )
    assert "nicht möglich" in assessment["summary"]
    assert assessment["recommended_action"] == "Akte prüfen lassen."
    merged = _merge_explanations([entry], explanation)
    assert merged[0]["commentary"] == entry["commentary"]


def test_mixed_available_and_unavailable_checks_keep_review_requirement():
    successful = _entry("provisional")
    unsuccessful = _entry("unavailable")
    result = _build_overall_assessment(
        [successful, unsuccessful],
        {
            "overall_assessment": {
                "summary": "Alle Posten sind richtig.",
                "recommended_action": "Keine Prüfung nötig.",
            }
        },
        referral_hint="Offene Angaben prüfen lassen.",
    )
    assert "nicht alle" in result["summary"].lower()
    assert result["recommended_action"] == "Offene Angaben prüfen lassen."
