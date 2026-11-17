"""Law abbreviations the citation parser recognises (WP-114).

Domain-neutral catalog of German federal law abbreviations → canonical
spelling and, where the core corpus catalog carries the law, its corpus
source type. Recognising a law is independent of whether any module uses
it; verification can only confirm laws that have a source type.
"""

# Semantic Version: 1.0.0 | 2026-11-17 — WP-114: initial version.

from __future__ import annotations

import re

_ROMAN = {
    "I": 1,
    "II": 2,
    "III": 3,
    "IV": 4,
    "V": 5,
    "VI": 6,
    "VII": 7,
    "VIII": 8,
    "IX": 9,
    "X": 10,
    "XI": 11,
    "XII": 12,
    "XIV": 14,
}
_ROMAN_BY_NUMBER = {v: k for k, v in _ROMAN.items()}

#: SGB book number → corpus source type (core catalog, app/services/corpus.py).
_SGB_SOURCE_TYPES = {1: "sgb1", 2: "sgb2", 3: "sgb3", 9: "sgb9", 10: "sgbx", 12: "sgb12"}

#: Canonical abbreviation → corpus source type (None: recognised, not catalogued).
LAWS: dict[str, str | None] = {
    "BGB": "bgb",
    "SGG": "sgg",
    "VwVfG": "vwvfg",
    "ErbStG": "erbstg",
    "KSchG": "kschg",
    "BUrlG": "burlg",
    "TVG": "tvg",
    "HöfeO": "hoefev",
    "GG": None,
    "VwGO": None,
    "ZPO": None,
    "StPO": None,
    "StGB": None,
    "OWiG": None,
    "AO": None,
    "EStG": None,
    "HGB": None,
    "GVG": None,
    "InsO": None,
    "AufenthG": None,
    "AsylG": None,
    "AsylbLG": None,
    "WoGG": None,
    "BKGG": None,
    "BEEG": None,
    "UhVorschG": None,
    "BAföG": None,
    "RDG": None,
    "StVG": None,
    "StVO": None,
    "BetrVG": None,
    "ArbZG": None,
    "TzBfG": None,
    "MuSchG": None,
    "EGBGB": None,
    "FamFG": None,
    "RVG": None,
    "GKG": None,
    "BDSG": None,
    "DSGVO": None,
    "PostModG": None,
}

_SGB_RE = r"SGB\s?(?:XIV|XII|XI|X|IX|VIII|VII|VI|V|IV|III|II|I|1[0-4]|[1-9])(?![A-Za-z0-9])"
#: Alternation of every recognised abbreviation, longest first.
LAW_PATTERN = (
    "(?:"
    + _SGB_RE
    + "|"
    + "|".join(re.escape(k) for k in sorted(LAWS, key=len, reverse=True))
    + r")(?![A-Za-zÄÖÜäöüß])"
)


def normalise_law(text: str) -> tuple[str, str | None]:
    """``(canonical abbreviation, source type | None)`` of a matched law."""
    compact = " ".join(text.split())
    match = re.fullmatch(r"SGB\s?([IVX]+|\d+)", compact)
    if match:
        token = match.group(1)
        number = int(token) if token.isdigit() else _ROMAN[token]
        return f"SGB {_ROMAN_BY_NUMBER.get(number, str(number))}", _SGB_SOURCE_TYPES.get(number)
    return compact, LAWS.get(compact)


__all__ = ["LAWS", "LAW_PATTERN", "normalise_law"]
