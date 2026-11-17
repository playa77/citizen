"""Citation parser for German legal texts (WP-114).

Finds three kinds of citation, each with its character span:

``statute``  ``§ 44 Abs. 1 Satz 2 SGB X`` · ``§§ 11, 11b SGB II`` ·
             ``§§ 535 ff. BGB`` · ``§ 11b Abs. 3 S. 2 Nr. 1–3 SGB II`` ·
             ``Art. 3 Abs. 1 GG`` · a ``§`` without a recognised law is
             reported with ``law: null`` (it cannot be verified).
``ecli``     European Case Law Identifier, e.g. ``ECLI:DE:BSG:2019:…``.
``docket``   BSG docket numbers (``B 4 AS 19/18 R``).

Deterministic and LLM-free; the regexes are bounded (no nested
quantifiers over unbounded text), so parsing stays linear in the input.
"""

# Semantic Version: 1.0.0 | 2026-11-17 — WP-114: initial version.

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.citations.laws import LAW_PATTERN, normalise_law

_UNIT = r"\d{1,4}[a-z]?"
_SEP = r"(?:\s*(?:,|und|bis|–|-|/)\s*)"
_PART = (
    r"(?:\s*(?:Abs\.|Absatz|S\.|Satz|Nr\.|Nummer|Buchst\.|Buchstabe|lit\.|Halbs\.|Halbsatz"
    r"|Alt\.|Alternative|UAbs\.)\s*(?:\d{1,3}[a-z]?|[a-z]\))"
    r"(?:" + _SEP + r"(?:\d{1,3}[a-z]?|[a-z]\)))*)"
)
_FF = r"(?:\s*ff?\.)"
_STATUTE_RE = re.compile(
    r"(?P<sign>§§|§|Art\.|Artikel)\s*"
    r"(?P<body>" + _UNIT + r"(?:" + _PART + r"|" + _FF + r"|" + _SEP + _UNIT + r")*)"
    r"(?:\s+(?:des|der|dem|im|in der)?\s*)?"
    r"(?P<law>" + LAW_PATTERN + r")?"
)
_ECLI_RE = re.compile(r"\bECLI:[A-Z]{2}:[A-Z0-9.]{1,7}:\d{4}:[A-Z0-9.]{1,25}\b", re.IGNORECASE)
_DOCKET_RE = re.compile(r"\bB\s\d{1,2}\s[A-Z]{1,3}\s\d{1,4}/\d{2}\s[A-Z]{1,2}\b")

_ABS_RE = re.compile(r"(?:Abs\.|Absatz)\s*(\d{1,3}[a-z]?)")
_SATZ_RE = re.compile(r"(?:\bS\.|Satz)\s*(\d{1,3})")
_NR_RE = re.compile(r"(?:Nr\.|Nummer)\s*(\d{1,3}[a-z]?)")


@dataclass(frozen=True)
class Citation:
    kind: str  # statute | ecli | docket
    text: str
    start: int
    end: int
    law: str | None = None
    source_type: str | None = None
    paragraphs: tuple[str, ...] = ()  # "44", "11b", ranges as "11–11b"
    absatz: str | None = None
    satz: str | None = None
    nummer: str | None = None
    ff: bool = False
    article: bool = False  # "Art." instead of "§"
    identifier: str | None = None  # normalised ECLI / docket
    extra: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "text": self.text,
            "span": [self.start, self.end],
            "law": self.law,
            "source_type": self.source_type,
            "paragraphs": list(self.paragraphs),
            "absatz": self.absatz,
            "satz": self.satz,
            "nummer": self.nummer,
            "ff": self.ff,
            "article": self.article,
            "identifier": self.identifier,
        }


def _paragraph_list(body: str) -> tuple[str, ...]:
    """Cited §/Art. numbers of *body*: the units outside Abs./Satz/Nr. parts."""
    stripped = re.sub(_PART, " ", body)
    stripped = re.sub(_FF, " ", stripped)
    units = re.findall(r"(" + _UNIT + r")(\s*(?:bis|–|-)\s*(" + _UNIT + r"))?", stripped)
    result: list[str] = []
    for first, range_part, last in units:
        result.append(f"{first}–{last}" if range_part else first)
    return tuple(result)


def _statutes(text: str) -> list[Citation]:
    citations: list[Citation] = []
    for match in _STATUTE_RE.finditer(text):
        body = match.group("body")
        law_text = match.group("law")
        law, source_type = normalise_law(law_text) if law_text else (None, None)
        end = match.end("law") if law_text else match.end("body")
        first_part = re.split(_SEP + _UNIT, body, maxsplit=1)[0]
        absatz = _ABS_RE.search(first_part)
        satz = _SATZ_RE.search(first_part)
        nummer = _NR_RE.search(first_part)
        citations.append(
            Citation(
                kind="statute",
                text=text[match.start() : end],
                start=match.start(),
                end=end,
                law=law,
                source_type=source_type,
                paragraphs=_paragraph_list(body),
                absatz=absatz.group(1) if absatz else None,
                satz=satz.group(1) if satz else None,
                nummer=nummer.group(1) if nummer else None,
                ff=bool(re.search(_FF, body)),
                article=match.group("sign").startswith("Art"),
            )
        )
    return citations


def parse_citations(text: str) -> list[Citation]:
    """Every citation in *text*, ordered by position."""
    found = _statutes(text)
    for match in _ECLI_RE.finditer(text):
        found.append(
            Citation(
                kind="ecli",
                text=match.group(0),
                start=match.start(),
                end=match.end(),
                identifier=match.group(0).upper(),
            )
        )
    for match in _DOCKET_RE.finditer(text):
        found.append(
            Citation(
                kind="docket",
                text=match.group(0),
                start=match.start(),
                end=match.end(),
                identifier=match.group(0),
                extra={"court": "BSG"},
            )
        )
    return sorted(found, key=lambda c: (c.start, c.end))


__all__ = ["Citation", "parse_citations"]
