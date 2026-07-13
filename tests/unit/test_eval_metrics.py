"""Unit tests for eval metrics, including WP-12 quote verification rate and WP-32 PII metrics."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from eval.metrics import (
    compute_leakage_rate,
    compute_over_redaction_count,
    compute_pii_precision,
    compute_pii_recall,
    compute_quote_verification_rate,
    compute_reinjection_integrity,
)
from eval.goldset_loader import PiiAnnotation, PiiSpan


# ===========================================================================
# Quote verification rate (WP-12) — existing tests
# ===========================================================================


class TestComputeQuoteVerificationRate:
    """``compute_quote_verification_rate`` behavior."""

    def test_all_exakt(self) -> None:
        claims = [
            {"verification_status": "exakt"},
            {"verification_status": "exakt"},
            {"verification_status": "exakt"},
        ]
        assert compute_quote_verification_rate(claims) == 1.0

    def test_all_normalisiert(self) -> None:
        claims = [
            {"verification_status": "normalisiert"},
            {"verification_status": "normalisiert"},
        ]
        assert compute_quote_verification_rate(claims) == 1.0

    def test_mixed_verified(self) -> None:
        claims = [
            {"verification_status": "exakt"},
            {"verification_status": "normalisiert"},
            {"verification_status": "unverifiziert"},
            {"verification_status": "unverifiziert"},
        ]
        # 2 verified out of 4
        assert compute_quote_verification_rate(claims) == 0.5

    def test_all_unverifiziert(self) -> None:
        claims = [
            {"verification_status": "unverifiziert"},
            {"verification_status": "unverifiziert"},
        ]
        assert compute_quote_verification_rate(claims) == 0.0

    def test_empty_list(self) -> None:
        assert compute_quote_verification_rate([]) == 0.0

    def test_single_exakt(self) -> None:
        claims = [{"verification_status": "exakt"}]
        assert compute_quote_verification_rate(claims) == 1.0

    def test_single_unverifiziert(self) -> None:
        claims = [{"verification_status": "unverifiziert"}]
        assert compute_quote_verification_rate(claims) == 0.0

    def test_unknown_status_ignored(self) -> None:
        """A dict without verification_status or with an unknown value."""
        claims = [
            {"verification_status": "exakt"},
            {"verification_status": "unbekannt"},
            {},
        ]
        # Only 1 verified out of 3
        assert compute_quote_verification_rate(claims) == pytest.approx(1.0 / 3.0)


# ===========================================================================
# PII metrics (WP-32)
# ===========================================================================


class TestComputeLeakageRate:
    """``compute_leakage_rate`` — hard CI gate."""

    def test_clean_no_leakage(self) -> None:
        pseudo = "Sehr geehrte/r [[PERSON_1]], Ihr [[ID_1]] wurde bewilligt."
        mapping = {"value_to_placeholder": {"Max Mustermann": "[[PERSON_1]]", "BG-12345": "[[ID_1]]"}}
        assert compute_leakage_rate(pseudo, mapping) == 0.0

    def test_leak_detected(self) -> None:
        pseudo = "Sehr geehrter Max Mustermann, Ihr Bescheid wurde bewilligt."
        mapping = {"value_to_placeholder": {"Max Mustermann": "[[PERSON_1]]"}}
        assert compute_leakage_rate(pseudo, mapping) == 1.0

    def test_casefolded_leak_detected(self) -> None:
        pseudo = "Sehr geehrter MAX MUSTERMANN, Ihr Bescheid wurde bewilligt."
        mapping = {"value_to_placeholder": {"Max Mustermann": "[[PERSON_1]]"}}
        assert compute_leakage_rate(pseudo, mapping) == 1.0

    def test_empty_mapping(self) -> None:
        pseudo = "Some text with no PII."
        mapping = {"value_to_placeholder": {}}
        assert compute_leakage_rate(pseudo, mapping) == 0.0

    def test_placeholder_in_mapping_skipped(self) -> None:
        """Placeholder-formatted strings in the mapping are skipped."""
        pseudo = "Some [[PERSON_1]] text."
        mapping = {"value_to_placeholder": {"[[PERSON_1]]": "original"}}
        assert compute_leakage_rate(pseudo, mapping) == 0.0


class TestComputePiiRecall:
    """``compute_pii_recall`` — fraction of spans pseudonymized."""

    def test_all_recalled(self) -> None:
        text = "Hallo Herr Mustermann, Ihre BG-Nummer ist BG-12345."
        annotations = [
            PiiAnnotation(
                type="person",
                canonical="Mustermann",
                spans=[PiiSpan(start=10, end=20, text="Mustermann")],
            ),
        ]
        # After pseudonymization, "Mustermann" should be replaced
        from app.services.pseudonymization import pseudonymize
        pseudo, mapping = pseudonymize(text)
        recall = compute_pii_recall(text, annotations, mapping)
        assert recall == 1.0

    def test_none_recalled_empty_annotations(self) -> None:
        text = "Just some text."
        recall = compute_pii_recall(text, [], {"placeholder_to_value": {}})
        assert recall == 1.0


class TestComputePiiPrecision:
    """``compute_pii_precision`` — fraction of redactions that are correct."""

    def test_perfect_precision(self) -> None:
        text = "Hallo Herr Mustermann!"
        annotations = [
            PiiAnnotation(
                type="person",
                canonical="Mustermann",
                spans=[PiiSpan(start=10, end=20, text="Mustermann")],
            ),
        ]
        from app.services.pseudonymization import pseudonymize
        pseudo, mapping = pseudonymize(text)
        prec = compute_pii_precision(text, annotations, mapping)
        assert prec == 1.0

    def test_no_annotations_no_pseudonymization(self) -> None:
        text = "Just some harmless text."
        prec = compute_pii_precision(text, [], {"placeholder_to_value": {}})
        assert prec == 1.0


class TestComputeOverRedactionCount:
    """``compute_over_redaction_count`` — GS-012 negative controls."""

    def test_none_over_redacted(self) -> None:
        original = "Bescheid vom 03.05.2024. Regelbedarf 563,00 EUR."
        pseudo = "Bescheid vom 03.05.2024. Regelbedarf 563,00 EUR."
        controls = ["03.05.2024", "563,00 EUR"]
        assert compute_over_redaction_count(pseudo, original, controls) == 0

    def test_some_over_redacted(self) -> None:
        original = "Bescheid vom 03.05.2024. Geburtsdatum 03.05.1980."
        pseudo = "Bescheid vom [[GEBURTSDATUM_1]]. Geburtsdatum [[GEBURTSDATUM_1]]."
        controls = ["03.05.2024"]  # This was incorrectly redacted
        assert compute_over_redaction_count(pseudo, original, controls) == 1

    def test_empty_controls(self) -> None:
        assert compute_over_redaction_count("any", "any", []) == 0

    def test_control_not_in_original(self) -> None:
        """Skip controls that don't exist in the original."""
        assert compute_over_redaction_count("pseudo", "original", ["nonexistent"]) == 0


class TestComputeReinjectionIntegrity:
    """``compute_reinjection_integrity`` — roundtrip fidelity."""

    def test_perfect_roundtrip(self) -> None:
        original = "Sehr geehrter Herr Mustermann, Ihr Bescheid vom 03.05.2024."
        pseudo = "Sehr geehrter Herr [[PERSON_1]], Ihr Bescheid vom 03.05.2024."
        depseudo = "Sehr geehrter Herr Mustermann, Ihr Bescheid vom 03.05.2024."
        assert compute_reinjection_integrity(original, pseudo, depseudo) == 1.0

    def test_whitespace_differences(self) -> None:
        """Whitespace differences are tolerated."""
        original = "Sehr geehrter Herr  Mustermann,  Ihr Bescheid."
        pseudo = "Sehr geehrter Herr [[PERSON_1]], Ihr Bescheid."
        depseudo = "Sehr geehrter Herr Mustermann, Ihr Bescheid."
        result = compute_reinjection_integrity(original, pseudo, depseudo)
        assert result == pytest.approx(1.0, abs=0.1)  # Near perfect

    def test_partial_mismatch(self) -> None:
        original = "Hallo Welt"
        depseudo = "Hallo Welt und mehr"
        result = compute_reinjection_integrity(original, "", depseudo)
        assert result < 1.0

    def test_empty_original(self) -> None:
        assert compute_reinjection_integrity("", "", "") == 1.0
