"""Unit tests for the deterministic SGB II rules engine.

Covers every function in ``app.services.rules_engine`` with no mocking
required — all calculations are pure and local.
"""

# Semantic Version: 0.1.0

from __future__ import annotations

from app.services.rules_engine import (
    check_arithmetic,
    compute_aufrechnung,
    compute_freibetrag,
    compute_regelbedarf,
    process_extraction,
    supported_years,
)


# ---------------------------------------------------------------------------
# compute_regelbedarf
# ---------------------------------------------------------------------------


class TestComputeRegelbedarf:
    """Tests for the Regelbedarf lookup function."""

    def test_alleinstehend_2025(self) -> None:
        result = compute_regelbedarf(2025, "alleinstehend")
        assert result["value"] == 563.00
        assert result["stufe"] == 1
        assert result["error"] is None

    def test_alleinerziehend_2025(self) -> None:
        result = compute_regelbedarf(2025, "alleinerziehend")
        assert result["value"] == 563.00
        assert result["stufe"] == 1
        assert result["error"] is None

    def test_partner_2025(self) -> None:
        result = compute_regelbedarf(2025, "partner")
        assert result["value"] == 506.00
        assert result["stufe"] == 2
        assert result["error"] is None

    def test_whitespace_person_type(self) -> None:
        result = compute_regelbedarf(2025, "  Partner  ")
        assert result["value"] == 506.00
        assert result["stufe"] == 2

    def test_none_year(self) -> None:
        result = compute_regelbedarf(None, "alleinstehend")
        assert result["value"] is None
        assert result["stufe"] is None
        assert result["error"] is not None
        assert "Jahr" in result["error"]

    def test_none_person_type(self) -> None:
        result = compute_regelbedarf(2025, None)
        assert result["value"] is None
        assert result["stufe"] is None
        assert result["error"] is not None
        assert "Personentyp" in result["error"]

    def test_unknown_person_type(self) -> None:
        result = compute_regelbedarf(2025, "kind")
        assert result["value"] is None
        assert result["stufe"] is None
        assert "Unbekannt" in result["error"]

    def test_unavailable_year_falls_back(self) -> None:
        """When exact year is unavailable, nearest available year is used."""
        result = compute_regelbedarf(2024, "alleinstehend")
        # Should fall back to 2025.
        assert result["value"] == 563.00
        assert result["stufe"] == 1
        assert result["error"] is not None
        assert "2025" in result["error"]

    def test_no_data_at_all(self, monkeypatch) -> None:
        """If the table is empty, returns an error."""
        import app.services.rules_engine as mod
        monkeypatch.setattr(mod, "_REGELBEDARF_TABLE", {})
        result = compute_regelbedarf(2025, "alleinstehend")
        assert result["value"] is None
        assert result["error"] is not None
        assert "verfügbar" in result["error"]


# ---------------------------------------------------------------------------
# compute_freibetrag
# ---------------------------------------------------------------------------


class TestComputeFreibetrag:
    """Tests for the Erwerbstätigenfreibetrag computation (§ 11b SGB II)."""

    def test_no_income(self) -> None:
        result = compute_freibetrag(0.0)
        assert result["value"] == 0.0
        assert result["brackets_applied"] == []

    def test_none_income(self) -> None:
        result = compute_freibetrag(None)
        assert result["value"] is None
        assert "Bruttoeinkommen" in result["error"]

    def test_grundfreibetrag_only(self) -> None:
        """Income ≤ 100 EUR: only Grundfreibetrag applies."""
        result = compute_freibetrag(100.00)
        assert result["value"] == 100.00
        assert len(result["brackets_applied"]) == 1
        assert result["brackets_applied"][0]["rate"] == 1.00
        assert result["brackets_applied"][0]["amount"] == 100.00

    def test_partial_second_bracket(self) -> None:
        """Income 300 EUR: 100 Grund + 20 % of 200."""
        result = compute_freibetrag(300.00)
        assert result["value"] == 140.00  # 100 + 40
        assert len(result["brackets_applied"]) == 2
        assert result["brackets_applied"][0]["amount"] == 100.00
        assert result["brackets_applied"][1]["amount"] == 40.00

    def test_second_bracket_boundary(self) -> None:
        """Income 520 EUR: 100 Grund + 20 % of 419.99."""
        result = compute_freibetrag(520.00)
        # 100 + (520 - 100.01) * 0.20 ≈ 100 + 84.00 = 184.00
        # Let me recalculate: 520 - 100.01 = 419.99, * 0.20 = 83.998 → 84.00
        # Wait, more precisely: bracket from 100.01 to 520.00, amount = 520.00 - 100.01 = 419.99
        # 419.99 * 0.20 = 83.998, round to 84.00
        # 100 + 84 = 184.00
        assert result["value"] == pytest.approx(184.00, abs=0.01)
        assert len(result["brackets_applied"]) == 2
        # First bracket: 0.00 to 100.00 at 1.00 = 100.00
        # Second bracket: 100.01 to 520.00 at 0.20
        b2_amount = result["brackets_applied"][1]["amount"]
        assert b2_amount == pytest.approx(84.00, abs=0.01)

    def test_full_three_brackets(self) -> None:
        """Income 1000 EUR: 100 + 20% of 420 + 30% of 480."""
        result = compute_freibetrag(1000.00)
        # 100 + (520-100.01)*0.20 + (1000-520.01)*0.30
        # 100 + 419.99*0.20 + 479.99*0.30
        # 100 + 84.00 + 144.00 = 328.00
        assert result["value"] == pytest.approx(328.00, abs=0.02)
        assert len(result["brackets_applied"]) == 3

    def test_fourth_bracket_applies(self) -> None:
        """Income 1200 EUR without child: fourth bracket at 10%."""
        result = compute_freibetrag(1200.00, has_minor_child=False)
        # 100 + 84.00 + 144.00 + (1200-1000.01)*0.10
        # 100 + 84 + 144 + 199.99*0.10
        # 100 + 84 + 144 + 20.00 = 348.00
        assert result["value"] == pytest.approx(348.00, abs=0.02)
        assert len(result["brackets_applied"]) == 4
        assert result["upper_limit"] == 1200.00

    def test_with_minor_child_extends_upper_limit(self) -> None:
        """Income 1500 EUR with child: brackets extend to 1500."""
        result = compute_freibetrag(1500.00, has_minor_child=True)
        # 100 + 84.00 + 144.00 + 200.00*0.10 + 300.00*0.10
        # This gets truncated to 1500 by the child limit
        # 100 + 84 + 144 + 200*0.10 (1001.01 to 1200) + 300*0.10 (1200.01 to 1500)
        # 100 + 84 + 144 + 20 + 30 = 378.00
        assert result["value"] == pytest.approx(378.00, abs=0.02)
        assert result["upper_limit"] == 1500.00

    def test_child_unknown_defaults_to_standard_cap(self) -> None:
        """When has_minor_child is None, the standard 1200 cap applies."""
        result = compute_freibetrag(1500.00, has_minor_child=None)
        # Should cap at 1200.
        assert result["upper_limit"] == 1200.00

    def test_high_income_beyond_cap(self) -> None:
        """Income above the cap: only income up to the cap is considered."""
        result = compute_freibetrag(2000.00, has_minor_child=False)
        # Should be same as 1200 EUR income.
        ref = compute_freibetrag(1200.00, has_minor_child=False)
        assert result["value"] == pytest.approx(ref["value"], abs=0.01)
        assert result["upper_limit"] == 1200.00

    def test_bracket_boundary_100_01(self) -> None:
        """Just above Grundfreibetrag triggers second bracket (zero contribution)."""
        result = compute_freibetrag(100.01)
        # 100 + (100.01 - 100.01) * 0.20 = 100.00
        assert result["value"] == 100.00
        assert len(result["brackets_applied"]) >= 1

    def test_bracket_boundary_520_01(self) -> None:
        """Just above 520 triggers third bracket (zero contribution at boundary)."""
        result = compute_freibetrag(520.01)
        # 100 + 419.99*0.20 + 0*0.30 ≈ 100 + 84 = 184
        assert result["value"] == pytest.approx(184.00, abs=0.02)

    def test_bracket_boundary_1000_01(self) -> None:
        """Just above 1000 triggers fourth bracket."""
        result = compute_freibetrag(1000.01, has_minor_child=False)
        # 100 + 84 + 144 + 0*0.10 ≈ 328
        assert result["value"] == pytest.approx(328.00, abs=0.02)


pytest = __import__("pytest")  # type: ignore[assignment]  # noqa: F811


# ---------------------------------------------------------------------------
# compute_aufrechnung
# ---------------------------------------------------------------------------


class TestComputeAufrechnung:
    """Tests for the Aufrechnung computation (§ 42a SGB II)."""

    def test_standard_2025_regelbedarf(self) -> None:
        result = compute_aufrechnung(563.00)
        assert result["value"] == 28.15  # 5 % of 563.00
        assert result["rate"] == 0.05
        assert result["error"] is None

    def test_partner_regelbedarf(self) -> None:
        result = compute_aufrechnung(506.00)
        assert result["value"] == 25.30  # 5 % of 506.00
        assert result["error"] is None

    def test_none_input(self) -> None:
        result = compute_aufrechnung(None)
        assert result["value"] is None
        assert "Regelbedarf" in result["error"]

    def test_zero_input(self) -> None:
        result = compute_aufrechnung(0.0)
        assert result["value"] == 0.0
        assert result["error"] is None


# ---------------------------------------------------------------------------
# check_arithmetic
# ---------------------------------------------------------------------------


class TestCheckArithmetic:
    """Tests for the arithmetic validation helper."""

    def test_parts_sum_to_total(self) -> None:
        result = check_arithmetic([540.00, 80.00], 620.00)
        assert result["checkable"] is True
        assert result["computed_total"] == 620.00
        assert result["discrepancy"] == 0.0

    def test_mismatch_detected(self) -> None:
        result = check_arithmetic([540.00, 80.00], 600.00)
        assert result["checkable"] is True
        assert result["computed_total"] == 620.00
        assert result["discrepancy"] == 20.00

    def test_some_none_parts(self) -> None:
        """None parts are ignored; only non-None values summed."""
        result = check_arithmetic([100.00, None, 50.00], 150.00)
        assert result["checkable"] is True
        assert result["computed_total"] == 150.00
        assert result["discrepancy"] == 0.0

    def test_all_none_parts(self) -> None:
        result = check_arithmetic([None, None], 100.00)
        assert result["checkable"] is False
        assert "Einzelbeträge" in result["error"]

    def test_none_total(self) -> None:
        result = check_arithmetic([100.00], None)
        assert result["checkable"] is False
        assert "Gesamtbetrag" in result["error"]

    def test_within_tolerance(self) -> None:
        """Rounding difference within tolerance is acceptable."""
        result = check_arithmetic([100.01, 50.01], 150.00, tolerance=0.05)
        assert result["computed_total"] == 150.02
        assert abs(result["discrepancy"]) <= 0.02

    def test_exceeds_tolerance(self) -> None:
        result = check_arithmetic([100.00, 50.00], 150.50, tolerance=0.05)
        assert result["discrepancy"] == -0.50


# ---------------------------------------------------------------------------
# process_extraction
# ---------------------------------------------------------------------------


class TestProcessExtraction:
    """Integration tests for the full extraction → calculations pipeline."""

    def test_full_extraction_all_checks(self) -> None:
        """A complete extraction triggers all check types."""
        extraction = {
            "person_type": "alleinstehend",
            "has_minor_child": False,
            "period_year": 2025,
            "extracted_values": {
                "regelbedarf_authority": 563.00,
                "brutto_einkommen": 1200.00,
                "netto_einkommen": 950.00,
                "freibetrag_authority": 184.00,  # WRONG: should be ~348
                "aufrechnung_regelbedarf_used": 563.00,
                "aufrechnung_authority": 28.15,
                "kdu_unterkunft": 540.00,
                "kdu_heizung": 80.00,
                "kdu_gesamt_authority": 620.00,
                "anrechenbares_einkommen_authority": 1050.00,
                "auszahlungsbetrag_authority": 133.00,
            },
        }

        results = process_extraction(extraction)

        # Should produce entries for: Regelbedarf, Freibetrag, Aufrechnung,
        # KdU, Einkommensanrechnung, Auszahlungsbetrag.
        labels = [r["label"] for r in results]
        assert "Regelbedarf" in labels
        assert "Erwerbstätigenfreibetrag" in labels
        assert "Aufrechnung (Darlehen)" in labels
        assert "Kosten der Unterkunft (KdU)" in labels
        assert "Einkommensanrechnung (Brutto - Freibetrag)" in labels
        assert "Auszahlungsbetrag (Gesamt)" in labels

        # Regelbedarf should match exactly.
        rb = next(r for r in results if r["label"] == "Regelbedarf")
        assert rb["discrepancy_found"] is False
        assert rb["discrepancy_amount_eur"] == 0.0

        # Freibetrag discrepancy: authority says 184, correct is ~348.
        fb = next(r for r in results if r["label"] == "Erwerbstätigenfreibetrag")
        assert fb["discrepancy_found"] is True
        assert fb["discrepancy_direction"] == "zulasten"  # authority too low
        assert fb["discrepancy_amount_eur"] > 100.0
        assert fb["computed_values"]["deterministic_result"] is not None

        # KdU adds up correctly.
        kdu = next(r for r in results if r["label"] == "Kosten der Unterkunft (KdU)")
        assert kdu["discrepancy_found"] is False

    def test_minimal_extraction(self) -> None:
        """Only Regelbedarf and a few values — engine skips uncheckable ones."""
        extraction = {
            "person_type": "partner",
            "period_year": 2025,
            "extracted_values": {
                "regelbedarf_authority": 563.00,  # WRONG for partner: should be 506
            },
        }

        results = process_extraction(extraction)

        # Should still produce a Regelbedarf entry with a discrepancy.
        rb = next(r for r in results if r["label"] == "Regelbedarf")
        assert rb["discrepancy_found"] is True
        assert rb["discrepancy_direction"] == "zugunsten"  # authority set too high
        assert rb["computed_values"]["deterministic_result"] == 506.00

    def test_no_person_type(self) -> None:
        """Missing person type → Regelbedarf is uncheckable."""
        extraction = {
            "period_year": 2025,
            "extracted_values": {
                "regelbedarf_authority": 563.00,
            },
        }

        results = process_extraction(extraction)
        rb = next(r for r in results if r["label"] == "Regelbedarf")
        assert rb["discrepancy_found"] is False
        assert rb["discrepancy_direction"] == "keine"
        assert "Personentyp" in rb["commentary"]

    def test_no_extracted_values_at_all(self) -> None:
        """Empty extraction produces a non-checkable entry."""
        results = process_extraction({})
        assert len(results) == 1
        assert results[0]["label"] == "Regelbedarf"
        assert results[0]["discrepancy_found"] is False

    def test_every_entry_has_required_fields(self) -> None:
        """Ensure every result entry conforms to the expected schema."""
        extraction = {
            "person_type": "alleinstehend",
            "period_year": 2025,
            "extracted_values": {
                "regelbedarf_authority": 563.00,
                "brutto_einkommen": 1200.00,
                "freibetrag_authority": 300.00,
                "aufrechnung_regelbedarf_used": 563.00,
                "aufrechnung_authority": 28.15,
                "kdu_unterkunft": 500.00,
                "kdu_heizung": 100.00,
                "kdu_gesamt_authority": 600.00,
                "anrechenbares_einkommen_authority": 900.00,
                "auszahlungsbetrag_authority": 163.00,
            },
        }

        results = process_extraction(extraction)
        required_keys = {
            "label",
            "document_values",
            "computed_values",
            "correct_calculation",
            "discrepancy_found",
            "discrepancy_amount_eur",
            "discrepancy_direction",
            "relevant_rule",
            "commentary",
        }

        for entry in results:
            assert isinstance(entry, dict)
            assert required_keys.issubset(entry.keys()), (
                f"Missing keys in {entry['label']}: "
                f"{required_keys - set(entry.keys())}"
            )
            assert entry["discrepancy_direction"] in ("zulasten", "zugunsten", "keine")


# ---------------------------------------------------------------------------
# supported_years
# ---------------------------------------------------------------------------


def test_supported_years() -> None:
    years = supported_years()
    assert isinstance(years, list)
    assert 2025 in years
    assert years == sorted(years)
