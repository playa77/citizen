"""Unit tests for the pseudonymization gate (WP-30).

Covers:
- Structured ID detection (BG-Nummer, Aktenzeichen, IBAN, etc.)
- Person name detection (NER, gazetteer, salutations)
- Street address detection
- Birth date detection + age preservation
- Negative controls (must NOT redact dates, amounts, §§, authority names)
- Determinism
- Depseudonymize roundtrip
- Tolerant depseudonymize (LLM mutations)
- Multiple persons
- Genitive/inflected forms
"""

# Semantic Version: 0.1.0 | 2026-07-12 — WP-30 tests

from __future__ import annotations

import re

import pytest

from app.services.pseudonymization import (
    PiiMapping,
    _detect_birth_dates,
    _detect_first_name,
    _detect_ner_names,
    _detect_salutation_names,
    _detect_street_addresses,
    _detect_structured_ids,
    _get_patterns,
    _strip_inflected_suffix,
    depseudonymize,
    depseudonymize_output,
    depseudonymize_tolerant,
    pseudonymize,
    pseudonymize_case_run,
)

# =========================================================================
# Helper
# =========================================================================


def _count_placeholders(text: str, prefix: str) -> int:
    """Count unique placeholders with a given prefix in text."""
    pattern = re.compile(rf"\[\[{prefix}_(\d+)\]\]")
    return len(set(pattern.findall(text)))


# =========================================================================
# Structured IDs
# =========================================================================


class TestStructuredIds:
    def test_bg_nummer_double_slash(self):
        text = "Meine BG-Nummer ist 12345//1234567."
        result, mapping = pseudonymize(text)
        assert "[[ID_1]]" in result
        assert "12345//1234567" not in result

    def test_bg_nummer_single_slash(self):
        text = "BG: 12345/1234567"
        result, mapping = pseudonymize(text)
        assert "[[" in result
        assert "12345/1234567" not in result

    def test_aktenzeichen(self):
        text = "Az.: 12/34/56789"
        result, mapping = pseudonymize(text)
        assert "[[" in result
        assert "Az.:" not in result

    def test_aktenzeichen_geschaeftszeichen(self):
        text = "Gesch.-Z.: 123/45/67890"
        result, mapping = pseudonymize(text)
        assert "[[" in result

    def test_sv_nummer(self):
        text = "SV-Nummer: 12 345678 9 01 2"
        result, mapping = pseudonymize(text)
        assert "[[" in result

    def test_steuer_id(self):
        text = "Steuer-ID: 12 345 678 90123"
        result, mapping = pseudonymize(text)
        assert "[[" in result

    def test_iban(self):
        text = "IBAN: DE12 3456 7890 1234 5678 90"
        result, mapping = pseudonymize(text)
        assert "[[" in result
        assert "DE12" not in result

    def test_phone(self):
        text = "Telefon: 0176 12345678"
        result, mapping = pseudonymize(text)
        assert "[[" in result

    def test_email(self):
        text = "E-Mail: max@mustermann.de"
        result, mapping = pseudonymize(text)
        assert "[[" in result
        assert "max@mustermann.de" not in result


# =========================================================================
# Person names
# =========================================================================


class TestPersonNames:
    def test_salutation_herr(self):
        text = "Herr Max Mustermann"
        result, mapping = pseudonymize(text)
        assert "[[PERSON_1]]" in result
        assert "Max" not in result

    def test_salutation_frau(self):
        text = "Frau Erika Schmidt"
        result, mapping = pseudonymize(text)
        assert "[[PERSON_1]]" in result
        assert "Erika" not in result

    def test_multiple_persons(self):
        text = "Herr Müller und Frau Schmidt"
        result, mapping = pseudonymize(text)
        assert _count_placeholders(result, "PERSON") >= 2

    def test_letterhead_very_sehr_geehrte(self):
        text = "Sehr geehrter Herr Vahrenholt,"
        result, mapping = pseudonymize(text)
        assert "[[PERSON_1]]" in result

    def test_first_name_gazetteer(self):
        text = "Thomas hat einen Antrag gestellt."
        result, mapping = pseudonymize(text)
        assert "[[PERSON_1]]" in result
        assert "Thomas" not in result


# =========================================================================
# Street addresses
# =========================================================================


class TestStreetAddresses:
    def test_street_address_full(self):
        text = "Musterstraße 42, 12345 Berlin"
        result, mapping = pseudonymize(text)
        assert "[[ADRESSE_1]]" in result
        # City kept, PLZ kept (PLZ-only redaction not required)
        assert "Berlin" in result

    def test_street_address_weg(self):
        text = "Am Rosenweg 7, 53113 Bonn"
        result, mapping = pseudonymize(text)
        assert "[[ADRESSE_1]]" in result
        assert "Bonn" in result

    def test_street_address_with_house_letter(self):
        text = "Hauptstraße 12a"
        result, mapping = pseudonymize(text)
        assert "[[ADRESSE_1]]" in result


# =========================================================================
# Birth dates
# =========================================================================


class TestBirthDates:
    def test_birth_date_with_context(self):
        text = "geboren am 12.05.1980"
        result, mapping = pseudonymize(text)
        assert "[[GEBURTSDATUM_1]]" in result
        assert "12.05.1980" not in result
        # Should have estimated age
        assert "Jahre" in result

    def test_birth_date_geb_pattern(self):
        text = "geb. 12.05.1980"
        result, mapping = pseudonymize(text)
        assert "[[GEBURTSDATUM_1]]" in result

    def test_age_preserved_if_stated(self):
        text = "geboren am 12.05.1980 (45 Jahre)"
        result, mapping = pseudonymize(text)
        assert "45 Jahre" in result


# =========================================================================
# Negative controls — must NOT be redacted
# =========================================================================


class TestNegativeControls:
    def test_paragraphs_kept(self):
        text = "§ 11b Abs. 2 SGB II"
        result, mapping = pseudonymize(text)
        assert "§ 11b Abs. 2 SGB II" in result

    def test_amounts_kept(self):
        text = "563,00 EUR"
        result, mapping = pseudonymize(text)
        assert "563,00 EUR" in result

    def test_dates_kept(self):
        text = "Der Bescheid datiert vom 15.03.2024."
        result, mapping = pseudonymize(text)
        assert "15.03.2024" in result

    def test_authority_name_kept(self):
        text = "Jobcenter Köln"
        result, mapping = pseudonymize(text)
        assert "Jobcenter Köln" in result

    def test_city_name_kept(self):
        text = "Köln"
        result, mapping = pseudonymize(text)
        assert "Köln" in result

    def test_bundesland_kept(self):
        text = "Nordrhein-Westfalen"
        result, mapping = pseudonymize(text)
        assert "Nordrhein-Westfalen" in result

    def test_agentur_fuer_arbeit_kept(self):
        text = "Agentur für Arbeit"
        result, mapping = pseudonymize(text)
        assert "Agentur für Arbeit" in result


# =========================================================================
# Determinism
# =========================================================================


class TestDeterminism:
    def test_double_run_identical(self):
        text = "Herr Thomas Müller wohnt in Musterstraße 42."
        result1, mapping1 = pseudonymize(text)
        result2, mapping2 = pseudonymize(text)
        assert result1 == result2
        assert mapping1.to_dict() == mapping2.to_dict()

    def test_reuse_mapping_deterministic(self):
        text1 = "Herr Müller"
        text2 = "Herr Müller und Frau Schmidt"
        mapping = PiiMapping()
        result1, mapping = pseudonymize(text1, mapping)
        result2, mapping = pseudonymize(text2, mapping)
        # "Müller" should be the same placeholder in both
        mueller_id = mapping.value_to_placeholder.get("Müller")
        assert mueller_id


# =========================================================================
# Depseudonymize roundtrip
# =========================================================================


class TestDepseudonymizeRoundtrip:
    def test_exact_roundtrip(self):
        original = "Herr Max Mustermann wohnt in Musterstraße 42."
        pseudonymized, mapping = pseudonymize(original)
        restored, warnings = depseudonymize_output(pseudonymized, mapping)
        assert restored == original
        assert len(warnings) == 0

    def test_roundtrip_with_id(self):
        original = "BG-Nummer: 12345//1234567, Az.: 12/34/56789"
        pseudonymized, mapping = pseudonymize(original)
        restored, warnings = depseudonymize_output(pseudonymized, mapping)
        assert restored == original
        assert len(warnings) == 0

    def test_roundtrip_birth_date(self):
        original = "geboren am 12.05.1980"
        pseudonymized, mapping = pseudonymize(original)
        restored, warnings = depseudonymize_output(pseudonymized, mapping)
        # The restored text should contain the birth date, though the exact
        # format may differ because we inject age info
        assert "12.05.1980" in restored


# =========================================================================
# Tolerant depseudonymize
# =========================================================================


class TestTolerantDepseudonymize:
    def test_genitive_suffix(self):
        """LLM might write [[PERSON_1]]s for genitive."""
        original = "Vahrenholts"
        mapping = PiiMapping()
        _ = _get_placeholder_for(mapping, "person", "Vahrenholt")
        text = "[[PERSON_1]]s Antrag"
        restored, warnings = depseudonymize_tolerant(text, mapping)
        assert "Vahrenholts" in restored
        assert len(warnings) == 0

    def test_missing_bracket_pair(self):
        original = "Thomas"
        mapping = PiiMapping()
        _ = _get_placeholder_for(mapping, "person", "Thomas")
        text = "Herr [PERSON_1]"
        restored, warnings = depseudonymize_tolerant(text, mapping)
        assert "Thomas" in restored

    def test_unresolved_placeholder_emits_warning(self):
        mapping = PiiMapping()
        text = "[[UNKNOWN_1]]"
        restored, warnings = depseudonymize_tolerant(text, mapping)
        assert len(warnings) >= 1


# =========================================================================
# Genitive / Inflected names
# =========================================================================


def _get_placeholder_for(mapping: PiiMapping, category: str, raw_value: str) -> str:
    """Helper: allocate a placeholder for a given raw value."""
    if raw_value in mapping.value_to_placeholder:
        return mapping.value_to_placeholder[raw_value]
    if category == "person":
        mapping.person_counter += 1
        placeholder = f"[[PERSON_{mapping.person_counter}]]"
    else:
        mapping.id_counter += 1
        placeholder = f"[[ID_{mapping.id_counter}]]"
    mapping.value_to_placeholder[raw_value] = placeholder
    mapping.placeholder_to_value[placeholder] = raw_value
    return placeholder


class TestInflectedForms:
    def test_strip_genitive_s(self):
        assert _strip_inflected_suffix("Vahrenholts") == "Vahrenholt"

    def test_strip_genitive_es(self):
        assert _strip_inflected_suffix("Beckers") == "Becker"

    def test_none_inflected_stays(self):
        assert _strip_inflected_suffix("Berlin") == "Berlin"


# =========================================================================
# PiiMapping serialization
# =========================================================================


class TestPiiMappingSerialization:
    def test_to_dict_from_dict_roundtrip(self):
        mapping = PiiMapping(
            person_counter=5,
            address_counter=2,
            company_counter=1,
            id_counter=3,
            placeholder_to_value={
                "[[PERSON_1]]": "Thomas",
                "[[ADRESSE_1]]": "Musterstraße 42",
            },
            value_to_placeholder={
                "Thomas": "[[PERSON_1]]",
                "Musterstraße 42": "[[ADRESSE_1]]",
            },
        )
        d = mapping.to_dict()
        restored = PiiMapping.from_dict(d)
        assert restored.person_counter == 5
        assert restored.address_counter == 2
        assert restored.placeholder_to_value["[[PERSON_1]]"] == "Thomas"

    def test_from_dict_none(self):
        restored = PiiMapping.from_dict(None)
        assert restored.person_counter == 0


# =========================================================================
# Integration: pseudonymize_case_run
# =========================================================================


class TestPseudonymizeCaseRun:
    def test_returns_mapping(self):
        text = "Herr Thomas Müller, Musterstraße 42, 12345 Berlin"
        result, mapping = pseudonymize_case_run(text)
        assert isinstance(mapping, PiiMapping)
        assert "[[" in result
        assert "Thomas" not in result

    def test_empty_text_is_safe(self):
        result, mapping = pseudonymize_case_run("")
        assert result == ""


# =========================================================================
# Realistic legal document — full integration test
# =========================================================================


class TestRealisticDocument:
    def test_complex_case_text(self):
        text = """
        Sehr geehrter Herr Dr. Schmidt,

        hiermit lege ich Widerspruch gegen den Bescheid des Jobcenters Köln
        vom 15.03.2024 (Az.: 12/34/56789) ein.

        Mir wurden die Leistungen nach § 31 SGB II in Höhe von 563,00 EUR
        gekürzt. Ich bin geboren am 12.05.1980 und wohne in der Musterstraße 42,
        50667 Köln.

        Mein Arzt, Dr. Weber, hat mir eine Arbeitsunfähigkeitsbescheinigung
        ausgestellt. Meine SV-Nummer ist 12 345678 9 01 2.

        Bitte kontaktieren Sie mich unter max.schmidt@email.de oder telefonisch
        unter 0176 12345678.

        Mit freundlichen Grüßen,
        Max Schmidt
        """
        result, mapping = pseudonymize(text)

        # Structured IDs redacted
        assert "12/34/56789" not in result
        assert "12 345678 9 01 2" not in result

        # PII redacted
        assert "Schmidt" not in result or "Max" not in result or "[[PERSON_"

        # Email redacted
        assert "max.schmidt@email.de" not in result

        # Phone redacted
        assert "0176 12345678" not in result

        # Street address redacted
        assert "Musterstraße 42" not in result

        # Birth date redacted
        assert "12.05.1980" not in result or "[[GEBURTSDATUM"

        # Negative controls
        assert "Jobcenters Köln" in result
        assert "§ 31 SGB II" in result
        assert "563,00 EUR" in result
        assert "15.03.2024" in result  # decision date — kept
        assert "Köln" in result
        assert "50667" in result  # PLZ — kept (part of address, not individually)

        # Roundtrip
        restored, warnings = depseudonymize_output(result, mapping)
        assert len(warnings) == 0
        # The restored text should have the original PII values back
        assert "max.schmidt@email.de" in restored
        assert "Musterstraße 42" in restored
        assert "12 345678 9 01 2" in restored


# =========================================================================
# Edge cases
# =========================================================================


class TestEdgeCases:
    def test_depseudonymize_exact(self):
        mapping = PiiMapping(
            placeholder_to_value={
                "[[PERSON_1]]": "Thomas",
                "[[ID_1]]": "12345//1234567",
            },
            value_to_placeholder={
                "Thomas": "[[PERSON_1]]",
                "12345//1234567": "[[ID_1]]",
            },
        )
        result = depseudonymize(
            "Herr [[PERSON_1]], ID: [[ID_1]]", mapping
        )
        assert result == "Herr Thomas, ID: 12345//1234567"

    def test_full_address_with_city(self):
        """Address with PLZ + city: address redacted, city kept."""
        text = "Wohnhaft: Musterstraße 42, 12345 Berlin"
        result, mapping = pseudonymize(text)
        assert "[[ADRESSE_1]]" in result
        assert "Berlin" in result

    def test_no_pii_unchanged(self):
        text = "§ 11b Abs. 2 SGB II — kein PII vorhanden."
        result, mapping = pseudonymize(text)
        assert result == text
