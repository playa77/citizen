"""OCR quality assessment — deterministic quality gate before pipeline.

Checks extracted text for common OCR artifacts, garbage characters, and
structural issues. Produces a scored ``OcrQualityReport`` that the pipeline
uses to decide whether to proceed, warn, or reject.

Usage::

    from app.services.ocr_quality import assess_ocr_quality

    report = assess_ocr_quality(extracted_text)
    if report.score < 0.3:
        raise OcrQualityError(...)
"""

# Semantic Version: 0.1.0 | 2026-07-13

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Common German function words used for language detection
# ---------------------------------------------------------------------------

_GERMAN_FUNCTION_WORDS: frozenset[str] = frozenset(
    {
        "der",
        "die",
        "das",
        "den",
        "dem",
        "des",
        "ein",
        "eine",
        "einer",
        "eines",
        "einem",
        "einen",
        "und",
        "oder",
        "aber",
        "sondern",
        "doch",
        "ist",
        "sind",
        "war",
        "waren",
        "wird",
        "werden",
        "wurde",
        "würden",
        "hat",
        "haben",
        "hatte",
        "hatten",
        "nicht",
        "kein",
        "keine",
        "keinen",
        "keiner",
        "keines",
        "mit",
        "von",
        "auf",
        "für",
        "über",
        "unter",
        "nach",
        "vor",
        "bei",
        "aus",
        "an",
        "in",
        "zu",
        "um",
        "durch",
        "gegen",
        "ohne",
        "bis",
        "seit",
        "außer",
        "gemäß",
        "laut",
        "zur",
        "zum",
        "beim",
        "vom",
        "ins",
        "im",
        "am",
        "als",
        "wie",
        "so",
        "auch",
        "nur",
        "noch",
        "schon",
        "bereits",
        "immer",
        "nie",
        "niemals",
        "dann",
        "davor",
        "danach",
        "deshalb",
        "daher",
        "trotzdem",
        "dennoch",
        "allerdings",
        "jedoch",
        "zwar",
        "nämlich",
        "also",
        "folglich",
        "dieser",
        "diese",
        "dieses",
        "diesen",
        "diesem",
        "solche",
        "solcher",
        "solches",
        "jeder",
        "jede",
        "jedes",
        "jeden",
        "jedem",
        "wer",
        "was",
        "wem",
        "wen",
        "welche",
        "welcher",
        "welches",
        "sich",
        "ihm",
        "ihn",
        "ihr",
        "ihre",
        "ihres",
        "ihrer",
        "ihren",
        "sein",
        "seine",
        "seines",
        "seiner",
        "seinen",
        "seinem",
        "unser",
        "unsere",
        "unseres",
        "unserer",
        "unseren",
        "uns",
        "euch",
        "euer",
        "eure",
        "ihnen",
        "sie",
        "es",
        "man",
        "alle",
        "bzw",
        "zB",
        "ca",
        "ggf",
        "etc",
        "usw",
        "d.h",
    }
)

# ---------------------------------------------------------------------------
# Common OCR artifact patterns
# ---------------------------------------------------------------------------

# O instead of 0 in numeric contexts (e.g., "15.O3.2O25" → "15.03.2025")
_OCR_O_FOR_ZERO: re.Pattern[str] = re.compile(
    r"(?<=\d)[Oo](?=\d)|(?<=\d)[Oo](?=\D)|(?<=\D)[Oo](?=\d)"
)

# l (lowercase L) instead of 1 (e.g., "l5" → "15")
_OCR_L_FOR_ONE: re.Pattern[str] = re.compile(r"(?<=\d)l(?=\d)|(?<=\D)l(?=\d)")

# Garbled special chars in non-address contexts (e.g., @#$% in text body)
_OCR_GARBLED_CHARS: re.Pattern[str] = re.compile(r"[@#$%^&*=_+{}[\]|\\<>~`]")

# Hyphenation errors: split words across lines (e.g., "Beschei-\ndigung")
_OCR_HYPHEN_SPLIT: re.Pattern[str] = re.compile(r"[a-zäöüß]-\s*\n[a-zäöüß]")

# Long runs of non-word characters (garbled region)
_OCR_GARBLED_RUNS: re.Pattern[str] = re.compile(r"[^a-zäöüßA-ZÄÖÜ0-9\s.,;:!?\"'()\-/]")

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class OcrQualityReport:
    """OCR quality assessment result.

    Attributes
    ----------
    score :
        Overall quality score from 0.0 to 1.0 (higher = better).
    level :
        Categorical quality: ``"good"``, ``"acceptable"``, ``"poor"``,
        or ``"unusable"``.
    issues :
        Human-readable quality issues found during assessment.
    warnings :
        Warnings to show the user before proceeding.
    ocr_artifacts_detected :
        Whether common OCR artifacts (O→0, l→1, garbled chars) were found.
    readable_words_pct :
        Percentage of word-like tokens that look like real words (0.0-1.0).
    language_detected :
        ``"de"`` if German patterns detected, ``"unknown"`` otherwise.
    recommendations :
        Suggested actions for the user (e.g., re-scan, manual entry).
    """

    score: float = 0.0
    level: str = "unusable"
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    ocr_artifacts_detected: bool = False
    readable_words_pct: float = 0.0
    language_detected: str = "unknown"
    recommendations: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Internal scoring helpers
# ---------------------------------------------------------------------------


def _score_by_level(score: float) -> str:
    """Map a numeric score to a categorical quality level."""
    if score >= 0.8:
        return "good"
    if score >= 0.5:
        return "acceptable"
    if score >= 0.3:
        return "poor"
    return "unusable"


def _detect_german_language(text: str) -> tuple[str, float]:
    """Detect whether *text* appears to be German.

    Checks for:
    - German-specific characters (ä, ö, ü, ß)
    - Common German function words

    Returns
    -------
    tuple[str, float]
        ``("de"|"unknown", confidence)`` where confidence is 0.0-1.0.
    """
    lower = text.lower()
    total_chars = len(text.strip())
    if total_chars == 0:
        return "unknown", 0.0

    # Check for German-specific characters
    has_umlauts = bool(re.search(r"[äöüßÄÖÜ]", text))

    # Tokenise and check function-word ratio
    tokens = re.findall(r"[a-zäöüß]+", lower)
    if not tokens:
        return "unknown", 0.0

    fn_words = sum(1 for t in tokens if t in _GERMAN_FUNCTION_WORDS)
    fn_ratio = fn_words / len(tokens)

    if has_umlauts and fn_ratio >= 0.05:
        return "de", min(1.0, 0.5 + fn_ratio)
    if fn_ratio >= 0.15:
        return "de", fn_ratio
    if has_umlauts:
        return "de", 0.5
    return "unknown", fn_ratio


def _count_garbage_chars(text: str) -> tuple[int, float]:
    """Count characters outside printable ASCII + German umlauts + standard punctuation.

    Standard punctuation includes: ``.,;:!?\"'()-/``.

    Returns
    -------
    tuple[int, float]
        (count, ratio_of_garbage_to_total_non_whitespace).
    """
    non_ws = text.replace(" ", "").replace("\n", "").replace("\t", "")
    if len(non_ws) == 0:
        return 0, 0.0

    # Characters that are VALID (not garbage)
    valid_chars = set(
        "abcdefghijklmnopqrstuvwxyz"
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        "äöüßÄÖÜ"
        "0123456789"
        ".,;:!?\"'()-/ "
    )
    garbage = sum(1 for c in non_ws if c not in valid_chars and not c.isprintable())
    # Also count "garbled special chars" (non-standard punctuation, math symbols, etc.)
    garbled_specials = _OCR_GARBLED_CHARS.findall(non_ws)

    return garbage + len(garbled_specials), (garbage + len(garbled_specials)) / len(non_ws)


def _count_alphabetic_ratio(text: str) -> tuple[int, float]:
    """Ratio of alphabetic characters (a-z, äöüß, A-Z, ÄÖÜ) to total non-whitespace.

    Returns
    -------
    tuple[int, float]
        (alphabetic_count, ratio).
    """
    non_ws = text.replace(" ", "").replace("\n", "").replace("\t", "")
    if len(non_ws) == 0:
        return 0, 0.0

    alpha = sum(1 for c in non_ws if c.isalpha() or c in "äöüßÄÖÜ")
    return alpha, alpha / len(non_ws)


def _count_readable_words(text: str) -> tuple[float, list[str]]:
    """Estimate the fraction of tokens that look like real German words.

    A token is considered "word-like" if it is composed primarily of letters
    (a-z, äöüß).  Among those, a subset matches known German function words
    or common word patterns (longer than 2 chars with sufficient vowels).

    Returns
    -------
    tuple[float, list[str]]
        (readable_ratio, issues_found).
    """
    tokens = re.findall(r"[a-zäöüßA-ZÄÖÜ]{2,}", text)
    if not tokens:
        return 0.0, ["Keine erkennbaren Wort-Token gefunden"]

    lower_tokens = [t.lower() for t in tokens]

    # Count tokens that look like real words: known function words, or
    # tokens > 2 chars with at least one vowel
    vowel_pattern = re.compile(r"[aeiouäöü]")
    real_words = sum(
        1
        for t in lower_tokens
        if t in _GERMAN_FUNCTION_WORDS or (len(t) > 2 and vowel_pattern.search(t))
    )

    ratio = real_words / len(tokens)
    issues: list[str] = []
    if ratio < 0.3:
        issues.append(f"Nur {ratio:.0%} der Token sind erkennbare Wörter " f"(erwartet: >30 %).")
    elif ratio < 0.6:
        issues.append(
            f"Ca. {ratio:.0%} der Token sind erkennbare Wörter "
            f"(erwartet: >60 % für gute Qualität)."
        )

    return ratio, issues


def _detect_ocr_artifacts(text: str) -> tuple[bool, list[str]]:
    """Detect common OCR artifact patterns.

    Returns
    -------
    tuple[bool, list[str]]
        (any_found, descriptions).
    """
    issues: list[str] = []
    found = False

    o_matches = _OCR_O_FOR_ZERO.findall(text)
    if o_matches:
        found = True
        issues.append(
            f"OCR-Artefakt: 'O' statt '0' in {len(o_matches)} Stelle(n) "
            f"(z. B. '15.O3' → '15.03')."
        )

    l_matches = _OCR_L_FOR_ONE.findall(text)
    if l_matches:
        found = True
        issues.append(f"OCR-Artefakt: 'l' statt '1' in {len(l_matches)} Stelle(n).")

    garbled_matches = _OCR_GARBLED_CHARS.findall(text)
    if garbled_matches:
        found = True
        issues.append(
            f"Sonderzeichen-Artefakte gefunden "
            f"({len(garbled_matches)} Vorkommen von @ # $ % ^ & * o. Ä.)."
        )

    hyphen_matches = _OCR_HYPHEN_SPLIT.findall(text)
    if hyphen_matches:
        found = True
        issues.append(
            f"Zeilenweise Silbentrennung ({len(hyphen_matches)} Stelle(n)) "
            f"- ggf. getrennte Wörter wieder zusammenführen."
        )

    return found, issues


def _assess_text_structure(text: str) -> list[str]:
    """Check for structural issues: sentence breaks, paragraph breaks.

    Returns
    -------
    list[str]
        Human-readable warnings about structural problems.
    """
    issues: list[str] = []
    stripped = text.strip()
    if not stripped:
        return issues

    # Check for sentence-ending punctuation
    sentences = re.findall(r"[.!?]", stripped)
    if not sentences:
        issues.append(
            "Keine Satzzeichen (Punkt, Fragezeichen, Ausrufezeichen) gefunden. "
            "Text wirkt möglicherweise unstrukturiert."
        )
    else:
        # Check for suspiciously long stretches without sentence breaks
        parts = re.split(r"[.!?]", stripped)
        longest = max(len(p.strip()) for p in parts) if parts else 0
        if longest > 500:
            issues.append(
                f"Textabschnitt von {longest} Zeichen ohne Satzzeichen - "
                "moeglicherweise fehlen Trennungen."
            )

    # Check for paragraph breaks
    if "\n\n" not in stripped and len(stripped) > 200:
        issues.append(
            "Keine Absatzumbrüche (doppelte Zeilenumbrüche) gefunden. "
            "Bei mehrzeiligen Dokumenten sind Absätze zu erwarten."
        )

    return issues


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def assess_ocr_quality(text: str) -> OcrQualityReport:
    """Assess OCR quality of extracted text using deterministic heuristics.

    The assessment covers:

    - **Character-level**: ratio of valid characters vs. garbage
    - **Word-level**: fraction of tokens that look like real German words
    - **OCR artifacts**: O→0, l→1, garbled special chars, hyphenation errors
    - **Language detection**: heuristic check for German-specific patterns
      (umlauts, common function words)
    - **Text structure**: sentence breaks, paragraph breaks

    Scoring thresholds
    ------------------
    - ``>= 0.8`` -> ``"good"`` - pass through silently
    - ``0.5-0.8`` -> ``"acceptable"`` - warn user, proceed
    - ``0.3-0.5`` -> ``"poor"`` - strong warning, offer re-scan
    - ``< 0.3`` -> ``"unusable"`` - refuse to proceed

    Parameters
    ----------
    text :
        The extracted (and optionally normalized) UTF-8 text string.

    Returns
    -------
    OcrQualityReport
        A dataclass with score, level, issues, and recommendations.
    """
    logger.debug("Assessing OCR quality on %d chars of text", len(text))

    issues: list[str] = []
    warnings: list[str] = []
    recommendations: list[str] = []

    # Handle empty / whitespace-only text
    stripped = text.strip()
    if not stripped:
        logger.info("OCR quality: empty text → unusable (score=0.0)")
        return OcrQualityReport(
            score=0.0,
            level="unusable",
            issues=["Der extrahierte Text ist leer."],
            warnings=[],
            ocr_artifacts_detected=False,
            readable_words_pct=0.0,
            language_detected="unknown",
            recommendations=[
                "Bitte laden Sie das Dokument erneut hoch.",
                "Stellen Sie sicher, dass das Dokument lesbaren Text enthält.",
                "Alternativ können Sie den Text manuell eingeben.",
            ],
        )

    # ── 1. Language detection ──────────────────────────────────────────
    lang, lang_conf = _detect_german_language(stripped)
    logger.debug("Language detection: %s (confidence=%.2f)", lang, lang_conf)

    if lang == "unknown" and lang_conf < 0.1:
        warnings.append(
            "Die Texterkennung konnte keine deutsche Sprache sicher erkennen. "
            "Die Analysequalität kann eingeschränkt sein."
        )

    # ── 2. Garbage character ratio ────────────────────────────────────
    garbage_count, garbage_ratio = _count_garbage_chars(stripped)
    logger.debug("Garbage chars: %d / ratio=%.4f", garbage_count, garbage_ratio)

    if garbage_ratio > 0.05:
        issues.append(
            f"{garbage_count} ungültige Zeichen gefunden "
            f"({garbage_ratio:.1%} des Textes) - moeglicherweise "
            "falsch erkannter Scan."
        )

    # ── 3. Alphabetic ratio ──────────────────────────────────────────
    alpha_count, alpha_ratio = _count_alphabetic_ratio(stripped)
    non_ws_len = len(stripped.replace(" ", "").replace("\n", "").replace("\t", ""))
    logger.debug(
        "Alphabetic ratio: %.2f (%d/%d non-ws chars)",
        alpha_ratio,
        alpha_count,
        non_ws_len,
    )

    if alpha_ratio < 0.5:
        issues.append(
            f"Weniger als 50 % Buchstaben im Text ({alpha_ratio:.0%}). "
            "Hoher Anteil an Ziffern oder Sonderzeichen - ggf. Scan-Artefakte."
        )
    elif alpha_ratio < 0.8:
        warnings.append(
            f"Nur {alpha_ratio:.0%} Buchstabenanteil im Text "
            "(erwartet: >80 % für sauberen Text)."
        )

    # ── 4. Readable words ratio ──────────────────────────────────────
    readable_ratio, word_issues = _count_readable_words(stripped)
    logger.debug("Readable words ratio: %.2f", readable_ratio)
    issues.extend(word_issues)

    # ── 5. OCR artifacts ─────────────────────────────────────────────
    artifacts_found, artifact_issues = _detect_ocr_artifacts(stripped)
    if artifact_issues:
        logger.debug("OCR artifacts detected: %d types", len(artifact_issues))
    issues.extend(artifact_issues)

    # ── 6. Text structure ────────────────────────────────────────────
    structural_issues = _assess_text_structure(stripped)
    issues.extend(structural_issues)

    # ── 7. Compute overall score ─────────────────────────────────────
    # Score components and weights (per WP-42 spec):
    #   - character_ratio   (30 %) — fraction of chars that are valid letters
    #   - readable_words    (30 %) — tokens that look like real words
    #   - german_word_match (25 %) — known German function words matched
    #   - structure_score   (15 %) — sentence breaks & structure
    #
    # Each sub-score is 0.0-1.0. The artifact penalty is folded into the
    # character and structure components (artifacts degrade both).

    sub_alpha = min(1.0, alpha_ratio / 0.8)
    sub_readable = readable_ratio

    # German word match ratio: fraction of tokens matching known function words
    tokens = re.findall(r"[a-zäöüß]+", text.lower())
    if tokens:
        fn_match_ratio = sum(1 for t in tokens if t in _GERMAN_FUNCTION_WORDS) / len(tokens)
    else:
        fn_match_ratio = 0.0
    sub_german = min(1.0, fn_match_ratio / 0.25)  # 25 % function words → 1.0

    # Structure score: presence of sentence punctuation
    has_sentence_breaks = bool(re.search(r"[.!?]", text))
    sub_structure = 1.0 if has_sentence_breaks else 0.3

    # Garbage penalty: applied as a multiplier on character score
    garbage_mult = max(0.0, 1.0 - garbage_ratio * 8)  # 12.5 % garbage → 0

    # Artifact penalty: reduces structure and readability
    artifact_mult = 0.6 if artifacts_found else 1.0

    score = (
        0.30 * sub_alpha * garbage_mult
        + 0.30 * sub_readable
        + 0.25 * sub_german
        + 0.15 * sub_structure * artifact_mult
    )
    score = max(0.0, min(1.0, score))

    level = _score_by_level(score)

    # ── 8. Build recommendations ─────────────────────────────────────
    if level == "unusable":
        recommendations.extend(
            [
                "Bitte laden Sie das Dokument erneut hoch (300 dpi, hoher Kontrast).",
                "Stellen Sie sicher, dass das Dokument flach und ohne Schatten gescannt wurde.",
                "Alternativ können Sie den Text manuell eingeben.",
            ]
        )
    elif level == "poor":
        recommendations.extend(
            [
                "Besser: Dokument neu scannen (300 dpi, Schwarz/Weiß, hoher Kontrast).",
                "Sie können den extrahierten Text manuell korrigieren.",
            ]
        )
    elif level == "acceptable":
        recommendations.append(
            "Der Text ist nutzbar, aber eine manuelle Überprüfung wird empfohlen."
        )
    elif level == "good" and issues:
        recommendations.append(
            "Kleinere Auffälligkeiten wurden korrigiert. Die Analyse kann fortgesetzt werden."
        )

    # ── 9. Build warnings ────────────────────────────────────────────
    if level == "poor":
        warnings.append(
            "Die OCR-Qualität ist gering. Ergebnisse können ungenau sein. "
            "Besser: Dokument neu scannen oder Text manuell eingeben."
        )
    elif level == "acceptable":
        warnings.append(
            "Die OCR-Qualität ist ausreichend. Bitte überprüfen Sie "
            "den extrahierten Text auf offensichtliche Fehler."
        )

    report = OcrQualityReport(
        score=round(score, 4),
        level=level,
        issues=issues,
        warnings=warnings,
        ocr_artifacts_detected=artifacts_found,
        readable_words_pct=round(readable_ratio, 4),
        language_detected=lang,
        recommendations=recommendations,
    )

    logger.info(
        "OCR quality assessment: score=%.4f level=%s artifacts=%s " "lang=%s issues=%d",
        report.score,
        report.level,
        report.ocr_artifacts_detected,
        report.language_detected,
        len(report.issues),
    )

    return report
