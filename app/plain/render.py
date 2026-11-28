"""Render plain-language copy for findings and deadlines (WP-122, D-068).

Nothing here generates language. Copy is fixed module text; the renderer
picks the entry and fills whitelisted placeholders from deterministic data:

* deadline placeholders come from the Fristen core's result items
  (``app/dossier/deadlines.py``) — dates are never taken from LLM output;
* the finding category is read from the opening sentence of the analysis
  ``ergebnis`` ("Vorläufige Einordnung: <Begriff>.", prompt set 3.0.0). The
  term is matched against the module's closed category vocabulary; anything
  else falls back to the open category with ``category_source: "fallback"``,
  so an off-vocabulary model answer can never select reassuring copy.
"""

# Semantic Version: 1.0.0 | 2026-11-17 — WP-122: initial version.

from __future__ import annotations

import re
import string
from collections.abc import Iterable, Mapping, Sequence
from datetime import date
from typing import Any

from app.modules.registry import ModuleManifest
from app.plain.copy import (
    OPEN_CATEGORY_TERM,
    FindingCategory,
    PlainCopyError,
    category_key,
    copy_languages,
    finding_categories,
    load_copy,
)
from app.plain.languages import format_date, register_for

PLAIN_SPEC_VERSION = "citizen-plain-v1.0"

#: Placeholders a copy text may use, and the deadline-item field each reads.
DEADLINE_PLACEHOLDERS: dict[str, str] = {
    "frist_ende": "frist_ende",
    "bekanntgabe": "bekanntgabe",
    "oq1_alternate_ende": "oq1_alternate_ende",
    "basis": "basis",
}
_DATE_FIELDS = {"frist_ende", "bekanntgabe", "oq1_alternate_ende"}

_OPENING = re.compile(r"Vorläufige\s+Einordnung\s*:\s*(?P<term>[^.\n]+)", re.IGNORECASE)


class MissingPlaceholderValue(KeyError):
    """A copy text needs a value the deadline item does not carry."""


def placeholders(text: str) -> list[str]:
    """Field names used in *text* (``{name}``)."""
    return [name for _, name, _, _ in string.Formatter().parse(text) if name]


# ---------------------------------------------------------------------------
# Findings
# ---------------------------------------------------------------------------


def classify_ergebnis(
    ergebnis: str | None, categories: Sequence[FindingCategory]
) -> tuple[FindingCategory, str]:
    """Return ``(category, source)``; source is ``"ergebnis"`` or ``"fallback"``."""
    open_cat = next(c for c in categories if c.term == OPEN_CATEGORY_TERM)
    match = _OPENING.search(ergebnis or "")
    if match is None:
        return open_cat, "fallback"
    found = category_key(match.group("term"))
    exact = [c for c in categories if c.key == found]
    if exact:
        return exact[0], "ergebnis"
    # "teilweise rechtswidrig (Unterkunftskosten)" → longest matching prefix,
    # so "teilweise_rechtswidrig" wins over "rechtswidrig".
    prefixed = sorted(
        (c for c in categories if found.startswith(c.key + "_")),
        key=lambda c: len(c.key),
        reverse=True,
    )
    if prefixed:
        return prefixed[0], "ergebnis"
    return open_cat, "fallback"


def _lang_block(doc: Mapping[str, Any], language: str) -> dict[str, Any]:
    reg = register_for(language)
    review = doc.get("review") or {}
    return {
        "language": language,
        "bcp47": reg.bcp47,
        "register": reg.register,
        "review_status": review.get("status", "draft"),
    }


def render_finding(
    manifest: ModuleManifest, ergebnis: str | None, languages: Iterable[str]
) -> dict[str, Any]:
    """Plain-language finding for one module, every requested language."""
    category, source = classify_ergebnis(ergebnis, finding_categories(manifest))
    texts: dict[str, Any] = {}
    missing: list[str] = []
    available = set(copy_languages(manifest))
    for language in languages:
        if language not in available:
            missing.append(language)
            continue
        doc = load_copy(manifest, language)
        entry = (doc.get("findings") or {}).get(category.key)
        if entry is None:
            missing.append(language)
            continue
        texts[language] = {**_lang_block(doc, language), **entry}
    return {
        "module_id": manifest.id,
        "category": category.key,
        "category_term": category.term,
        "category_source": source,
        "texts": texts,
        "missing_languages": missing,
    }


# ---------------------------------------------------------------------------
# Deadlines
# ---------------------------------------------------------------------------


def _value(item: Mapping[str, Any], field: str, language: str) -> str:
    raw = item.get(DEADLINE_PLACEHOLDERS[field])
    if raw in (None, ""):
        raise MissingPlaceholderValue(field)
    if field in _DATE_FIELDS:
        return format_date(date.fromisoformat(str(raw)), language)
    return str(raw)


def deadline_text(
    entry: Mapping[str, Any], item: Mapping[str, Any], language: str
) -> tuple[str, str]:
    """``(text_key, rendered text)`` for one deadline item.

    Lookup order: ``<status>.<frist_typ>`` then ``<status>``. Raises
    :class:`PlainCopyError` if neither exists and
    :class:`MissingPlaceholderValue` if the text needs a value the item lacks.
    """
    texts: Mapping[str, str] = entry.get("texts") or {}
    status = str(item.get("status"))
    frist_typ = item.get("frist_typ")
    keys = ([f"{status}.{frist_typ}"] if frist_typ else []) + [status]
    for key in keys:
        if key in texts:
            template = texts[key]
            values = {name: _value(item, name, language) for name in placeholders(template)}
            return key, template.format(**values)
    raise PlainCopyError(f"no copy text for deadline status {keys!r}")


def render_deadline(
    manifest: ModuleManifest, item: Mapping[str, Any], languages: Iterable[str]
) -> dict[str, Any]:
    """One deadline item (Fristen-core output) plus its plain texts."""
    texts: dict[str, Any] = {}
    missing: list[str] = []
    referral_required = False
    available = set(copy_languages(manifest))
    for language in languages:
        if language not in available:
            missing.append(language)
            continue
        doc = load_copy(manifest, language)
        entry = (doc.get("deadlines") or {}).get(str(item.get("spec_id")))
        if entry is None:
            missing.append(language)
            continue
        if (
            entry.get("referral_when_not_applicable") is True
            and item.get("severity") == "critical"
            and item.get("status") == "not_applicable"
        ):
            referral_required = True
        try:
            key, text = deadline_text(entry, item, language)
        except (PlainCopyError, MissingPlaceholderValue):
            missing.append(language)
            continue
        texts[language] = {
            **_lang_block(doc, language),
            "title": entry["title"],
            "text": text,
            "text_key": key,
            "action": entry["action"],
        }
    return {
        "module_id": item.get("module_id"),
        "spec_id": item.get("spec_id"),
        "severity": item.get("severity"),
        "status": item.get("status"),
        "frist_typ": item.get("frist_typ"),
        "frist_ende": item.get("frist_ende"),
        "texts": texts,
        "missing_languages": missing,
        **({"referral_required": True} if referral_required else {}),
    }


#: Statuses that call for the person's action (not "not_applicable").
_ACTIONABLE = ("computed", "provisional", "missing_input")


def deadline_banner(rendered: Sequence[Mapping[str, Any]]) -> dict[str, Any] | None:
    """The deadline a client must show first and prominently (WP-121 banner).

    The earliest-ending *critical* actionable deadline; a critical deadline
    that could not be computed (``missing_input``) outranks every computed
    one, because the person does not yet know how much time is left.
    """
    critical = [
        d
        for d in rendered
        if d.get("severity") == "critical"
        and (d.get("status") in _ACTIONABLE or d.get("referral_required") is True)
    ]
    if not critical:
        return None

    def rank(d: Mapping[str, Any]) -> tuple[int, str]:
        if d.get("status") == "missing_input":
            return (0, "")
        if d.get("status") == "not_applicable":
            return (2, "")
        return (1, str(d.get("frist_ende") or "9999-12-31"))

    first = min(critical, key=rank)
    return {"module_id": first.get("module_id"), "spec_id": first.get("spec_id")}


__all__ = [
    "DEADLINE_PLACEHOLDERS",
    "PLAIN_SPEC_VERSION",
    "MissingPlaceholderValue",
    "classify_ergebnis",
    "deadline_banner",
    "deadline_text",
    "placeholders",
    "render_deadline",
    "render_finding",
]
