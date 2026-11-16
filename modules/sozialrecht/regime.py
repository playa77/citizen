"""Intertemporal law selection — deterministic legal regime resolution.

This module determines which legal regime applies to a given period of time.
It is a pure, synchronous module with no async, no DB, and no LLM dependencies.

Regime boundaries (derived from major SGB II reforms):
  - before 2023-07-01: "a.F._vor_2023"        — pre-Bürgergeld
  - 2023-07-01 to 2024-12-31: "a.F._2023"      — Bürgergeld-Gesetz (sanction reform, § 11b)
  - 2025-01-01 to 2026-06-30: "a.F._2025"      — Regelbedarf update
  - 2026-07-01 onward: "n.F._2026"              — major reform (new age tiers, Vermögensfreibeträge)

Module code of ``sozialrecht`` (WP-93: moved from ``app/services/regime.py``;
generalised by the core as an ``app.modules.sdk.RegimeProvider``, exported as
``REGIME_PROVIDER`` below and declared in ``module.yaml`` under
``regimes.provider``). The core reaches it only through
``app.modules.runtime.regime_banner_for``.

Usage (inside the module)::

    from .regime import legal_regime, regime_banner

    reg = legal_regime(date(2026, 5, 1))   # → "a.F._2025"
    print(regime_banner(reg))  # → "Achtung: Für diesen Zeitraum gilt …"
"""

# Semantic Version: 0.3.0 | 2026-11-16 — prompt set 3.0.0: banners state segment
# and dates only (F-24, F-13); reference_period() reads the reference date from
# the document (CR-06, F-06).
# 0.2.0

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Final

from app.modules.sdk import ReferencePeriod, RegimeProvider

# ---------------------------------------------------------------------------
# Regime boundary dates
# ---------------------------------------------------------------------------

_BOUNDARY_2023: Final[date] = date(2023, 7, 1)
_BOUNDARY_2025: Final[date] = date(2025, 1, 1)
_BOUNDARY_2026: Final[date] = date(2026, 7, 1)

# Regime tags (used as values in LegalParameter.regime and as cache keys).
REGIME_VOR_2023: Final[str] = "a.F._vor_2023"
REGIME_2023: Final[str] = "a.F._2023"
REGIME_2025: Final[str] = "a.F._2025"
REGIME_2026: Final[str] = "n.F._2026"


def regime_transition_dates() -> list[date]:
    """Return the regime boundary dates in chronological order.

    Returns
    -------
    list[date]
        ``[2023-07-01, 2025-01-01, 2026-07-01]``
    """
    return [_BOUNDARY_2023, _BOUNDARY_2025, _BOUNDARY_2026]


def legal_regime(period_month: date) -> str:
    """Return the legal regime tag for a given month.

    Parameters
    ----------
    period_month :
        Any date within the period of interest. Only the year/month portion
        is semantically meaningful for regime determination.

    Returns
    -------
    str
        One of ``"a.F._vor_2023"``, ``"a.F._2023"``, ``"a.F._2025"``,
        ``"n.F._2026"``.

    Examples
    --------
    >>> legal_regime(date(2023, 6, 30))
    'a.F._vor_2023'
    >>> legal_regime(date(2023, 7, 1))
    'a.F._2023'
    >>> legal_regime(date(2026, 7, 1))
    'n.F._2026'
    """
    if period_month < _BOUNDARY_2023:
        return REGIME_VOR_2023
    if period_month < _BOUNDARY_2025:
        return REGIME_2023
    if period_month < _BOUNDARY_2026:
        return REGIME_2025
    return REGIME_2026


def regime_for_period_range(start: date, end: date) -> list[tuple[date, date, str]]:
    """Split a date range into contiguous segments with their regimes.

    When a period spans one or more regime boundaries, the range is split
    at each boundary so that each segment falls entirely within one regime.
    Each segment is returned as ``(start, end, regime_tag)``.

    Parameters
    ----------
    start :
        Start of the period (inclusive).
    end :
        End of the period (inclusive). Must be ``>= start``.

    Returns
    -------
    list[tuple[date, date, str]]
        Chronologically ordered list of ``(start, end, regime)`` tuples.

    Examples
    --------
    >>> regime_for_period_range(date(2026, 5, 1), date(2026, 8, 31))
    [(date(2026, 5, 1), date(2026, 6, 30), 'a.F._2025'),
     (date(2026, 7, 1), date(2026, 8, 31), 'n.F._2026')]

    >>> regime_for_period_range(date(2025, 6, 1), date(2025, 6, 30))
    [(date(2025, 6, 1), date(2025, 6, 30), 'a.F._2025')]
    """
    if end < start:
        raise ValueError(f"end ({end}) must be >= start ({start})")

    boundaries = regime_transition_dates()
    segments: list[tuple[date, date, str]] = []

    cursor = start
    while cursor <= end:
        # Find the next boundary strictly within the remaining range (cursor < b <= end).
        next_boundary: date | None = None
        for b in boundaries:
            if cursor < b <= end:
                next_boundary = b
                break

        if next_boundary is not None:
            # Segment runs from cursor up to the day before the boundary.
            seg_end = next_boundary - timedelta(days=1)
            regime = legal_regime(cursor)
            segments.append((cursor, seg_end, regime))
            cursor = next_boundary
        else:
            # No more boundaries in range — add the remainder.
            regime = legal_regime(cursor)
            segments.append((cursor, end, regime))
            break  # cursor is past end; we're done

    return segments


def regime_banner(regime: str) -> str:
    """Return a German-language regime awareness banner for LLM prompt injection.

    Parameters
    ----------
    regime :
        One of the four regime tags returned by :func:`legal_regime`.

    Returns
    -------
    str
        Human-readable banner string in German, suitable for prepending to
        LLM system prompts or user messages.

    Raises
    ------
    ValueError
        If *regime* is not a recognised tag.
    """
    # Prompt set 3.0.0 (P-16, F-24): each banner names the segment and its
    # dates only. The v2 texts asserted reform content this project could not
    # verify (and dated the Bürgergeld sanction reform to 01.07.2023 instead of
    # 01.01.2023); amounts come from the engine, not from the banner. The core
    # wraps the banner in <rechtsstand> with the reference date and the rule
    # for choosing the version of the law (app.modules.runtime.regime_block_for).
    _banners: dict[str, str] = {
        REGIME_VOR_2023: (
            "Rechtsstand-Segment a.F._vor_2023 (Stichtag vor dem 01.07.2023). Das "
            "Bürgergeld-Gesetz hat das SGB II zum 01.01.2023 und zum 01.07.2023 geändert; "
            "für Stichtage im ersten Halbjahr 2023 kann daher bereits dessen erste Stufe "
            "gelten."
        ),
        REGIME_2023: (
            "Rechtsstand-Segment a.F._2023 (Stichtag 01.07.2023 bis 31.12.2024): SGB II in der "
            "Fassung des Bürgergeld-Gesetzes einschließlich der zum 01.07.2023 in Kraft "
            "getretenen Änderungen."
        ),
        REGIME_2025: (
            "Rechtsstand-Segment a.F._2025 (Stichtag 01.01.2025 bis 30.06.2026): SGB II in der "
            "in diesem Zeitraum geltenden Fassung."
        ),
        REGIME_2026: (
            "Rechtsstand-Segment n.F._2026 (Stichtag ab 01.07.2026): SGB II in der ab "
            "01.07.2026 geltenden Fassung."
        ),
    }

    banner = _banners.get(regime)
    if banner is None:
        valid = ", ".join(sorted(_banners))
        raise ValueError(f"Unbekanntes Regime: {regime!r}. Gültige Werte: {valid}")
    return banner


# ---------------------------------------------------------------------------
# Reference period from the document (CR-06, F-06)
# ---------------------------------------------------------------------------

_DATE = r"(\d{1,2})\.(\d{1,2})\.(\d{4})"
_RANGE_SEP = r"\s*(?:bis(?:\s+zum|\s+einschließlich)?|–|-)\s*"
#: Benefit period introduced by its usual wording in SGB II notices.
_PERIOD_RE = re.compile(
    r"(?:Bewilligungszeitraum|Leistungszeitraum|Zeitraum|für\s+die\s+Zeit)"
    r"\s*(?:vom|von|:)?\s*" + _DATE + _RANGE_SEP + _DATE,
    re.IGNORECASE,
)
#: Any "TT.MM.JJJJ bis TT.MM.JJJJ" range (second choice).
_RANGE_RE = re.compile(_DATE + _RANGE_SEP + _DATE)
#: Date of the letter, most specific first: a header line "<Ort>, [den]
#: TT.MM.JJJJ", then "Datum: …", then "Bescheid vom …". "Schreiben vom …" is
#: deliberately absent: in notices it usually cites an *earlier* letter.
_LETTER_DATE_RES: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"^[ \t]*[A-ZÄÖÜ][\wÄÖÜäöüß.\- ]{1,40},[ \t]*(?:den[ \t]+)?" + _DATE + r"[ \t]*$", re.M
    ),
    re.compile(r"Datum\s*:\s*" + _DATE, re.IGNORECASE),
    re.compile(r"Bescheid\s+vom\s+" + _DATE, re.IGNORECASE),
)
#: Longest plausible benefit period (12 months plus slack); longer ranges are
#: not a benefit period (e.g. "Bewilligung seit 2019 bis 2026").
_MAX_PERIOD_DAYS = 400


def _to_date(day: str, month: str, year: str) -> date | None:
    try:
        value = date(int(year), int(month), int(day))
    except ValueError:
        return None
    return value if 2000 <= value.year <= 2100 else None


def _first_range(pattern: re.Pattern[str], text: str) -> tuple[date, date] | None:
    for match in pattern.finditer(text):
        start = _to_date(*match.group(1, 2, 3))
        end = _to_date(*match.group(4, 5, 6))
        if start and end and 0 < (end - start).days <= _MAX_PERIOD_DAYS:
            return start, end
    return None


def reference_period(document_text: str) -> ReferencePeriod:
    """Reference period of an SGB II document, deterministically (no LLM).

    Order: an explicitly introduced benefit period ("Bewilligungszeitraum",
    "für die Zeit vom … bis …"), then any plausible date range, then the
    letter date. ``(None, None, "")`` when nothing matches — the core then
    falls back to the current date and says so in the prompt.
    """
    found = _first_range(_PERIOD_RE, document_text)
    if found:
        return found[0], found[1], "Beginn des Leistungszeitraums laut Dokument"
    found = _first_range(_RANGE_RE, document_text)
    if found:
        return found[0], found[1], "Beginn des im Dokument genannten Zeitraums"
    for pattern in _LETTER_DATE_RES:
        for match in pattern.finditer(document_text):
            letter = _to_date(*match.group(1, 2, 3))
            if letter:
                return letter, None, "Datum des Schreibens laut Dokument"
    return None, None, ""


#: The module's ``RegimeProvider`` (ARCHITECTURE.md § 2.4), declared in
#: ``module.yaml`` as ``regimes.provider: regime:REGIME_PROVIDER``.
REGIME_PROVIDER = RegimeProvider(
    regime_for=legal_regime, banner=regime_banner, reference_period=reference_period
)
