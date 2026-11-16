# Version: 1.1.0 | 2026-11-16 — prompt set 3.0.0 measurement fix (F-19, CR-13):
# norm regex accepts spelled-out Satz and §§ lists and no longer swallows
# trailing prose; hierarchy norms are normalised to the same key.
# 1.0.0 | 2026-07-12
"""Deterministic extraction functions for pipeline output analysis.

All functions are pure — no LLM calls, no side effects, no DB access.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from eval.pipeline_adapter import PipelineOutput

# ---------------------------------------------------------------------------
# Norm reference regex
# ---------------------------------------------------------------------------

# Match patterns like:
#   § 11b Abs. 3 S. 2 Nr. 1-3 SGB II
#   § 31 Abs. 1 Satz 2 SGB II          (Satz spelled out, 1.1.0)
#   § 32 SGB II n.F.
#   § 12 Abs. 4 SGB II a.F. (bis 30.06.2026)
#   § 41a Abs. 1, 3, 6 SGB II
#   §§ 45/48/50 SGB X, §§ 45, 48 SGB X, §§ 45 und 48 SGB X
#   § 40 Abs. 2 Nr. 3 SGB II i.V.m. § 330 Abs. 3 SGB III
#
# Strategy (1.1.0): "§" + paragraph number(s) + optional subsection
# qualifiers + a statute abbreviation. The statute is ONE token with at least
# two capital letters (SGB, BGB, ErbStG, BewG, HöfeO, SGG ...) plus an
# optional roman book number (SGB II, SGB XII). Matching stops there, so
# trailing prose ("… SGB II zu übernehmen") is no longer swallowed into the
# norm (F-19). n.F./a.F. and parentheticals are consumed separately.
_PARA = r"\d+[a-z]?"
_SUB_NUM = r"\d+[a-z]?(?:\s*(?:[-/,]|und|bis)\s*\d+[a-z]?)*"
_SINGLE_NORM_RE = re.compile(
    r"§{1,2}\s*"  # § or §§
    rf"(?P<para>{_PARA}(?:\s*(?:/|,|und)\s*{_PARA})*)"  # paragraph number(s)
    r"(?:\s+(?:"
    rf"Abs\.\s*{_SUB_NUM}"  # Absatz
    rf"|S\.\s*{_SUB_NUM}"  # Satz (abbreviated)
    rf"|Satz\s*{_SUB_NUM}"  # Satz (spelled out)
    rf"|Hs\.\s*{_SUB_NUM}"  # Halbsatz
    r"|Nr\.\s*[A-Za-z0-9]+(?:\s*[-/,]\s*[A-Za-z0-9]+)*"  # Nummer
    r"|(?:Buchst\.|lit\.)\s*[a-z]+"  # Buchstabe
    r"))*"
    r"\s+"  # mandatory space before statute
    r"(?P<statute>"
    r"[A-ZÄÖÜ][A-Za-zÄÖÜäöüß]*"  # statute abbreviation (checked: >= 2 capitals)
    r"(?:\s+(?:XIV|XIII|XII|XI|IX|X|VIII|VII|VI|V|IV|III|II|I)(?![A-Za-z]))?"  # book
    r")"
    r"(?:\s+(?:n\.F\.|a\.F\.))?"  # optional n.F./a.F.
    r"(?:\s*\([^)]*\))?"
)


def _is_statute_token(statute: str) -> bool:
    """A statute abbreviation has at least two capital letters (SGB, BewG)."""
    first = statute.split()[0]
    return sum(1 for ch in first if ch.isupper()) >= 2


# Case-law citations: "BSG, Urt. v. 19.02.2009 - B 4 AS 30/08 R"
_CASE_LAW_RE = re.compile(
    r"[A-Za-zÄÖÜäöü]+,\s*"
    r"(?:Urt|Beschl|Hinweisbeschl|Gerichtsbescheid)\.\s*v\.\s*"
    r"\d{2}\.\d{2}\.\d{4}\s*-\s*"
    r"[A-Za-z0-9\s/]+"
)


# ---------------------------------------------------------------------------
# Public extraction functions
# ---------------------------------------------------------------------------


def extract_norm_references(text: str) -> set[str]:
    """Parse statute references from *text* using regex.

    Handles common German statute citation patterns:

    - ``§ 11b Abs. 3 S. 2 Nr. 1-3 SGB II``
    - ``§ 11b Abs. 2 S. 1 SGB II``
    - ``§ 32 SGB II n.F.``
    - ``§ 12 Abs. 4 SGB II a.F. (bis 30.06.2026)``
    - ``§§ 45/48/50 SGB X``
    - ``§ 31a Abs. 1 S. 2 SGB II n.F.``

    Also detects case-law citations like
    ``BSG, Urt. v. 19.02.2009 - B 4 AS 30/08 R`` — these are returned as-is
    (they won't match the statute pattern).

    Each statute reference is normalised: ``n.F.`` and ``a.F.`` flags and
    parenthetical date ranges are stripped. Multiple paragraphs in a
    ``§§ 45/48/50``-style reference are exploded into individual norms.

    Returns
    -------
    set[str]
        Normalised, deduplicated norm strings.
    """
    found: set[str] = set()

    # --- Match case-law citations directly ---
    for match in _CASE_LAW_RE.finditer(text):
        found.add(match.group(0).strip())

    # --- Match statute references ---
    for match in _SINGLE_NORM_RE.finditer(text):
        raw_paras = match.group("para").strip()  # e.g. "11b" or "45/48/50"
        statute = " ".join(match.group("statute").split())  # e.g. "SGB II"
        if not _is_statute_token(statute):
            continue  # "§ 22 Kosten …" — prose, not a statute

        # Explode multiple paragraphs (e.g. "45/48/50", "45, 48", "45 und 48")
        for para in re.split(r"\s*(?:/|,|und)\s*", raw_paras):
            if para:
                found.add(f"§ {para} {statute}")

    return found


def extract_citations_from_pipeline(output: PipelineOutput) -> set[str]:
    """Extract all norm references from pipeline output.

    Three sources are searched:

    1. **Claim evidence hierarchies** — hierarchy paths like
       ``"SGB II > § 11b > Abs. 3"`` are converted to
       ``"§ 11b Abs. 3 SGB II"``.
    2. **Final output sections** — all text values in ``output.final_output``
       are joined and parsed for §-references.
    3. **Calculation result** — all string values in
       ``output.calculation_result`` are recursively searched.

    Returns
    -------
    set[str]
        Union of all normalised norm strings found across all sources.
    """
    result: set[str] = set()

    # Source 1: claim evidence hierarchies
    for claim in output.claims:
        hierarchy = claim.get("evidence_hierarchy", "")
        if hierarchy:
            normalised = _hierarchy_to_norm(hierarchy)
            if normalised:
                # Same key as text citations ("§ 31 SGB II"), 1.1.0.
                result.update(extract_norm_references(normalised) or {normalised})

    # Source 2: final output sections
    all_section_text = " ".join(
        v for v in output.final_output.values() if isinstance(v, str) and v.strip()
    )
    if all_section_text:
        result.update(extract_norm_references(all_section_text))

    # Source 3: calculation result (recursive string search)
    calc_texts = _collect_strings(output.calculation_result)
    combined_calc_text = " ".join(calc_texts)
    if combined_calc_text:
        result.update(extract_norm_references(combined_calc_text))

    return result


def extract_assessment_from_pipeline(output: PipelineOutput) -> str | None:
    """Extract overall assessment from pipeline output via keyword matching.

    The ``ergebnis`` section of ``output.final_output`` is searched for
    known assessment keywords. Longer/more-specific patterns are checked
    first to avoid false positives (e.g. ``teilweise_rechtswidrig`` before
    ``rechtswidrig``).

    Returns
    -------
    str | None
        One of ``teilweise_rechtswidrig``, ``ueberwiegend_rechtmaessig``,
        ``rechtswidrig``, ``kein_verwaltungsakt``, or ``None`` if no match.
    """
    ASSESSMENT_KEYWORDS: list[tuple[str, list[str]]] = [
        (
            "teilweise_rechtswidrig",
            [
                "teilweise rechtswidrig",
                "teils rechtswidrig",
                "teilweise rechtsfehlerhaft",
            ],
        ),
        (
            "ueberwiegend_rechtmaessig",
            [
                "überwiegend rechtmäßig",
                "im wesentlichen korrekt",
                "weist jedoch keine durchgreifenden fehler",
            ],
        ),
        (
            "rechtswidrig",
            [
                "rechtswidrig",
                "nicht rechtmäßig",
                "unzulässig",
            ],
        ),
        (
            "kein_verwaltungsakt",
            [
                "kein verwaltungsakt",
                "nicht verwaltungsakt",
                "kein va",
            ],
        ),
    ]

    text = output.final_output.get("ergebnis", "")
    if not text:
        return None

    text_lower = text.lower()

    for assessment, keywords in ASSESSMENT_KEYWORDS:
        for kw in keywords:
            if kw in text_lower:
                return assessment

    return None


def extract_calculation_values(output: PipelineOutput) -> dict[str, float]:
    """Map pipeline calculation labels to goldset ``expected_korrekt`` keys.

    Each entry in ``output.calculation_result.get("calculations_found", [])``
    is matched via ``LABEL_TO_GOLDSET``. The ``computed_values.deterministic_result``
    is extracted and cast to ``float``.

    Returns
    -------
    dict[str, float]
        Goldset-key → float-value mapping. Only entries whose label is in
        ``LABEL_TO_GOLDSET`` and whose result is numeric are included.
    """
    LABEL_TO_GOLDSET: dict[str, str] = {
        "Erwerbstätigenfreibetrag": "freibetrag_gesamt",
        "Einkommensanrechnung (Brutto - Freibetrag)": "anzurechnendes_einkommen",
        "Auszahlungsbetrag (Gesamt)": "anspruch_monatlich",
        "Regelbedarf": "regelbedarf",
        "Kosten der Unterkunft und Heizung": "kdu_gesamt",
        "Gesamtbedarf": "gesamtbedarf",
        "Brutto-Erwerbseinkommen": "erwerbseinkommen_brutto",
        "Netto-Erwerbseinkommen": "erwerbseinkommen_netto",
        "Grundabsetzungsbetrag (§ 11b Abs. 2)": "grundabsetzung",
        "Freibetrag 20% (100-520 EUR)": "fb_20_prozent_band",
        "Freibetrag 30% (520-1000 EUR)": "fb_30_prozent_band",
        "Freibetrag 10% (1000-1200 EUR)": "fb_10_prozent_band",
        "Anzurechnendes Einkommen": "anzurechnendes_einkommen",
        # Reconciliation labels (WP-23)
        "Anrechenbares Einkommen": "anzurechnendes_einkommen",
        "Anspruch (Leistung)": "anspruch_monatlich",
    }

    result: dict[str, float] = {}
    calculations = output.calculation_result.get("calculations_found", [])
    if not isinstance(calculations, list):
        return result

    for entry in calculations:
        if not isinstance(entry, dict):
            continue
        label = entry.get("label", "")
        goldset_key = LABEL_TO_GOLDSET.get(label)
        if goldset_key is None:
            continue
        computed = entry.get("computed_values", {})
        if not isinstance(computed, dict):
            continue
        val = computed.get("deterministic_result")
        if val is not None:
            try:
                result[goldset_key] = float(val)
            except (TypeError, ValueError):
                continue

    return result


def extract_issues_from_pipeline(output: PipelineOutput) -> list[set[str]]:
    """Extract §-references from each pipeline issue.

    For each issue string in ``output.issues``, all norm references are
    extracted using :func:`extract_norm_references`. One set per issue is
    returned. Even if a set is empty (no § found), it is included — it
    represents an issue that could not be mapped to a specific statute.

    Returns
    -------
    list[set[str]]
        One set of norm strings per pipeline issue.
    """
    return [extract_norm_references(issue) for issue in output.issues]


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _hierarchy_to_norm(hierarchy: str) -> str | None:
    """Convert a pipeline evidence hierarchy path to a norm string.

    Example: ``"SGB II > § 11b > Abs. 3"`` → ``"§ 11b Abs. 3 SGB II"``
    """
    parts = [p.strip() for p in hierarchy.split(">")]
    if len(parts) < 2:
        return None

    # parts[0] is the statute name (e.g. "SGB II")
    # parts[1] is the paragraph (e.g. "§ 11b")
    # parts[2:] are subsections (e.g. "Abs. 3", "S. 2")
    statute = parts[0]
    paragraph = parts[1]
    subsections = " ".join(parts[2:]) if len(parts) > 2 else ""

    if subsections:
        return f"{paragraph} {subsections} {statute}"
    return f"{paragraph} {statute}"


def _collect_strings(obj: Any) -> list[str]:
    """Recursively collect all string values from a nested dict/list structure."""
    strings: list[str] = []

    if isinstance(obj, str):
        strings.append(obj)
    elif isinstance(obj, dict):
        for val in obj.values():
            strings.extend(_collect_strings(val))
    elif isinstance(obj, list):
        for item in obj:
            strings.extend(_collect_strings(item))

    return strings
