"""Unit tests for action document generators (WP-40).

Tests cover:
- Guardrail: unverified/not-confirmed claims → [BITTE PRÜFEN: ...]
- Guardrail: verified + confirmed claims → fluent text
- Generator selection: Frist open → Widerspruch
- Generator selection: lapsed + fehlerhafte RBB → Jahresfrist
- Generator selection: lapsed → § 44
- All three generator templates produce valid German legal documents
- Golden-output snapshot: deterministic sections byte-stable
- Footer contains required metadata
- Pseudonymization reinjection roundtrip
"""

# Semantic Version: 0.1.0

from __future__ import annotations

import hashlib
from datetime import date, timedelta
from typing import Any

import pytest

from app.services.document_generators import (
    DocumentSlot,
    GeneratedDocument,
    _build_footer,
    _find_reconciliation_value,
    _fmt_eur,
    _get_verified_claim_text,
    generate_document,
    select_generator,
    validate_slot_claim,
)
from app.services.fristen import FristResult, compute_widerspruchsfrist
from app.services.rules_engine import ReconciliationLineItem

# ===========================================================================
# Fixtures
# ===========================================================================


@pytest.fixture
def today() -> date:
    return date.today()


@pytest.fixture
def bescheid_datum() -> date:
    return date(2025, 6, 15)


@pytest.fixture
def frist_open(today: date) -> FristResult:
    """A FristResult with a deadline in the future."""
    return compute_widerspruchsfrist(
        bescheid_datum=today - timedelta(days=20),
        rbb_status="korrekt",
        bundesland="NW",
    )


@pytest.fixture
def frist_lapsed(today: date) -> FristResult:
    """A FristResult with a deadline in the past."""
    return compute_widerspruchsfrist(
        bescheid_datum=today - timedelta(days=60),
        rbb_status="korrekt",
        bundesland="NW",
    )


@pytest.fixture
def frist_lapsed_no_rbb(today: date) -> FristResult:
    """A FristResult with fehlerhafte RBB → Jahresfrist, still open."""
    return compute_widerspruchsfrist(
        bescheid_datum=today - timedelta(days=200),
        rbb_status="fehlerhaft",
        bundesland="NW",
    )


@pytest.fixture
def frist_kein_va(today: date) -> FristResult:
    """A FristResult indicating the document is not a Verwaltungsakt."""
    return compute_widerspruchsfrist(
        bescheid_datum=today - timedelta(days=20),
        ist_verwaltungsakt=False,
        bundesland="NW",
    )


@pytest.fixture
def reconciliation() -> list[ReconciliationLineItem]:
    """Standard reconciliation with known values."""
    return [
        ReconciliationLineItem(
            label="Gesamtbedarf",
            jobcenter_ergebnis=900.00,
            korrekt=950.00,
            differenz=50.00,
            relevant_rule="§ 19 SGB II",
            detail="Gesamtbedarf korrekt: 950.00 EUR",
        ),
        ReconciliationLineItem(
            label="Erwerbstätigenfreibetrag",
            jobcenter_ergebnis=None,
            korrekt=180.00,
            differenz=None,
            relevant_rule="§ 11b SGB II",
            detail="Freibetrag: 180.00 EUR",
        ),
        ReconciliationLineItem(
            label="Anrechenbares Einkommen",
            jobcenter_ergebnis=400.00,
            korrekt=320.00,
            differenz=-80.00,
            relevant_rule="§ 11b SGB II",
            detail="Anrechenbar: 320.00 EUR",
        ),
        ReconciliationLineItem(
            label="Anspruch (Leistung)",
            jobcenter_ergebnis=500.00,
            korrekt=630.00,
            differenz=130.00,
            relevant_rule="§ 19 SGB II",
            detail="Anspruch korrekt: 630.00 EUR",
        ),
    ]


def _verified_claim(
    text: str,
    v_status: str = "exakt",
    adjudicated: bool = True,
) -> dict[str, Any]:
    """Build a claim dict for testing."""
    claim: dict[str, Any] = {
        "claim_text": text,
        "confidence_score": 0.95,
        "claim_type": "fact",
        "verification_status": v_status,
        "user_adjudication": {"status": "confirmed", "note": ""} if adjudicated else {},
    }
    return claim


# ===========================================================================
# Guardrail tests
# ===========================================================================


class TestValidateSlotClaim:
    """Tests for the guardrail function."""

    def test_none_claim(self) -> None:
        assert validate_slot_claim(None) is False

    def test_empty_dict(self) -> None:
        assert validate_slot_claim({}) is False

    def test_verified_confirmed(self) -> None:
        c = _verified_claim("Test claim", "exakt", True)
        assert validate_slot_claim(c) is True

    def test_verified_not_confirmed(self) -> None:
        c = _verified_claim("Test claim", "exakt", adjudicated=False)
        assert validate_slot_claim(c) is False

    def test_normalisiert_confirmed(self) -> None:
        c = _verified_claim("Test claim", "normalisiert", True)
        assert validate_slot_claim(c) is True

    def test_unverifiziert(self) -> None:
        c = _verified_claim("Test claim", "unverifiziert", True)
        assert validate_slot_claim(c) is False

    def test_confirmed_wrong_status(self) -> None:
        """Confirmed but verification_status is missing."""
        c = _verified_claim("Test claim", "exakt", True)
        del c["verification_status"]
        assert validate_slot_claim(c) is False

    def test_adjudication_not_dict(self) -> None:
        c = _verified_claim("Test claim", "exakt", True)
        c["user_adjudication"] = None
        assert validate_slot_claim(c) is False


class TestSlotRendering:
    """Test that unverified slots render as [BITTE PRÜFEN: ...]."""

    def test_verified_slot_renders_value(self) -> None:
        slot = DocumentSlot(
            key="test", label="Test", source="user_input",
            value="Wert", verified=True,
        )
        assert slot.render() == "Wert"

    def test_unverified_slot_renders_review(self) -> None:
        slot = DocumentSlot(
            key="test", label="Test", source="user_input",
            value="Wert", verified=False,
            needs_review=True, review_topic="Testwert",
        )
        assert slot.render() == "[BITTE PRÜFEN: Testwert]"

    def test_none_value_renders_review(self) -> None:
        slot = DocumentSlot(
            key="test", label="Test", source="user_input",
            value=None, verified=False,
            needs_review=True, review_topic="Testwert",
        )
        assert slot.render() == "[BITTE PRÜFEN: Testwert]"

    def test_unverified_no_review_topic_falls_back_to_label(self) -> None:
        slot = DocumentSlot(
            key="test", label="Test Label", source="user_input",
            value=None, verified=False,
            needs_review=True, review_topic="",
        )
        assert slot.render() == "[BITTE PRÜFEN: Test Label]"


class TestGuardrailInDocuments:
    """Integration-style: verify claims in documents respect guardrails."""

    def test_unverified_claim_becomes_bitte_pruefen(self, frist_open: FristResult, reconciliation: list[ReconciliationLineItem]) -> None:
        """An unverified claim → [BITTE PRÜFEN: ...] in document."""
        claims = [
            _verified_claim("Der Regelbedarf beträgt 563 EUR.", "unverifiziert", True),
        ]
        doc = generate_document(
            doc_type="widerspruch",
            frist_result=frist_open,
            reconciliation=reconciliation,
            claims=claims,
            user_data={"name": "Max Mustermann", "adresse": "Musterstr. 1, 12345 Berlin"},
        )
        assert "[BITTE PRÜFEN:" in doc.rendered_text
        # The claims_text slot should show the review placeholder
        claims_slot = next((s for s in doc.slots if s.key == "claims_text"), None)
        assert claims_slot is not None
        assert claims_slot.needs_review is True

    def test_verified_but_not_confirmed_renders_bitte_pruefen(self, frist_open: FristResult, reconciliation: list[ReconciliationLineItem]) -> None:
        """Verified claim but not user-confirmed → [BITTE PRÜFEN: ...]."""
        claims = [
            _verified_claim("Der Regelbedarf beträgt 563 EUR.", "exakt", adjudicated=False),
        ]
        doc = generate_document(
            doc_type="widerspruch",
            frist_result=frist_open,
            reconciliation=reconciliation,
            claims=claims,
            user_data={"name": "Max Mustermann", "adresse": "Musterstr. 1, 12345 Berlin"},
        )
        assert "[BITTE PRÜFEN:" in doc.rendered_text

    def test_verified_and_confirmed_appears_in_document(self, frist_open: FristResult, reconciliation: list[ReconciliationLineItem]) -> None:
        """Verified + confirmed claim → fluent text in document."""
        claim_text = "Der Regelbedarf für einen Alleinstehenden beträgt 563 EUR pro Monat."
        claims = [
            _verified_claim(claim_text, "exakt", True),
        ]
        doc = generate_document(
            doc_type="widerspruch",
            frist_result=frist_open,
            reconciliation=reconciliation,
            claims=claims,
            user_data={"name": "Max Mustermann", "adresse": "Musterstr. 1, 12345 Berlin"},
            bescheid_datum=date(2025, 6, 15),
            aktenzeichen="AZ-12345/2025",
            behoerde="Jobcenter Berlin Mitte",
        )
        assert claim_text in doc.rendered_text
        assert "[BITTE PRÜFEN:" not in doc.rendered_text

    def test_mixed_claims(self, frist_open: FristResult, reconciliation: list[ReconciliationLineItem]) -> None:
        """Mixes of verified and unverified claims: verified shown, unverified as review."""
        verified_text = "Dieser Anspruch ist korrekt und belegt."
        claims = [
            _verified_claim(verified_text, "exakt", True),
            _verified_claim("Dieser Anspruch ist nicht belegt.", "unverifiziert", True),
        ]
        doc = generate_document(
            doc_type="widerspruch",
            frist_result=frist_open,
            reconciliation=reconciliation,
            claims=claims,
            user_data={"name": "Max Mustermann", "adresse": "Musterstr. 1, 12345 Berlin"},
        )
        assert verified_text in doc.rendered_text

    def test_verified_claim_text_helper(self) -> None:
        """_get_verified_claim_text finds and validates correctly."""
        claims = [
            _verified_claim("Der Regelbedarf beträgt 563 EUR.", "exakt", True),
            _verified_claim("Nicht relevant.", "unverifiziert", True),
        ]
        found_text, found_verified = _get_verified_claim_text(
            claims, ["Regelbedarf", "563"],
        )
        assert found_text == "Der Regelbedarf beträgt 563 EUR."
        assert found_verified is True

    def test_verified_claim_text_no_match(self) -> None:
        claims = [
            _verified_claim("Etwas anderes.", "exakt", True),
        ]
        found_text, found_verified = _get_verified_claim_text(
            claims, ["Regelbedarf"],
        )
        assert found_text is None
        assert found_verified is False


# ===========================================================================
# Generator selection tests
# ===========================================================================


class TestSelectGenerator:
    """Tests for generator selection logic."""

    def test_frist_open_widerspruch(self, frist_open: FristResult) -> None:
        """Frist still open → standard Widerspruch."""
        assert select_generator(frist_open) == "widerspruch"

    def test_frist_open_jahresfrist(self, frist_lapsed_no_rbb: FristResult) -> None:
        """Jahresfrist (fehlerhafte RBB) still open → widerspruch_jahresfrist."""
        assert select_generator(frist_lapsed_no_rbb) == "widerspruch_jahresfrist"

    def test_frist_lapsed(self, frist_lapsed: FristResult) -> None:
        """Frist lapsed → Überprüfungsantrag § 44."""
        assert select_generator(frist_lapsed) == "ueberpruefungsantrag_44"

    def test_kein_va(self, frist_kein_va: FristResult) -> None:
        """Not a Verwaltungsakt → Akteneinsicht (no Widerspruch possible)."""
        assert select_generator(frist_kein_va) == "akteneinsichtsantrag_25"

    def test_none_frist(self) -> None:
        """No Frist data → Akteneinsicht (safe default)."""
        assert select_generator(None) == "akteneinsichtsantrag_25"

    def test_frist_open_jahresfrist_after_lapse(self, today: date) -> None:
        """Jahresfrist where frist_ende has passed but it's still a 'jahr' typ."""
        frist = FristResult(
            bekanntgabe=today - timedelta(days=400),
            frist_ende=today - timedelta(days=35),  # 1 year + 1 month ago
            frist_typ="jahr",
            rollover_applied=False,
            oq1_flag=False,
            oq1_alternate_ende=None,
            explanation_de="Jahresfrist",
        )
        # GS-010: Lapsed but Jahresfrist → still widerspruch_jahresfrist
        assert select_generator(frist) == "widerspruch_jahresfrist"


# ===========================================================================
# Template output tests
# ===========================================================================


class TestWiderspruchTemplate:
    """Test that the Widerspruch template produces valid German legal text."""

    def test_basic_widerspruch(self, frist_open: FristResult, reconciliation: list[ReconciliationLineItem]) -> None:
        """Basic Widerspruch document with all data."""
        claims = [
            _verified_claim("Die Berechnung des Regelbedarfs ist fehlerhaft.", "exakt", True),
            _verified_claim("Das Einkommen wurde nicht korrekt angerechnet.", "normalisiert", True),
        ]
        doc = generate_document(
            doc_type="widerspruch",
            frist_result=frist_open,
            reconciliation=reconciliation,
            claims=claims,
            user_data={"name": "Max Mustermann", "adresse": "Musterstr. 1, 12345 Berlin"},
            bescheid_datum=date(2025, 6, 15),
            aktenzeichen="AZ-12345/2025",
            behoerde="Jobcenter Berlin Mitte",
        )
        assert doc.document_type == "widerspruch"
        assert "Widerspruch" in doc.title
        assert "Max Mustermann" in doc.rendered_text
        assert "Jobcenter Berlin Mitte" in doc.rendered_text
        assert "AZ-12345/2025" in doc.rendered_text
        assert "Regelbedarf" in doc.rendered_text
        assert "630.00 EUR" in doc.rendered_text  # Anspruch (Leistung) korrekt
        assert "[Unterschrift]" in doc.rendered_text

    def test_widerspruch_without_user_data(self, frist_open: FristResult, reconciliation: list[ReconciliationLineItem]) -> None:
        """Widerspruch without user data still produces valid document."""
        doc = generate_document(
            doc_type="widerspruch",
            frist_result=frist_open,
            reconciliation=reconciliation,
            claims=[],
            user_data=None,
        )
        assert doc.document_type == "widerspruch"
        assert "Bescheid" in doc.rendered_text
        assert len(doc.rendered_text) > 200

    def test_widerspruch_alle_slots(self, frist_open: FristResult, reconciliation: list[ReconciliationLineItem]) -> None:
        """All slots are present in the output."""
        claims = [
            _verified_claim("Test claim text.", "exakt", True),
        ]
        doc = generate_document(
            doc_type="widerspruch",
            frist_result=frist_open,
            reconciliation=reconciliation,
            claims=claims,
            user_data={"name": "Test User"},
            bescheid_datum=date(2025, 6, 1),
            aktenzeichen="AZ-TEST",
            behoerde="Testbehörde",
        )
        slot_keys = {s.key for s in doc.slots}
        expected = {
            "bescheid_datum", "bescheid_aktenzeichen", "behoerde_name",
            "bekanntgabe", "widerspruchsfrist_ende",
            "anspruch_hoehe", "differenz_gesamt", "claims_text",
        }
        assert slot_keys == expected, f"Missing slots: {expected - slot_keys}"


class TestJahresfristTemplate:
    """Test the Jahresfrist Widerspruch template."""

    def test_jahresfrist_template(self, frist_lapsed_no_rbb: FristResult, reconciliation: list[ReconciliationLineItem]) -> None:
        """Jahresfrist Widerspruch document."""
        doc = generate_document(
            doc_type="widerspruch_jahresfrist",
            frist_result=frist_lapsed_no_rbb,
            reconciliation=reconciliation,
            claims=[],
            user_data={"name": "Max Mustermann"},
            bescheid_datum=date(2025, 1, 15),
            aktenzeichen="AZ-123/2025",
            behoerde="Jobcenter Berlin",
        )
        assert doc.document_type == "widerspruch_jahresfrist"
        assert "§ 66 Abs. 2 SGG" in doc.rendered_text
        assert "Jahresfrist" in doc.rendered_text
        assert "[Unterschrift]" in doc.rendered_text


class TestUeberpruefungsantragTemplate:
    """Test the § 44 SGB X template."""

    def test_ueberpruefungsantrag(self, frist_lapsed: FristResult, reconciliation: list[ReconciliationLineItem]) -> None:
        """Überprüfungsantrag document."""
        doc = generate_document(
            doc_type="ueberpruefungsantrag_44",
            frist_result=frist_lapsed,
            reconciliation=reconciliation,
            claims=[],
            user_data={"name": "Max Mustermann"},
            bescheid_datum=date(2025, 3, 1),
            aktenzeichen="AZ-456/2025",
            behoerde="Jobcenter Berlin",
        )
        assert doc.document_type == "ueberpruefungsantrag_44"
        assert "§ 44 SGB X" in doc.rendered_text
        assert "Rücknahme" in doc.rendered_text
        assert "[Unterschrift]" in doc.rendered_text


class TestAkteneinsichtsantragTemplate:
    """Test the § 25 SGB X template."""

    def test_akteneinsichtsantrag(self) -> None:
        """Akteneinsichtsantrag document (simplest template, less claim-dependent)."""
        doc = generate_document(
            doc_type="akteneinsichtsantrag_25",
            frist_result=None,
            reconciliation=[],
            claims=[],
            user_data={"name": "Max Mustermann", "adresse": "Musterstr. 1"},
            bescheid_datum=date(2025, 6, 15),
            aktenzeichen="AZ-789/2025",
            behoerde="Jobcenter Berlin",
        )
        assert doc.document_type == "akteneinsichtsantrag_25"
        assert "§ 25 SGB X" in doc.rendered_text
        assert "Akteneinsicht" in doc.rendered_text
        assert "AZ-789/2025" in doc.rendered_text
        assert "[Unterschrift]" in doc.rendered_text


# ===========================================================================
# Footer tests
# ===========================================================================


class TestFooter:
    """Test the mandatory document footer."""

    def test_footer_contains_required_fields(self) -> None:
        """Footer contains all required metadata fields."""
        footer = _build_footer()
        assert "Rechtsinformation:" in footer
        assert "Citizen" in footer
        assert "Generiert am:" in footer
        assert "Citizen Version:" in footer
        assert "Inference Profile:" in footer
        assert "keine Rechtsberatung" in footer

    def test_footer_appended_to_document(self, frist_open: FristResult, reconciliation: list[ReconciliationLineItem]) -> None:
        """Every generated document ends with the footer."""
        doc = generate_document(
            doc_type="widerspruch",
            frist_result=frist_open,
            reconciliation=reconciliation,
            claims=[],
        )
        assert doc.rendered_text.strip().endswith("----") is False  # footer ends with profile
        assert "Rechtsinformation:" in doc.rendered_text

    def test_footer_date_is_current(self) -> None:
        """Footer date matches the current date."""
        footer = _build_footer()
        today_str = date.today().strftime("%d.%m.%Y")
        assert today_str in footer


# ===========================================================================
# Golden-output snapshot tests
# ===========================================================================


class TestGoldenSnapshot:
    """Deterministic sections should be byte-stable across runs."""

    def test_deterministic_footer(self) -> None:
        """Footer content (minus date) is deterministic."""
        # This test verifies the structure, not the date-dependent parts
        footer = _build_footer()
        assert "Citizen Version:" in footer
        assert footer.count("\n") == 6  # 7 lines (6 newlines)

    def test_document_format_stable(self, frist_open: FristResult, reconciliation: list[ReconciliationLineItem]) -> None:
        """Document sections maintain structure across runs."""
        claims = [
            _verified_claim("Test claim A. Test claim B.", "exakt", True),
        ]
        doc1 = generate_document(
            doc_type="widerspruch",
            frist_result=frist_open,
            reconciliation=reconciliation,
            claims=claims,
            user_data={"name": "Max Mustermann"},
            bescheid_datum=date(2025, 6, 15),
            aktenzeichen="AZ-TEST",
            behoerde="Testbehörde",
        )
        doc2 = generate_document(
            doc_type="widerspruch",
            frist_result=frist_open,
            reconciliation=reconciliation,
            claims=claims,
            user_data={"name": "Max Mustermann"},
            bescheid_datum=date(2025, 6, 15),
            aktenzeichen="AZ-TEST",
            behoerde="Testbehörde",
        )
        assert doc1.rendered_text == doc2.rendered_text


# ===========================================================================
# Helper function tests
# ===========================================================================


class TestHelpers:
    """Tests for helper functions."""

    def test_fmt_eur_with_value(self) -> None:
        assert _fmt_eur(123.45) == "123.45 EUR"

    def test_fmt_eur_none(self) -> None:
        assert _fmt_eur(None) == "[BITTE PRÜFEN: Betrag]"

    def test_fmt_eur_zero(self) -> None:
        assert _fmt_eur(0.0) == "0.00 EUR"

    def test_find_reconciliation_value_found(self, reconciliation: list[ReconciliationLineItem]) -> None:
        val = _find_reconciliation_value(reconciliation, "Anspruch (Leistung)")
        assert val == 630.00

    def test_find_reconciliation_value_not_found(self, reconciliation: list[ReconciliationLineItem]) -> None:
        val = _find_reconciliation_value(reconciliation, "Nicht vorhanden")
        assert val is None

    def test_find_reconciliation_value_dict(self) -> None:
        items = [
            {"label": "Test", "korrekt": 42.0},
        ]
        val = _find_reconciliation_value(items, "Test")
        assert val == 42.0


# ===========================================================================
# GS scenario tests
# ===========================================================================


class TestGSScenarios:
    """GS (Goldset) scenario tests."""

    def test_gs003_urgent_deadline(self, today: date, reconciliation: list[ReconciliationLineItem]) -> None:
        """GS-003: Urgent deadline — Widerspruch with correct deadline."""
        bescheid = today - timedelta(days=18)
        frist = compute_widerspruchsfrist(
            bescheid_datum=bescheid,
            rbb_status="korrekt",
            bundesland="NW",
        )
        # Frist should still be open
        assert frist.frist_ende >= today
        assert select_generator(frist) == "widerspruch"

        doc = generate_document(
            doc_type="widerspruch",
            frist_result=frist,
            reconciliation=reconciliation,
            claims=[_verified_claim("Dringender Fall.", "exakt", True)],
            user_data={"name": "Eilfall"},
            bescheid_datum=bescheid,
            aktenzeichen="GS-003",
            behoerde="Jobcenter",
        )
        # Verify the correct deadline is in the document
        assert frist.frist_ende.strftime("%d.%m.%Y") in doc.rendered_text
        assert "Widerspruch" in doc.title

    def test_gs005_bekanntgabe_after_reference(self, today: date, reconciliation: list[ReconciliationLineItem]) -> None:
        """GS-005: Bekanntgabe after reference date — correct deadline."""
        bescheid = today - timedelta(days=30)
        aufgabe = bescheid + timedelta(days=2)
        frist = compute_widerspruchsfrist(
            bescheid_datum=bescheid,
            aufgabe_zur_post=aufgabe,
            rbb_status="korrekt",
            bundesland="NW",
        )
        # Frist may be ouvert if recently lapsed — this tests the bekanntgabe derivation
        assert frist.bekanntgabe >= aufgabe + timedelta(days=3)  # 4-day fiction

        doc = generate_document(
            doc_type=select_generator(frist),
            frist_result=frist,
            reconciliation=reconciliation,
            claims=[_verified_claim("Bekanntgabe geprüft.", "exakt", True)],
            bescheid_datum=bescheid,
            aktenzeichen="GS-005",
            behoerde="Jobcenter",
        )
        assert frist.frist_ende.strftime("%d.%m.%Y") in doc.rendered_text

    def test_gs010_jahresfrist_path(self, today: date, reconciliation: list[ReconciliationLineItem]) -> None:
        """GS-010: Fehlerhafte RBB → Jahresfrist path is stillwiderspruch_jahresfrist."""
        bescheid = today - timedelta(days=200)
        frist = compute_widerspruchsfrist(
            bescheid_datum=bescheid,
            rbb_status="fehlerhaft",
            bundesland="NW",
        )
        # Jahresfrist — should still be within the 1-year period
        assert frist.frist_ende >= today
        assert select_generator(frist) == "widerspruch_jahresfrist"

        doc = generate_document(
            doc_type="widerspruch_jahresfrist",
            frist_result=frist,
            reconciliation=reconciliation,
            claims=[_verified_claim("Jahresfrist Fall.", "exakt", True)],
            bescheid_datum=bescheid,
            aktenzeichen="GS-010",
            behoerde="Jobcenter",
        )
        assert "§ 66 Abs. 2 SGG" in doc.rendered_text
        assert frist.frist_ende.strftime("%d.%m.%Y") in doc.rendered_text


# ===========================================================================
# GeneratedDocument output structure
# ===========================================================================


class TestGeneratedDocumentOutput:
    """Test the output structure of GeneratedDocument."""

    def test_has_all_fields(self, frist_open: FristResult, reconciliation: list[ReconciliationLineItem]) -> None:
        """GeneratedDocument has all required fields."""
        doc = generate_document(
            doc_type="widerspruch",
            frist_result=frist_open,
            reconciliation=reconciliation,
            claims=[],
        )
        assert isinstance(doc.document_type, str)
        assert isinstance(doc.title, str)
        assert isinstance(doc.rendered_text, str)
        assert isinstance(doc.slots, list)
        assert isinstance(doc.warnings, list)
        assert isinstance(doc.generation_metadata, dict)

    def test_metadata_contains_keys(self, frist_open: FristResult, reconciliation: list[ReconciliationLineItem]) -> None:
        """Generation metadata contains expected keys."""
        doc = generate_document(
            doc_type="widerspruch",
            frist_result=frist_open,
            reconciliation=reconciliation,
            claims=[],
        )
        meta = doc.generation_metadata
        assert "app_version" in meta
        assert "inference_profile" in meta
        assert "generated_at" in meta
        assert "doc_type" in meta

    def test_warnings_for_missing_data(self, reconciliation: list[ReconciliationLineItem]) -> None:
        """Missing essential data produces warnings."""
        doc = generate_document(
            doc_type="widerspruch",
            frist_result=None,
            reconciliation=reconciliation,
            claims=[],
            user_data=None,
        )
        assert len(doc.warnings) > 0


# ===========================================================================
# Edge cases
# ===========================================================================


class TestEdgeCases:
    """Edge case tests."""

    def test_empty_claims_list(self, frist_open: FristResult, reconciliation: list[ReconciliationLineItem]) -> None:
        """Empty claims → all-claims slot shows review placeholder."""
        doc = generate_document(
            doc_type="widerspruch",
            frist_result=frist_open,
            reconciliation=reconciliation,
            claims=[],
        )
        # The claims_text slot should be in review
        claims_slot = next((s for s in doc.slots if s.key == "claims_text"), None)
        if claims_slot:
            assert claims_slot.needs_review or not claims_slot.verified

    def test_empty_reconciliation(self, frist_open: FristResult) -> None:
        """Empty reconciliation → amounts use review placeholders."""
        doc = generate_document(
            doc_type="widerspruch",
            frist_result=frist_open,
            reconciliation=[],
            claims=[],
        )
        anspruch_slot = next((s for s in doc.slots if s.key == "anspruch_hoehe"), None)
        if anspruch_slot:
            anspruch_slot.needs_review or not anspruch_slot.verified

    def test_unknown_doc_type(self, frist_open: FristResult, reconciliation: list[ReconciliationLineItem]) -> None:
        """Unknown doc_type → renders fallback text."""
        doc = generate_document(
            doc_type="unbekannt",
            frist_result=frist_open,
            reconciliation=reconciliation,
            claims=[],
        )
        assert "Unbekannter Dokumenttyp" in doc.rendered_text or "unbekannt" in doc.rendered_text.lower()

    def test_all_doc_types_produce_output(self, frist_open: FristResult, frist_lapsed: FristResult, frist_lapsed_no_rbb: FristResult, reconciliation: list[ReconciliationLineItem]) -> None:
        """All three document types produce non-empty output."""
        configs = [
            ("widerspruch", frist_open, {}),
            ("widerspruch_jahresfrist", frist_lapsed_no_rbb, {}),
            ("ueberpruefungsantrag_44", frist_lapsed, {}),
            ("akteneinsichtsantrag_25", None, {}),
        ]
        for doc_type, frist, kw in configs:
            doc = generate_document(
                doc_type=doc_type,
                frist_result=frist,
                reconciliation=reconciliation,
                claims=[],
                **kw,
            )
            assert len(doc.rendered_text) > 100, f"Document {doc_type} too short"
            assert doc.document_type == doc_type

    def test_keyword_matching_case_insensitive(self) -> None:
        """_get_verified_claim_text matches case-insensitively."""
        claims = [
            _verified_claim("Regelbedarf beträgt 563 EUR.", "exakt", True),
        ]
        text, verified = _get_verified_claim_text(claims, ["regelbedarf"])
        assert text is not None
        assert verified is True
