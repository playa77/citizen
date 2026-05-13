"""Unit tests for the calculation verification service (WP-014).

Covers the ``check_calculations`` function in ``app.services.calculation``,
including the disabled-early-return, the normal LLM-driven path, empty results,
and edge cases around optional ``claims`` / ``sections`` parameters.
"""

# Semantic Version: 0.1.0

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

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


@pytest.fixture
def mock_parse_json() -> MagicMock:
    """Patch ``_parse_json_response`` so no real LLM call is made."""
    with patch("app.services.calculation._parse_json_response") as mock:
        yield mock


@pytest.fixture
def mock_client() -> MagicMock:
    """Patch ``_get_client`` to return a fake async client."""
    with patch("app.services.calculation._get_client") as mock:
        fake_client = AsyncMock()
        fake_client.chat_completion = AsyncMock(return_value="{}")
        mock.return_value = fake_client
        yield mock


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_check_calculations_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """When ``ENABLE_CALCULATION_CHECK=False``, return an early skipped result
    without calling the LLM."""
    monkeypatch.setattr(
        "app.core.config.settings.ENABLE_CALCULATION_CHECK", False
    )

    result = await check_calculations(_SAMPLE_TEXT)

    # Should return the "skipped" empty result immediately.
    assert result["calculations_found"] == []
    assert result["overall_assessment"]["total_discrepancies"] == 0
    assert result["overall_assessment"]["total_amount_eur"] == 0.0
    assert result["overall_assessment"]["direction"] == "keine"
    assert "deaktiviert" in result["overall_assessment"]["summary"]
    assert result["overall_assessment"]["recommended_action"] == ""


async def test_check_calculations_success(
    mock_parse_json: MagicMock, mock_client: MagicMock
) -> None:
    """Happy path: LLM returns valid JSON with calculations found.

    Verifies:
    - ``calculations_found`` is returned correctly with all fields
    - ``overall_assessment`` has the right structure
    - Discrepancy values are properly validated (direction, amount)
    """
    mock_parse_json.return_value = {
        "calculations_found": [
            {
                "label": "Erwerbstätigenfreibetrag",
                "document_values": {
                    "extracted_numbers": {
                        "brutto": 1200.0,
                        "netto": 950.0,
                        "regelbedarf": 563.0,
                        "unterkunft": 540.0,
                    },
                    "authority_calculation": (
                        "Jobcenter: 100 EUR Grundfreibetrag + "
                        "20 % von 420 EUR = 184 EUR Freibetrag"
                    ),
                },
                "correct_calculation": (
                    "Korrekt: 100 EUR Grundfreibetrag + "
                    "20 % von 420 EUR (100-520) = 84 EUR + "
                    "30 % von 480 EUR (520-1000) = 144 EUR, "
                    "gesamt = 328 EUR Freibetrag"
                ),
                "discrepancy_found": True,
                "discrepancy_amount_eur": 144.0,
                "discrepancy_direction": "zulasten",
                "relevant_rule": "§ 11b SGB II – Freibetrag bei Erwerbstätigkeit",
                "commentary": (
                    "Das Jobcenter hat nur 184 EUR statt korrekt "
                    "328 EUR Freibetrag berücksichtigt."
                ),
            }
        ],
        "overall_assessment": {
            "total_discrepancies": 1,
            "total_amount_eur": 144.0,
            "direction": "zulasten",
            "summary": (
                "Es wurde ein Berechnungsfehler beim "
                "Erwerbstätigenfreibetrag festgestellt."
            ),
            "recommended_action": (
                "Widerspruch einlegen und Neuberechnung "
                "des Freibetrags fordern."
            ),
        },
    }

    result = await check_calculations(_SAMPLE_TEXT)

    # ── calculations_found ───────────────────────────────────────────
    assert len(result["calculations_found"]) == 1
    calc = result["calculations_found"][0]

    assert calc["label"] == "Erwerbstätigenfreibetrag"
    assert calc["document_values"]["extracted_numbers"]["brutto"] == 1200.0
    assert calc["document_values"]["extracted_numbers"]["netto"] == 950.0
    assert calc["document_values"]["extracted_numbers"]["regelbedarf"] == 563.0
    assert calc["document_values"]["extracted_numbers"]["unterkunft"] == 540.0
    assert "Grundfreibetrag" in calc["document_values"]["authority_calculation"]
    assert "Grundfreibetrag" in calc["correct_calculation"]
    assert calc["discrepancy_found"] is True
    assert calc["discrepancy_amount_eur"] == 144.0
    assert calc["discrepancy_direction"] == "zulasten"
    assert "§ 11b SGB II" in calc["relevant_rule"]
    assert isinstance(calc["commentary"], str)

    # ── overall_assessment ───────────────────────────────────────────
    assessment = result["overall_assessment"]
    assert assessment["total_discrepancies"] == 1
    assert assessment["total_amount_eur"] == 144.0
    assert assessment["direction"] == "zulasten"
    assert "Berechnungsfehler" in assessment["summary"]
    assert "Widerspruch" in assessment["recommended_action"]

    # Verify the LLM was actually called via the client (not early-returned).
    mock_client.return_value.chat_completion.assert_awaited_once()


async def test_check_calculations_empty_result(
    mock_parse_json: MagicMock, mock_client: MagicMock
) -> None:
    """When the LLM returns an empty ``calculations_found`` array, the
    function handles it gracefully and returns a neutral assessment."""
    mock_parse_json.return_value = {
        "calculations_found": [],
        "overall_assessment": {
            "total_discrepancies": 0,
            "total_amount_eur": 0.0,
            "direction": "keine",
            "summary": (
                "Es wurden keine Berechnungen im Dokument gefunden, "
                "die einer Überprüfung bedürfen."
            ),
            "recommended_action": "",
        },
    }

    result = await check_calculations(_SAMPLE_TEXT)

    assert result["calculations_found"] == []
    assert result["overall_assessment"]["total_discrepancies"] == 0
    assert result["overall_assessment"]["total_amount_eur"] == 0.0
    assert result["overall_assessment"]["direction"] == "keine"
    assert "keine Berechnungen" in result["overall_assessment"]["summary"]
    assert result["overall_assessment"]["recommended_action"] == ""


async def test_check_calculations_no_claims_or_sections(
    mock_parse_json: MagicMock, mock_client: MagicMock
) -> None:
    """When ``claims=None`` and ``sections=None``, the function works with
    just the ``normalized_text`` and produces a valid result."""
    mock_parse_json.return_value = {
        "calculations_found": [
            {
                "label": "Regelbedarf",
                "document_values": {
                    "extracted_numbers": {"regelbedarf": 563.0},
                    "authority_calculation": "563,00 EUR",
                },
                "correct_calculation": "563,00 EUR (korrekt)",
                "discrepancy_found": False,
                "discrepancy_amount_eur": 0.0,
                "discrepancy_direction": "keine",
                "relevant_rule": "§ 20 SGB II",
                "commentary": "Regelbedarf korrekt angesetzt.",
            }
        ],
        "overall_assessment": {
            "total_discrepancies": 0,
            "total_amount_eur": 0.0,
            "direction": "keine",
            "summary": "Alle Berechnungen sind korrekt.",
            "recommended_action": "",
        },
    }

    # Call with only normalized_text; claims and sections are None by default.
    result = await check_calculations(_SAMPLE_TEXT, claims=None, sections=None)

    assert len(result["calculations_found"]) == 1
    assert result["calculations_found"][0]["label"] == "Regelbedarf"
    assert result["calculations_found"][0]["discrepancy_found"] is False
    assert result["calculations_found"][0]["discrepancy_amount_eur"] == 0.0
    assert result["calculations_found"][0]["discrepancy_direction"] == "keine"

    assert result["overall_assessment"]["total_discrepancies"] == 0
    assert result["overall_assessment"]["direction"] == "keine"
    assert result["overall_assessment"]["summary"] == "Alle Berechnungen sind korrekt."

    # The client should still have been called (feature was enabled).
    mock_client.return_value.chat_completion.assert_awaited_once()
