"""Offline checks on plain-language copy: readability and duty of care (WP-122/WP-123).

* **Readability** — words per sentence against the register's limit
  (``app/plain/languages.py``). A crude but reproducible measure; it does not
  replace the human review OQ-3 asks for, it keeps reviewed copy from
  drifting back into Amtsdeutsch.
* **Duty of care** (``docs/duty-of-care-checklist.md``) — no discouraging
  language: copy must never tell a person that acting is pointless or that
  their chances are bad. Whether a remedy has prospects is for the lawyer or
  advice centre, and discouragement is exactly what makes people miss
  deadlines. Matching is case-insensitive on word boundaries.
"""

# Semantic Version: 1.0.0 | 2026-11-17 — WP-122/WP-123: initial version.

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator, Mapping
from typing import Any

#: Discouraging phrases (DE/EN). Extend, never shorten without a D-entry.
DISCOURAGING_PHRASES: tuple[str, ...] = (
    "aussichtslos",
    "hoffnungslos",
    "zwecklos",
    "sinnlos",
    "keine chance",
    "keine aussicht",
    "lohnt sich nicht",
    "bringt nichts",
    "vergeblich",
    "zu spät",
    "nichts mehr tun",
    "selbst schuld",
    "hopeless",
    "pointless",
    "no chance",
    "not worth",
    "too late",
    "nothing you can do",
    "your own fault",
)

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-ZÄÖÜ0-9„\"(])")
# Abbreviations whose dot does not end a sentence (kept short on purpose).
_ABBREV = re.compile(r"\b(z\.\s?B|d\.\s?h|u\.\s?a|bzw|Abs|Nr|S|Art|ca|vgl|e\.g|i\.e)\.", re.I)
_WORD = re.compile(r"[^\W\d_][\w'\u2019-]*|\d+", re.UNICODE)


def iter_texts(node: Any, path: str = "") -> Iterator[tuple[str, str]]:
    """Every string leaf of a copy document as ``(path, text)``, skipping metadata."""
    if isinstance(node, Mapping):
        for key, value in node.items():
            if path == "" and key in ("format", "module", "language", "review"):
                continue
            yield from iter_texts(value, f"{path}/{key}" if path else str(key))
    elif isinstance(node, list):
        for idx, value in enumerate(node):
            yield from iter_texts(value, f"{path}[{idx}]")
    elif isinstance(node, str):
        yield path, node


def sentences(text: str) -> list[str]:
    protected = _ABBREV.sub(lambda m: m.group(0).replace(".", "\u2024"), text)
    parts = _SENTENCE_END.split(protected.replace("\n", " "))
    return [p.replace("\u2024", ".").strip() for p in parts if p.strip()]


def words(sentence: str) -> list[str]:
    # Placeholders count as one word each ("{frist_ende}" → a date phrase).
    return _WORD.findall(re.sub(r"\{[a-z_]+\}", "X", sentence))


def long_sentences(text: str, limit: int) -> list[tuple[int, str]]:
    return [(len(w), s) for s in sentences(text) if len(w := words(s)) > limit]


def discouraging_hits(text: str, extra: Iterable[str] = ()) -> list[str]:
    lowered = text.lower()
    hits: list[str] = []
    for phrase in (*DISCOURAGING_PHRASES, *extra):
        if re.search(rf"(?<!\w){re.escape(phrase.lower())}(?!\w)", lowered):
            hits.append(phrase)
    return hits


__all__ = [
    "DISCOURAGING_PHRASES",
    "discouraging_hits",
    "iter_texts",
    "long_sentences",
    "sentences",
    "words",
]
