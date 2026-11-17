# Version: 1.2.0 | 2026-11-17 — assessment scorer fix (D-069, docs/quality-plan.md
# Q1): reads the "Vorläufige Einordnung:" verdict sentence first; free-text
# fallback ignores negated mentions and picks the earliest match; drops the
# "unzulässig" keyword; adds the labels rechtmaessig / einordnung_offen.
# Assessment scores are not comparable with reports scored by 1.1.0.
# 1.1.0 | 2026-11-16 — prompt set 3.0.0 measurement fix (F-19, CR-13):
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


# --- Overall assessment (1.2.0) --------------------------------------------
#
# The P-04/P-08 prompt (prompt set 3.0.0+) makes ``ergebnis`` open with
# exactly one sentence "Vorläufige Einordnung: <Begriff>." whose term comes
# from the module's closed ``result_categories`` vocabulary plus the core's
# "Einordnung offen". That sentence is the verdict; it is read first.
# Free-text keyword search is only the fallback for outputs that lack it
# (legacy prompt sets, malformed answers).
#
# 1.0.0/1.1.0 defects fixed here (docs/quality-plan.md, D-069):
# - no negation handling: "nicht rechtswidrig" scored ``rechtswidrig``;
# - label precedence over the whole text: any "rechtswidrig" in the
#   reasoning beat a "kein Verwaltungsakt" verdict;
# - "unzulässig" mapped to ``rechtswidrig`` although it describes an
#   inadmissible remedy (e.g. a Widerspruch against a non-VA), not an
#   unlawful notice;
# - "keinen Verwaltungsakt" (accusative) was not recognised;
# - a plain "rechtmäßig" verdict and "Einordnung offen" fell through to
#   ``None`` and were indistinguishable from an extraction failure.

# Label patterns, matched case-insensitively. Order matters only for the
# verdict sentence (first label whose pattern matches the term wins); in the
# free-text fallback the EARLIEST non-negated match wins, so overlapping
# phrases ("teilweise rechtswidrig" ⊃ "rechtswidrig") resolve by position.
_ASSESSMENT_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "kein_verwaltungsakt",
        (
            r"\bkein(?:e[nrs]?)?\s+verwaltungsakt",
            r"\bkeine\s+verwaltungsaktqualität",
            r"\bnicht\s+um\s+einen\s+verwaltungsakt",
            r"\bkein\s+va\b",
        ),
    ),
    ("einordnung_offen", (r"\beinordnung\s+offen\b",)),
    (
        "teilweise_rechtswidrig",
        (r"\bteil(?:weise|s)\s+rechts(?:widrig|fehlerhaft)",),
    ),
    (
        "ueberwiegend_rechtmaessig",
        (
            r"\büberwiegend\s+rechtmäßig",
            r"\bim\s+wesentlichen\s+(?:korrekt|rechtmäßig)",
            r"\bkeine\s+durchgreifenden\s+fehler",
        ),
    ),
    ("rechtswidrig", (r"\bnicht\s+rechtmäßig", r"\brechtswidrig")),
    ("rechtmaessig", (r"\brechtmäßig",)),
)

_VERDICT_RE = re.compile(r"vorläufige\s+einordnung\s*:\s*([^.\n]*)", re.IGNORECASE)
# A negator among the last few words of the same clause cancels a match.
# "nicht nur" intensifies rather than negates ("nicht nur teilweise").
_NEGATORS = frozenset({"nicht", "kein", "keine", "keinen", "keiner", "keines", "weder", "nie"})
_NEGATION_WINDOW_WORDS = 3
_CLAUSE_BREAK_RE = re.compile(r"[.;:!?\n]|,\s")
# Postposed negation in the same clause: "Rechtswidrigkeit ist nicht
# erkennbar", "… liegt nicht vor". Applied to the text right after a match.
_POSTPOSED_NEGATION_RE = re.compile(
    r"\w*\s+(?:\w+\s+)?(?:nicht|kaum)\s+"
    r"(?:erkennbar|ersichtlich|gegeben|festzustellen|feststellbar|vor)\b"
)


def _is_negated(text: str, start: int, end: int) -> bool:
    """True if the match ``text[start:end]`` is negated within its clause."""
    if _POSTPOSED_NEGATION_RE.match(text, end):
        return True
    clause_start = 0
    for m in _CLAUSE_BREAK_RE.finditer(text, 0, start):
        clause_start = m.end()
    words = re.findall(r"\w+", text[clause_start:start])[-_NEGATION_WINDOW_WORDS:]
    for i, word in enumerate(words):
        if word in _NEGATORS:
            following = words[i + 1] if i + 1 < len(words) else ""
            if word == "nicht" and following == "nur":
                continue
            return True
    return False


def _first_label(text: str, *, by_position: bool) -> str | None:
    """Return the label of the first non-negated pattern match in ``text``.

    ``by_position`` False: label order decides (verdict sentence).
    ``by_position`` True: the earliest match in the text decides (fallback).
    """
    best: tuple[int, str] | None = None
    for label, patterns in _ASSESSMENT_PATTERNS:
        for pattern in patterns:
            for m in re.finditer(pattern, text):
                if _is_negated(text, m.start(), m.end()):
                    continue
                if not by_position:
                    return label
                if best is None or m.start() < best[0]:
                    best = (m.start(), label)
                break  # earliest non-negated hit of this pattern is enough
    return best[1] if best else None


def extract_assessment_from_pipeline(output: PipelineOutput) -> str | None:
    """Extract the overall assessment from the ``ergebnis`` section.

    1. The verdict sentence "Vorläufige Einordnung: <Begriff>." (prompt set
       3.0.0+) decides when present and its term is recognised.
    2. Otherwise the whole section is searched; negated mentions are
       ignored and the earliest remaining match wins.

    Returns
    -------
    str | None
        One of the goldset labels ``rechtswidrig``,
        ``teilweise_rechtswidrig``, ``ueberwiegend_rechtmaessig``,
        ``kein_verwaltungsakt``; or ``rechtmaessig`` / ``einordnung_offen``
        (real answers that no goldset label equals, so they score as a
        mismatch); or ``None`` if no assessment can be extracted.
    """
    text = output.final_output.get("ergebnis", "")
    if not text:
        return None

    text_lower = text.lower()

    verdict = _VERDICT_RE.search(text_lower)
    if verdict:
        label = _first_label(verdict.group(1), by_position=False)
        if label is not None:
            return label

    return _first_label(text_lower, by_position=True)


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
