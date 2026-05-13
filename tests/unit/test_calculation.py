"""Unit tests for the calculation verification service (WP-014).

Covers the ``check_calculations`` function in ``app.services.calculation``
with the new three-phase architecture (extraction → rules engine → explanation).
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.services.calculation import check_calculations

pytestmark = pytest.mark.asyncio

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_SAMPLE_TEXT = (
    "Sehr geehrte Damen und Herren,\n\n"
    "hiermit lege ich Widerspruch gegen den Bescheid vom 01.03.2025 ein.\n"
    "Die Berechnung des Erwerbstätigenfreibetrags ist fehlerhaft.\n\n"
    "Bruttoeinkommen: 1.200,00 EUR\n"
    "Nettoeinkommen: 950,00 EUR\n"
    "Regelbedarf: 563,00 EUR\n"
    "Kosten der Unterkunft: 540,00 EUR\n\n"
    "Mit freundlichen Grüßen\nMax Mustermann"
)


def _make_extraction(**overrides):
    """Return a default extraction dict, optionally overriding fields."""
    base = {
        "person_type": "alleinstehend",
        "has_minor_child": False,
        "period_year": 2025,
        "extracted_values": {
            "regelbedarf_authority": 563.00,
            "regelbedarf_stufe": 1,
            "brutto_einkommen": 1200.00,
            "netto_einkommen": 950.00,
            "freibetrag_authority": 184.00,
            "aufrechnung_authority": 28.15,
            "aufrechnung_regelbedarf_used": 563.00,
            "kdu_unterkunft": 540.00,
            "kdu_heizung": 80.00,
            "kdu_gesamt_authority": 620.00,
            "anrechenbares_einkommen_authority": 1050.00,
            "auszahlungsbetrag_authority": 133.00,
        },
        "authority_calculation_text": (
            "Regelbedarf 563,00 EUR, Freibetrag 184,00 EUR "
            "(100 EUR Grundfreibetrag + 20 % von 420 EUR), "
            "Aufrechnung 28,15 EUR, Auszahlung 133,00 EUR"
        ),
        "extraction_notes": "",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_check_calculations_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """When ``ENABLE_CALCULATION_CHECK=False``, return an early empty result
    without calling any LLM."""
    monkeypatch.setattr(
        "app.core.config.settings.ENABLE_CALCULATION_CHECK", False
    )

    result = await check_calculations(_SAMPLE_TEXT)

    assert result["calculations_found"] == []
    assert result["overall_assessment"]["total_discrepancies"] == 0
    assert result["overall_assessment"]["total_amount_eur"] == 0.0
    assert result["overall_assessment"]["direction"] == "keine"
    assert "deaktiviert" in result["overall_assessment"]["summary"]
    assert result["overall_assessment"]["recommended_action"] == ""


async def test_check_calculations_extraction_failure() -> None:
    """When ``_llm_extract`` returns ``None``, return an empty result with
    an error message."""
    mock_extract = AsyncMock(return_value=None)

    with patch("app.services.calculation._llm_extract", mock_extract):
        result = await check_calculations(_SAMPLE_TEXT)

    assert result["calculations_found"] == []
    assert result["overall_assessment"]["total_discrepancies"] == 0
    assert result["overall_assessment"]["total_amount_eur"] == 0.0
    assert result["overall_assessment"]["direction"] == "keine"
    assert "fehlgeschlagen" in result["overall_assessment"]["summary"]
    assert result["overall_assessment"]["recommended_action"] == ""


async def test_check_calculations_successful_pipeline() -> None:
    """Happy path through all three phases.

    Verifies:
    - ``calculations_found`` entries have all required fields
    - ``overall_assessment`` reflects the LLM explanation
    - Discrepancy flags from the deterministic rules engine are propagated
    """
    extraction = _make_extraction()

    mock_extract = AsyncMock(return_value=extraction)

    mock_explain = AsyncMock(
        return_value={
            "enriched_calculations": [
                {"index": 1, "commentary": "Der Freibetrag wurde zu niedrig angesetzt."},
                {"index": 4, "commentary": "Das anrechenbare Einkommen weicht ab."},
            ],
            "overall_assessment": {
                "summary": "Test summary from explanation LLM",
                "recommended_action": "Widerspruch",
            },
        }
    )

    patches = [
        patch("app.services.calculation._llm_extract", mock_extract),
        patch("app.services.calculation._llm_explain", mock_explain),
    ]

    with patches[0], patches[1]:
        result = await check_calculations(_SAMPLE_TEXT)

    # ── calculations_found ──────────────────────────────────────────────
    calcs = result["calculations_found"]
    assert len(calcs) > 0, "Expected at least one calculation entry"

    # Verify each entry has all required fields.
    for entry in calcs:
        assert "label" in entry
        assert "document_values" in entry
        assert "extracted_numbers" in entry["document_values"]
        assert "authority_calculation" in entry["document_values"]
        assert "computed_values" in entry
        assert "deterministic_result" in entry["computed_values"]
        assert "computation_detail" in entry["computed_values"]
        assert "correct_calculation" in entry
        assert "discrepancy_found" in entry
        assert "discrepancy_amount_eur" in entry
        assert "discrepancy_direction" in entry
        assert "relevant_rule" in entry
        assert "commentary" in entry

    # Check specific expected entries (by label).
    labels = [c["label"] for c in calcs]

    # ── Regelbedarf (no discrepancy: 563 vs 563) ────────────────────────
    assert "Regelbedarf" in labels
    rb = next(c for c in calcs if c["label"] == "Regelbedarf")
    assert rb["discrepancy_found"] is False
    assert rb["discrepancy_amount_eur"] == 0.0
    assert rb["discrepancy_direction"] == "keine"

    # ── Erwerbstätigenfreibetrag (discrepancy: 184 vs 348 ─ zulasten) ────
    assert "Erwerbstätigenfreibetrag" in labels
    fb = next(c for c in calcs if c["label"] == "Erwerbstätigenfreibetrag")
    assert fb["discrepancy_found"] is True
    assert fb["discrepancy_direction"] == "zulasten"
    # computed=348, authority=184, diff=164
    assert fb["discrepancy_amount_eur"] == 164.0
    assert "§ 11b SGB II" in fb["relevant_rule"]
    # LLM commentary should override engine commentary for index 1.
    assert fb["commentary"] == "Der Freibetrag wurde zu niedrig angesetzt."

    # ── Aufrechnung (no discrepancy: 28.15 vs 28.15) ────────────────────
    assert "Aufrechnung (Darlehen)" in labels
    auf = next(c for c in calcs if c["label"] == "Aufrechnung (Darlehen)")
    assert auf["discrepancy_found"] is False

    # ── KdU (no discrepancy: 540+80 = 620) ──────────────────────────────
    assert "Kosten der Unterkunft (KdU)" in labels
    kdu = next(c for c in calcs if c["label"] == "Kosten der Unterkunft (KdU)")
    assert kdu["discrepancy_found"] is False

    # ── Einkommensanrechnung (discrepancy: 852 vs 1050 ─ zugunsten) ─────
    assert "Einkommensanrechnung (Brutto - Freibetrag)" in labels
    ec = next(c for c in calcs if c["label"] == "Einkommensanrechnung (Brutto - Freibetrag)")
    assert ec["discrepancy_found"] is True
    assert ec["discrepancy_direction"] == "zugunsten"
    assert ec["discrepancy_amount_eur"] == 198.0
    # LLM commentary should override engine commentary for index 4.
    assert ec["commentary"] == "Das anrechenbare Einkommen weicht ab."

    # ── Auszahlungsbetrag (discrepancy: 331 vs 133 ─ zulasten) ──────────
    assert "Auszahlungsbetrag (Gesamt)" in labels
    az = next(c for c in calcs if c["label"] == "Auszahlungsbetrag (Gesamt)")
    assert az["discrepancy_found"] is True
    assert az["discrepancy_direction"] == "zulasten"
    assert az["discrepancy_amount_eur"] == 198.0

    # ── overall_assessment ──────────────────────────────────────────────
    assessment = result["overall_assessment"]
    assert assessment["summary"] == "Test summary from explanation LLM"
    assert assessment["recommended_action"] == "Widerspruch"

    # Total discrepancies from the engine (3 of 6 entries have discrepancies).
    assert assessment["total_discrepancies"] == 3
    assert assessment["total_amount_eur"] == 560.0  # 164 + 198 + 198
    # Mixed directions default to "zulasten" in _build_overall_assessment.
    assert assessment["direction"] == "zulasten"


async def test_check_calculations_explanation_fallback() -> None:
    """When ``_llm_explain`` returns ``None``, the engine's templated
    commentary is used as a fallback. The result is still valid."""
    extraction = _make_extraction()

    mock_extract = AsyncMock(return_value=extraction)
    mock_explain = AsyncMock(return_value=None)

    patches = [
        patch("app.services.calculation._llm_extract", mock_extract),
        patch("app.services.calculation._llm_explain", mock_explain),
    ]

    with patches[0], patches[1]:
        result = await check_calculations(_SAMPLE_TEXT)

    # ── calculations_found ──────────────────────────────────────────────
    calcs = result["calculations_found"]
    assert len(calcs) > 0

    # Every entry must have a non-empty commentary (engine fallback).
    for entry in calcs:
        assert isinstance(entry["commentary"], str)
        assert len(entry["commentary"]) > 0

    # The engine's discrepancy data should still be intact.
    disc_entries = [c for c in calcs if c["discrepancy_found"]]
    assert len(disc_entries) == 3

    # ── overall_assessment (fallback — no LLM summary) ──────────────────
    assessment = result["overall_assessment"]
    # Since _llm_explain returned None, the engine's templated summary
    # should be used instead.
    assert len(assessment["summary"]) > 0
    assert "3" in assessment["summary"] or "drei" in assessment["summary"].lower() or "560" in assessment["summary"]
    assert "560" in assessment["summary"], (
        "Expected the fallback summary to mention the total amount (560.00 EUR)"
    )
    assert assessment["total_discrepancies"] == 3
    assert assessment["total_amount_eur"] == 560.0
