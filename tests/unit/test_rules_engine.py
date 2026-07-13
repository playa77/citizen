"""Unit tests for the deterministic SGB II rules engine.

Covers every function in ``app.services.rules_engine`` with no mocking
required — all calculations are pure and local.

Extended in WP-23 with tests for Bedarf assembly, full reconciliation,
Additionsfehler detection, multi-month aggregation, and regime-aware
Freibetrag brackets.
"""

# Semantic Version: 0.2.0

from __future__ import annotations

import pytest

from app.services.rules_engine import (
    ReconciliationLineItem,
    aggregate_months,
    check_arithmetic,
    compute_aufrechnung,
    compute_bedarf,
    compute_freibetrag,
    compute_regelbedarf,
    detect_additionsfehler,
    process_extraction,
    reconcile_bedarf_einkommen,
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
        assert result["value"] == pytest.approx(184.00, abs=0.01)
        assert len(result["brackets_applied"]) == 2
        b2_amount = result["brackets_applied"][1]["amount"]
        assert b2_amount == pytest.approx(84.00, abs=0.01)

    def test_full_three_brackets(self) -> None:
        """Income 1000 EUR: 100 + 20% of 420 + 30% of 480."""
        result = compute_freibetrag(1000.00)
        assert result["value"] == pytest.approx(328.00, abs=0.02)
        assert len(result["brackets_applied"]) == 3

    def test_fourth_bracket_applies(self) -> None:
        """Income 1200 EUR without child: fourth bracket at 10%."""
        result = compute_freibetrag(1200.00, has_minor_child=False)
        assert result["value"] == pytest.approx(348.00, abs=0.02)
        assert len(result["brackets_applied"]) == 4
        assert result["upper_limit"] == 1200.00

    def test_with_minor_child_extends_upper_limit(self) -> None:
        """Income 1500 EUR with child: brackets extend to 1500."""
        result = compute_freibetrag(1500.00, has_minor_child=True)
        assert result["value"] == pytest.approx(378.00, abs=0.02)
        assert result["upper_limit"] == 1500.00

    def test_child_unknown_defaults_to_standard_cap(self) -> None:
        """When has_minor_child is None, the standard 1200 cap applies."""
        result = compute_freibetrag(1500.00, has_minor_child=None)
        assert result["upper_limit"] == 1200.00

    def test_high_income_beyond_cap(self) -> None:
        """Income above the cap: only income up to the cap is considered."""
        result = compute_freibetrag(2000.00, has_minor_child=False)
        ref = compute_freibetrag(1200.00, has_minor_child=False)
        assert result["value"] == pytest.approx(ref["value"], abs=0.01)
        assert result["upper_limit"] == 1200.00

    def test_bracket_boundary_100_01(self) -> None:
        """Just above Grundfreibetrag triggers second bracket (zero contribution)."""
        result = compute_freibetrag(100.01)
        assert result["value"] == 100.00
        assert len(result["brackets_applied"]) >= 1

    def test_bracket_boundary_520_01(self) -> None:
        """Just above 520 triggers third bracket (zero contribution at boundary)."""
        result = compute_freibetrag(520.01)
        assert result["value"] == pytest.approx(184.00, abs=0.02)

    def test_bracket_boundary_1000_01(self) -> None:
        """Just above 1000 triggers fourth bracket."""
        result = compute_freibetrag(1000.01, has_minor_child=False)
        assert result["value"] == pytest.approx(328.00, abs=0.02)

    def test_regime_field_in_return(self) -> None:
        """Return dict includes the regime that was used."""
        result = compute_freibetrag(500.00, regime="a.F._vor_2023")
        assert result.get("regime") == "a.F._vor_2023"

        result2 = compute_freibetrag(500.00, regime=None)
        assert result2.get("regime") is None

    def test_old_brackets_no_30_percent_band(self) -> None:
        """a.F._vor_2023 regime uses old brackets (no 30% band).

        The old brackets:
            - 0.00-100.00 @ 100%
            - 100.01-1000.00 @ 20%
            - 1000.01-1200.00 @ 10%

        So income 1100 EUR: 100 + 899.99*0.20 + 99.99*0.10 = 100 + 180 + 10 = 290.
        """
        result_old = compute_freibetrag(1100.00, regime="a.F._vor_2023")
        # 100 + (1000-100.01)*0.20 + (1100-1000.01)*0.10
        # 100 + 899.99*0.20 + 99.99*0.10
        # 100 + 180.00 + 10.00 = 290.00
        assert result_old["value"] == pytest.approx(290.00, abs=0.02)
        assert len(result_old["brackets_applied"]) == 3

        # Same income with current brackets: 100 + 84 + 144 + 10 = 338.
        result_current = compute_freibetrag(1100.00, regime="a.F._2025")
        assert result_current["value"] == pytest.approx(338.00, abs=0.02)
        assert len(result_current["brackets_applied"]) == 4

    def test_old_brackets_boundary_at_520(self) -> None:
        """Old brackets have no rate change at 520 — still 20%."""
        result = compute_freibetrag(600.00, regime="a.F._vor_2023")
        # 100 + (600-100.01)*0.20 = 100 + 499.99*0.20 = 100 + 100.00 = 200.00
        assert result["value"] == pytest.approx(200.00, abs=0.02)
        assert len(result["brackets_applied"]) == 2  # only 100% and 20% bands

    def test_old_brackets_with_child_extends_upper_limit(self) -> None:
        """With child, upper limit extends to 1500 even with old brackets."""
        result = compute_freibetrag(1500.00, has_minor_child=True, regime="a.F._vor_2023")
        # 100 + (1000-100.01)*0.20 + (1500-1000.01)*0.10
        # 100 + 180.00 + 50.00 = 330.00
        assert result["value"] == pytest.approx(330.00, abs=0.02)
        assert result["upper_limit"] == 1500.00


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
        result = check_arithmetic([100.01, 50.01], 150.00, tolerance=0.05)
        assert result["computed_total"] == 150.02
        assert abs(result["discrepancy"]) <= 0.02

    def test_exceeds_tolerance(self) -> None:
        result = check_arithmetic([100.00, 50.00], 150.50, tolerance=0.05)
        assert result["discrepancy"] == -0.50


# ---------------------------------------------------------------------------
# compute_bedarf
# ---------------------------------------------------------------------------


class TestComputeBedarf:
    """Tests for Bedarf assembly (Regelbedarf + KdU + Mehrbedarfe)."""

    def test_single_person_no_mehrbedarf(self) -> None:
        """Basic Bedarf: Regelbedarf 563 + KdU 400 = 963."""
        result = compute_bedarf(
            person_type="alleinstehend",
            period_year=2025,
            kdu_authority=400.00,
        )
        assert result["regelbedarf"] == 563.00
        assert result["kdu"] == 400.00
        assert result["mehrbedarf_total"] == 0.0
        assert result["gesamtbedarf"] == 963.00
        assert result["regelbedarf_error"] is None

    def test_with_mehrbedarf_items(self) -> None:
        """Bedarf with Mehrbedarf items summed correctly."""
        result = compute_bedarf(
            person_type="alleinerziehend",
            period_year=2025,
            kdu_authority=450.00,
            mehrbedarf_items=[
                {"label": "Mehrbedarf Alleinerziehung", "amount": 187.00},
                {"label": "Mehrbedarf Kostenaufwand", "amount": 35.00},
            ],
        )
        assert result["regelbedarf"] == 563.00
        assert result["kdu"] == 450.00
        assert result["mehrbedarf_total"] == 222.00
        assert result["gesamtbedarf"] == 1235.00  # 563 + 450 + 222

    def test_missing_kdu_returns_none_gesamtbedarf(self) -> None:
        """Missing KdU → Gesamtbedarf is None."""
        result = compute_bedarf(
            person_type="alleinstehend",
            period_year=2025,
            kdu_authority=None,
        )
        assert result["regelbedarf"] == 563.00
        assert result["kdu"] is None
        assert result["gesamtbedarf"] is None

    def test_missing_person_type(self) -> None:
        """Unknown person type → Regelbedarf has error, Gesamtbedarf is None."""
        result = compute_bedarf(
            person_type="kind",
            period_year=2025,
            kdu_authority=400.00,
        )
        assert result["regelbedarf"] is None
        assert result["regelbedarf_error"] is not None
        assert result["kdu"] == 400.00
        assert result["gesamtbedarf"] is None

    def test_empty_mehrbedarf_items(self) -> None:
        """Empty or None Mehrbedarf list yields zero total."""
        result = compute_bedarf(
            person_type="alleinstehend",
            period_year=2025,
            kdu_authority=300.00,
            mehrbedarf_items=None,
        )
        assert result["mehrbedarf_total"] == 0.0
        assert result["mehrbedarfe"] == []

        result2 = compute_bedarf(
            person_type="alleinstehend",
            period_year=2025,
            kdu_authority=300.00,
            mehrbedarf_items=[],
        )
        assert result2["mehrbedarf_total"] == 0.0
        assert result2["mehrbedarfe"] == []

    def test_partner_bedarf(self) -> None:
        """Partner type uses Stufe 2 Regelbedarf."""
        result = compute_bedarf(
            person_type="partner",
            period_year=2025,
            kdu_authority=500.00,
        )
        assert result["regelbedarf"] == 506.00
        assert result["regelbedarf_stufe"] == 2
        assert result["gesamtbedarf"] == 1006.00


# ---------------------------------------------------------------------------
# reconcile_bedarf_einkommen
# ---------------------------------------------------------------------------


class TestReconcileBedarfEinkommen:
    """Tests for the full Bedarf-vs-Einkommen reconciliation."""

    def _make_bedarf(self, rb=563.0, kdu=400.0, mb_total=0.0) -> dict:
        return {
            "regelbedarf": rb,
            "regelbedarf_error": None,
            "regelbedarf_stufe": 1,
            "kdu": kdu,
            "mehrbedarfe": [],
            "mehrbedarf_total": mb_total,
            "gesamtbedarf": round(rb + kdu + mb_total, 2) if rb is not None and kdu is not None else None,
        }

    def _make_freibetrag(self, value=190.0) -> dict:
        return {"value": value, "brackets_applied": [], "upper_limit": 1200.0, "error": None, "regime": None}

    def test_happy_path(self) -> None:
        """Bedarf 563 + KdU 400 = 963, Netto 300, Freibetrag 190.

        Anrechenbares Einkommen: max(300 - 190, 0) = 110
        Anspruch: max(963 - 110, 0) = 853
        """
        items = reconcile_bedarf_einkommen(
            bedarf=self._make_bedarf(rb=563.0, kdu=400.0),
            einkommen_brutto=500.0,
            einkommen_netto=300.0,
            freibetrag=self._make_freibetrag(190.0),
            bedarf_authority=963.0,
            einkommen_authority=115.0,
            anspruch_authority=848.0,
        )

        labels = {i.label for i in items}
        assert "Gesamtbedarf" in labels
        assert "Erwerbstätigenfreibetrag" in labels
        assert "Anrechenbares Einkommen" in labels
        assert "Anspruch (Leistung)" in labels

        # Find line items.
        anspruch = next(i for i in items if i.label == "Anspruch (Leistung)")
        assert anspruch.korrekt == pytest.approx(853.0, abs=0.01)
        assert anspruch.jobcenter_ergebnis == 848.0
        assert anspruch.differenz == pytest.approx(5.0, abs=0.01)

        ae = next(i for i in items if i.label == "Anrechenbares Einkommen")
        assert ae.korrekt == 110.0

    def test_netto_less_than_freibetrag(self) -> None:
        """Netto < Freibetrag → anrechenbares Einkommen = 0.

        Netto 100, Freibetrag 190 → max(100 - 190, 0) = 0
        Anspruch = max(963 - 0, 0) = 963
        """
        items = reconcile_bedarf_einkommen(
            bedarf=self._make_bedarf(rb=563.0, kdu=400.0),
            einkommen_brutto=300.0,
            einkommen_netto=100.0,
            freibetrag=self._make_freibetrag(190.0),
            bedarf_authority=963.0,
            einkommen_authority=0.0,
            anspruch_authority=963.0,
        )

        ae = next(i for i in items if i.label == "Anrechenbares Einkommen")
        assert ae.korrekt == 0.0

        anspruch = next(i for i in items if i.label == "Anspruch (Leistung)")
        assert anspruch.korrekt == 963.0

    def test_anspruch_capped_at_zero(self) -> None:
        """Anspruch < 0 → cap at 0.

        Netto 1000, Bedarf 500, anrechenbar 810 → max(500 - 810, 0) = 0
        """
        items = reconcile_bedarf_einkommen(
            bedarf=self._make_bedarf(rb=400.0, kdu=100.0),  # gesamtbedarf = 500
            einkommen_brutto=1200.0,
            einkommen_netto=1000.0,
            freibetrag=self._make_freibetrag(190.0),  # anrechenbar = 1000-190 = 810
            bedarf_authority=500.0,
            einkommen_authority=810.0,
            anspruch_authority=0.0,
        )

        anspruch = next(i for i in items if i.label == "Anspruch (Leistung)")
        assert anspruch.korrekt == 0.0

    def test_gs001_scenario(self) -> None:
        """GS-001 goldset scenario: full reconciliation.

        Goldset GS-001 data:
            regelbedarf: 563, kdu: 550, gesamtbedarf: 1113
            brutto: 1100, netto: 890
            Expected korrekt:
                grundabsetzung: 100, fb_20: 84, fb_30: 144, fb_10: 10,
                freibetrag_gesamt: 338
                anzurechnendes_einkommen: 552
                anspruch_monatlich: 561
        """
        # Compute the Freibetrag for GS-001 (brutto 1100, current regime).
        fb = compute_freibetrag(1100.00, has_minor_child=False, regime="a.F._2025")
        assert fb["value"] == pytest.approx(338.0, abs=0.02)

        # Build Bedarf.
        bedarf = compute_bedarf(
            person_type="alleinstehend",
            period_year=2025,
            kdu_authority=550.0,
        )
        assert bedarf["regelbedarf"] == 563.0
        assert bedarf["kdu"] == 550.0
        assert bedarf["gesamtbedarf"] == 1113.0

        # Reconcile.
        items = reconcile_bedarf_einkommen(
            bedarf=bedarf,
            einkommen_brutto=1100.0,
            einkommen_netto=890.0,
            freibetrag=fb,
            bedarf_authority=1113.0,
            einkommen_authority=600.0,  # JC said 600
            anspruch_authority=513.0,  # JC said 513
        )

        ae = next(i for i in items if i.label == "Anrechenbares Einkommen")
        assert ae.korrekt == 552.0
        assert ae.korrekt == pytest.approx(890.0 - 338.0, abs=0.01)

        anspruch = next(i for i in items if i.label == "Anspruch (Leistung)")
        assert anspruch.korrekt == 561.0
        assert anspruch.korrekt == pytest.approx(1113.0 - 552.0, abs=0.01)

    def test_missing_netto_einkommen(self) -> None:
        """Missing netto → anrechenbares Einkommen and Anspruch are None."""
        fb = self._make_freibetrag(190.0)
        items = reconcile_bedarf_einkommen(
            bedarf=self._make_bedarf(rb=563.0, kdu=400.0),
            einkommen_brutto=500.0,
            einkommen_netto=None,
            freibetrag=fb,
            bedarf_authority=963.0,
            einkommen_authority=None,
            anspruch_authority=None,
        )

        ae = next(i for i in items if i.label == "Anrechenbares Einkommen")
        assert ae.korrekt is None
        assert ae.jobcenter_ergebnis is None

        anspruch = next(i for i in items if i.label == "Anspruch (Leistung)")
        assert anspruch.korrekt is None


# ---------------------------------------------------------------------------
# detect_additionsfehler
# ---------------------------------------------------------------------------


class TestDetectAdditionsfehler:
    """Tests for arithmetic error detection in Bescheid numbers."""

    def test_no_error_when_components_consistent(self) -> None:
        """No error when Gesamtbedarf - Anrechenbar = Anspruch."""
        items = [
            ReconciliationLineItem(
                label="Gesamtbedarf",
                jobcenter_ergebnis=1113.0,
                korrekt=1113.0,
                differenz=0.0,
                relevant_rule="§ 19",
                detail="",
            ),
            ReconciliationLineItem(
                label="Anrechenbares Einkommen",
                jobcenter_ergebnis=600.0,
                korrekt=552.0,
                differenz=-48.0,
                relevant_rule="§ 11b",
                detail="",
            ),
            ReconciliationLineItem(
                label="Anspruch (Leistung)",
                jobcenter_ergebnis=513.0,
                korrekt=561.0,
                differenz=48.0,
                relevant_rule="§ 19",
                detail="",
            ),
        ]
        result = detect_additionsfehler(items)
        # 513 ≈ max(1113 - 600, 0) = 513 ✓ — consistent
        assert result["additionsfehler_found"] is False
        assert result["error_count"] == 0

    def test_error_detected_anspruch_mismatch(self) -> None:
        """Error when Gesamtbedarf - Anrechenbar ≠ Anspruch."""
        items = [
            ReconciliationLineItem(
                label="Gesamtbedarf",
                jobcenter_ergebnis=1000.0,
                korrekt=1000.0,
                differenz=0.0,
                relevant_rule="§ 19",
                detail="",
            ),
            ReconciliationLineItem(
                label="Anrechenbares Einkommen",
                jobcenter_ergebnis=300.0,
                korrekt=300.0,
                differenz=0.0,
                relevant_rule="§ 11b",
                detail="",
            ),
            ReconciliationLineItem(
                label="Anspruch (Leistung)",
                jobcenter_ergebnis=800.0,  # should be 1000-300 = 700
                korrekt=700.0,
                differenz=-100.0,
                relevant_rule="§ 19",
                detail="",
            ),
        ]
        result = detect_additionsfehler(items)
        assert result["additionsfehler_found"] is True
        assert result["error_count"] >= 1
        assert any("Anspruch inkonsistent" in d for d in result["details"])

    def test_gs010_scenario(self) -> None:
        """GS-010 goldset scenario: known additionsfehler.

        Goldset GS-010:
            monatsbetraege: [214, 214, 214]
            jobcenter_ergebnis: gesamtforderung = 742
            expected_korrekt: summe_korrekt = 642, ueberhoehung = 100

        The authority says total is 742 but 3 × 214 = 642, so there's a 100 EUR overcharge.
        """
        items = [
            ReconciliationLineItem(
                label="Anspruch (Leistung)",
                jobcenter_ergebnis=742.0,  # authority says total
                korrekt=642.0,  # 3 * 214
                differenz=-100.0,
                relevant_rule="§ 19 SGB II",
                detail="Summe 3 × 214 = 642, Behörde: 742",
            ),
        ]
        result = detect_additionsfehler(items)
        # There's no Gesamtbedarf/Anrechenbar in this scenario,
        # so the check doesn't trigger (no gb/ae/anspruch all present).
        # The additionsfehler here is that 3*214 ≠ 742.
        # That kind of check requires GS-010's monthly amounts, not
        # the reconciliation line items.  The monolithic check passes.
        assert result["checked_items"] == 0  # can't check without all three

    def test_dict_items_accepted(self) -> None:
        """Plain dict items (not dataclass) are also accepted."""
        items = [
            {"label": "Gesamtbedarf", "jobcenter_ergebnis": 1000.0},
            {"label": "Anrechenbares Einkommen", "jobcenter_ergebnis": 300.0},
            {"label": "Anspruch (Leistung)", "jobcenter_ergebnis": 650.0},
        ]
        result = detect_additionsfehler(items)
        assert result["additionsfehler_found"] is True
        assert result["checked_items"] == 1
        assert result["error_count"] >= 1


# ---------------------------------------------------------------------------
# aggregate_months
# ---------------------------------------------------------------------------


class TestAggregateMonths:
    """Tests for multi-month aggregation of reconciliation data."""

    def _month_items(
        self,
        gesamtbedarf=(1113.0, 1113.0),
        anrechenbar=(600.0, 552.0),
        anspruch=(513.0, 561.0),
    ) -> list[ReconciliationLineItem]:
        gb_jc, gb_korr = gesamtbedarf
        ae_jc, ae_korr = anrechenbar
        an_jc, an_korr = anspruch
        return [
            ReconciliationLineItem(
                label="Gesamtbedarf",
                jobcenter_ergebnis=gb_jc, korrekt=gb_korr,
                differenz=round(gb_korr - gb_jc, 2) if gb_korr is not None and gb_jc is not None else None,
                relevant_rule="§ 19 SGB II",
                detail="",
            ),
            ReconciliationLineItem(
                label="Anrechenbares Einkommen",
                jobcenter_ergebnis=ae_jc, korrekt=ae_korr,
                differenz=round(ae_korr - ae_jc, 2) if ae_korr is not None and ae_jc is not None else None,
                relevant_rule="§ 11b SGB II",
                detail="",
            ),
            ReconciliationLineItem(
                label="Anspruch (Leistung)",
                jobcenter_ergebnis=an_jc, korrekt=an_korr,
                differenz=round(an_korr - an_jc, 2) if an_korr is not None and an_jc is not None else None,
                relevant_rule="§ 19 SGB II",
                detail="",
            ),
        ]

    def test_two_identical_months(self) -> None:
        """Two months with same data: values should double."""
        m1 = self._month_items()
        m2 = self._month_items()

        result = aggregate_months([m1, m2])

        assert result["month_count"] == 2
        aggregated = {e["label"]: e for e in result["aggregated"]}

        # Gesamtbedarf: 1113 * 2 = 2226
        gb = aggregated["Gesamtbedarf"]
        assert gb["jobcenter_ergebnis_total"] == 2226.0
        assert gb["korrekt_total"] == 2226.0
        assert gb["months"] == 2

        # Anspruch: 513 * 2 = 1026 (JC), 561 * 2 = 1122 (korrekt), diff = 96
        ansp = aggregated["Anspruch (Leistung)"]
        assert ansp["jobcenter_ergebnis_total"] == 1026.0
        assert ansp["korrekt_total"] == 1122.0
        assert ansp["differenz_total"] == 96.0

    def test_three_different_months(self) -> None:
        """Three months with varying data."""
        m1 = self._month_items(anspruch=(500.0, 550.0))  # month 1: diff 50
        m2 = self._month_items(anspruch=(500.0, 560.0))  # month 2: diff 60
        m3 = self._month_items(anspruch=(500.0, 570.0))  # month 3: diff 70

        result = aggregate_months([m1, m2, m3])

        assert result["month_count"] == 3
        aggregated = {e["label"]: e for e in result["aggregated"]}

        ansp = aggregated["Anspruch (Leistung)"]
        assert ansp["jobcenter_ergebnis_total"] == 1500.0  # 500 * 3
        assert ansp["korrekt_total"] == 1680.0  # 550 + 560 + 570
        assert ansp["differenz_total"] == 180.0  # 50 + 60 + 70

    def test_empty_input(self) -> None:
        """Empty input returns empty aggregation."""
        result = aggregate_months([])
        assert result["month_count"] == 0
        assert result["aggregated"] == []
        assert result["total_discrepancy"] == 0.0


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
        # KdU, Einkommensanrechnung, Auszahlungsbetrag PLUS reconciliation.
        labels = [r["label"] for r in results]
        assert "Regelbedarf" in labels
        assert "Erwerbstätigenfreibetrag" in labels
        assert "Aufrechnung (Darlehen)" in labels
        assert "Kosten der Unterkunft (KdU)" in labels
        assert "Einkommensanrechnung (Brutto - Freibetrag)" in labels
        assert "Auszahlungsbetrag (Gesamt)" in labels
        # Reconciliation entries (WP-23)
        assert "Gesamtbedarf" in labels
        assert "Anrechenbares Einkommen" in labels
        assert "Anspruch (Leistung)" in labels

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
        assert len(results) >= 1
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
# Property / edge-case tests
# ---------------------------------------------------------------------------


class TestFreibetragProperties:
    """Property-style tests for the Freibetrag computation."""

    def test_bracket_continuity_at_520(self) -> None:
        """No discontinuity when crossing from 520.00 to 520.01."""
        v1 = compute_freibetrag(520.00)["value"]
        v2 = compute_freibetrag(520.01)["value"]
        # The jump should be very small (at most the rate difference at the margin).
        assert v1 is not None and v2 is not None
        diff = abs(v2 - v1)
        assert diff < 0.10  # far less than 1 EUR

    def test_bracket_continuity_at_1000(self) -> None:
        """No discontinuity when crossing from 1000.00 to 1000.01."""
        v1 = compute_freibetrag(1000.00)["value"]
        v2 = compute_freibetrag(1000.01)["value"]
        assert v1 is not None and v2 is not None
        diff = abs(v2 - v1)
        assert diff < 0.10

    def test_bracket_continuity_at_1200(self) -> None:
        """No discontinuity at the cap boundary (1200.00 → 1200.01)."""
        v1 = compute_freibetrag(1200.00)["value"]
        v2 = compute_freibetrag(1200.01)["value"]
        assert v1 is not None and v2 is not None
        # Both should be capped at the same value (or very close).
        diff = abs(v2 - v1)
        assert diff < 0.02

    def test_no_negative_freibetrag(self) -> None:
        """Freibetrag is never negative for any valid input."""
        for income in [0.0, 50.0, 100.0, 100.01, 520.0, 1000.0, 1200.0, 2000.0]:
            result = compute_freibetrag(income)
            assert result["value"] is not None
            assert result["value"] >= 0.0

    def test_rounding_is_cent_exact(self) -> None:
        """All bracket amounts are rounded to 2 decimal places."""
        for income in [123.45, 567.89, 999.99, 1001.50]:
            result = compute_freibetrag(income)
            assert result["value"] is not None
            # Check 2 decimal places.
            assert result["value"] * 100 % 1 < 0.01
            for bracket in result["brackets_applied"]:
                amount = bracket["amount"]
                assert amount * 100 % 1 < 0.01

    def test_old_brackets_property_no_negative(self) -> None:
        """Freibetrag with old brackets never negative."""
        for income in [0.0, 100.0, 500.0, 1000.0, 1200.0, 2000.0]:
            result = compute_freibetrag(income, regime="a.F._vor_2023")
            assert result["value"] is not None
            assert result["value"] >= 0.0


# ---------------------------------------------------------------------------
# supported_years
# ---------------------------------------------------------------------------


def test_supported_years() -> None:
    years = supported_years()
    assert isinstance(years, list)
    assert 2025 in years
    assert years == sorted(years)
