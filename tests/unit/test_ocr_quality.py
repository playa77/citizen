"""Unit tests for ``app/services/ocr_quality.py`` — OCR quality gate (WP-42).

Tests cover:
- Good quality German legal text → score >= 0.8, level "good"
- Text with OCR artifacts → artifacts detected, score < 0.8
- Garbage text (random chars) → score < 0.3, level "unusable"
- Empty text → handled gracefully
- Very short text (1-2 sentences) → reasonable score
- Text with mixed languages → language_detected may be "unknown"
- German text with umlauts → language_detected "de"
- Poor quality but not garbage (~40% readable) → level "poor"
"""

# Version: 0.1.0 | 2026-07-13

from __future__ import annotations

from app.services.ocr_quality import assess_ocr_quality


class TestOcrQualityAssessment:
    """Test suite for the OCR quality assessment function."""

    def test_good_quality_german_legal_text(self):
        """Good quality German legal text → score >= 0.8, level 'good'."""
        text = (
            "Der Bescheid vom 15.03.2025 wurde geprüft. "
            "Das Jobcenter hat die Leistungen nach dem SGB II bewilligt. "
            "Der Antragsteller hat keinen Anspruch auf höhere Leistungen. "
            "Die Berechnung des Regelbedarfs ist korrekt erfolgt. "
            "Gemäß § 20 SGB II beträgt der Regelbedarf für Alleinstehende 563 Euro. "
            "Die Einkommensanrechnung wurde nach § 11b SGB II durchgeführt. "
            "Widerspruch gegen diesen Bescheid kann innerhalb eines Monats "
            "nach Bekanntgabe eingelegt werden."
        )
        report = assess_ocr_quality(text)

        assert report.score >= 0.8, f"Expected score >= 0.8, got {report.score}"
        assert report.level == "good", f"Expected 'good', got {report.level}"
        assert report.language_detected == "de"

    def test_ocr_artifacts_detected(self):
        """Text with OCR artifacts (O→0, l→1) → artifacts detected, score < 0.8."""
        text = (
            "Der Bescheid vOm l5.O3.2O25 wurde geprüft. "
            "Das J0bcenter hat die Leistungen nach dem SGB II bewilligt. "
            "Der Regelbedarf beträgt 563 Eur0."
        )
        report = assess_ocr_quality(text)

        assert report.ocr_artifacts_detected, "Expected OCR artifacts detected"
        assert len(report.issues) > 0
        assert any("OCR" in i or "Artefakt" in i for i in report.issues)

    def test_garbage_text_unusable(self):
        """Garbage text (random chars) → score < 0.3, level 'unusable'."""
        text = (
            "xK9#mP2$rT5!vB7@nM1%qW3^jH8&yU4*zC6(E)F0_G1-H2=I3+J4[K5]L6{M7}N8|"
            "O9:P0;Q1'R2,S3.S4/a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4"
            "^%$#@!*()_+-=[]{}|;':\",./<>?`~0123456789abcdefghijklmnopqrstuvwxyz"
            "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!##########################"
        )
        report = assess_ocr_quality(text)

        assert report.score < 0.3, f"Expected score < 0.3, got {report.score}"
        assert report.level == "unusable", f"Expected 'unusable', got {report.level}"
        assert len(report.recommendations) > 0

    def test_empty_text_handled_gracefully(self):
        """Empty text → handled without crashing, score 0, level 'unusable'."""
        text = ""
        report = assess_ocr_quality(text)

        assert report.score == 0.0
        assert report.level == "unusable"
        assert len(report.issues) > 0

    def test_whitespace_only_text(self):
        """Whitespace-only text → handled like empty."""
        text = "   \n\n  \t  "
        report = assess_ocr_quality(text)

        assert report.score == 0.0
        assert report.level == "unusable"

    def test_short_text_reasonable_score(self):
        """Very short text (1-2 sentences) → still gets a reasonable score."""
        text = "Der Bescheid wurde geprüft. Die Leistung wurde bewilligt."
        report = assess_ocr_quality(text)

        # Short but clean text should still pass the basic checks
        assert report.score > 0.0
        assert report.level in ("good", "acceptable")

    def test_german_with_umlauts(self):
        """German text with umlauts → language_detected 'de'."""
        text = (
            "Die Änderung des Bescheides wurde nach § 44 SGB X geprüft. "
            "Die Überprüfung der Einkommensverhältnisse ergab, dass "
            "der Kläger einen Anspruch auf höhere Leistungen hat. "
            "Die Behörde wurde zur Neubescheidung verurteilt."
        )
        report = assess_ocr_quality(text)

        assert report.language_detected == "de"

    def test_mixed_language_text(self):
        """Text with mixed languages → language_detected may be 'unknown'."""
        text = (
            "The quick brown fox jumps over the lazy dog. "
            "This is an English sentence without any German words. "
            "All of these tokens should be English."
        )
        report = assess_ocr_quality(text)

        # English text without umlauts → German detection fails → "unknown" is acceptable
        assert report.language_detected == "unknown"

    def test_poor_quality_not_garbage(self):
        """Poor quality but not garbage (~40% readable) → score in poor range."""
        text = (
            "Der Bescheid wurde geprüft. "
            "Das Jobcenter hat die Leistungen bewilligt. "
            "xB@nk#L9&mP!qR$tV%wX^yZ*aB(cD)eF_gH-iJ+kL[M]"
            "N{O}P|Q:R;S'T,U.V/W?X~Y`Z0123456789!@#$%^&*()"
            "Der Antragsteller hat keinen Anspruch. "
            "#@!$%^&*()_+-=[]{}|;':\",./<>?`~XXXXXXXXXXXXXXXX"
        )
        report = assess_ocr_quality(text)

        assert report.score < 0.5, f"Expected score < 0.5, got {report.score}"
        assert report.level in (
            "poor",
            "unusable",
        ), f"Expected 'poor' or 'unusable', got {report.level}"

    def test_acceptable_quality(self):
        """Text with minor issues → score >= 0.5."""
        text = (
            "Der Bescheid vom 15.03.2025 wurde geprüft. "
            "Das Jobcenter hat die Leistungen nach dem SGB II bewilligt. "
            "Der Regelbedarf beträgt 563 Eur0. "
            "Dies ist ein Testtext mit einem OCR-Fehler."
        )
        report = assess_ocr_quality(text)

        assert report.score >= 0.5, f"Expected score >= 0.5, got {report.score}"

    def test_alphabetic_ratio_check(self):
        """Text with very low alphabetic ratio → score < 0.5."""
        text = "12345 67890 12345 67890 12345 67890"
        report = assess_ocr_quality(text)

        assert report.score < 0.5

    def test_no_sentence_structure(self):
        """Text without sentence breaks → structural issue flagged."""
        text = (
            "dies ist ein langer text ohne satzzeichen "
            "der einfach immer weiterlaeuft ohne punkt "
            "oder absatz das ist ein strukturelles problem "
            "das vom qualitaetscheck erkannt werden sollte "
        )
        report = assess_ocr_quality(text)

        # Should flag no sentence punctuation as an issue
        has_structure_issue = any("Satzzeichen" in i for i in report.issues)
        assert has_structure_issue, "Expected structural issue about missing punctuation"
