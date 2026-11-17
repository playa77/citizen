"""Plain-language registers and date formatting (WP-122, D-068).

The language key is the copy-file key (``de``, ``de-LS``, ``en``, …).
Leichte Sprache has no BCP 47 subtag of its own, so ``bcp47`` gives the tag a
client must put into the HTML ``lang`` attribute for screen readers (WP-123):
``de-LS`` text is German and is announced as German.

Dates are spelled out with the weekday (``Montag, 21. Dezember 2026``): a
deadline must be unambiguous to a reader who does not know the numeric
format, and the weekday is a cross-check a person can make with a calendar.
No locale database is used, so the output does not depend on the host.
"""

# Semantic Version: 1.0.0 | 2026-11-17 — WP-122: initial version.

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Register:
    language: str
    bcp47: str
    register: str
    label_de: str
    label_en: str
    #: Readability gate: maximum words per sentence (eval.plain_eval).
    max_sentence_words: int


#: Known registers. Further languages (module need, e.g. M7) fall back to
#: :func:`register_for`'s generic register.
REGISTERS: dict[str, Register] = {
    "de": Register("de", "de", "buergersprache", "Bürgersprache", "Plain German", 22),
    "de-LS": Register(
        "de-LS", "de", "leichte_sprache", "Leichte Sprache", "Easy-to-read German", 14
    ),
    "en": Register("en", "en", "plain_en", "Einfaches Englisch", "Plain English", 22),
}

#: Languages every verified module ships for all copy (roadmap WP-122).
REQUIRED_LANGUAGES: tuple[str, ...] = ("de", "en")
#: Language required for critical copy (critical deadlines, disclaimer).
CRITICAL_LANGUAGE = "de-LS"

_WEEKDAYS = {
    "de": ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"),
    "en": ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"),
}
_MONTHS = {
    "de": (
        "Januar", "Februar", "März", "April", "Mai", "Juni",
        "Juli", "August", "September", "Oktober", "November", "Dezember",
    ),
    "en": (
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December",
    ),
}  # fmt: skip


def register_for(language: str) -> Register:
    known = REGISTERS.get(language)
    if known is not None:
        return known
    base = language.split("-", 1)[0]
    return Register(language, base, "plain", language, language, 22)


def format_date(value: date, language: str) -> str:
    """Spell out *value* for *language* (German forms for every ``de*``)."""
    family = "de" if language.startswith("de") else "en"
    if family not in _WEEKDAYS or not language.startswith(("de", "en")):
        # Unknown language family: ISO date is unambiguous and translatable.
        return value.isoformat()
    weekday = _WEEKDAYS[family][value.weekday()]
    month = _MONTHS[family][value.month - 1]
    if family == "de":
        return f"{weekday}, {value.day}. {month} {value.year}"
    return f"{weekday}, {value.day} {month} {value.year}"


__all__ = [
    "CRITICAL_LANGUAGE",
    "REGISTERS",
    "REQUIRED_LANGUAGES",
    "Register",
    "format_date",
    "register_for",
]
