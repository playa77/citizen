"""Intertemporal law selection — deterministic legal regime resolution.

This module determines which legal regime applies to a given period of time.
It is a pure, synchronous module with no async, no DB, and no LLM dependencies.

Regime boundaries (derived from major SGB II reforms):
  - before 2023-07-01: "a.F._vor_2023"        — pre-Bürgergeld
  - 2023-07-01 to 2024-12-31: "a.F._2023"      — Bürgergeld-Gesetz (sanction reform, § 11b)
  - 2025-01-01 to 2026-06-30: "a.F._2025"      — Regelbedarf update
  - 2026-07-01 onward: "n.F._2026"              — major reform (new age tiers, Vermögensfreibeträge)

Usage::

    from app.services.regime import legal_regime, regime_banner

    reg = legal_regime(date(2026, 5, 1))   # → "a.F._2025"
    print(regime_banner(reg))               # → "Achtung: Für diesen Zeitraum gilt die Rechtslage ..."
"""

# Semantic Version: 0.1.0

from __future__ import annotations

from datetime import date, timedelta
from typing import Final

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
    _banners: dict[str, str] = {
        REGIME_VOR_2023: (
            "ACHTUNG RECHTSLAGE: Für diesen Zeitraum gilt die Rechtslage vor dem "
            "01.07.2023 (alte Fassung, vor Bürgergeld-Gesetz). "
            "Bitte die bis 30.06.2023 geltenden Sanktionsregeln (§ 31 SGB II a.F.) "
            "und die alten Freibeträge anwenden."
        ),
        REGIME_2023: (
            "ACHTUNG RECHTSLAGE: Für diesen Zeitraum gilt die Rechtslage vom "
            "01.07.2023 bis 31.12.2024 (a.F., Bürgergeld-Gesetz). "
            "Bitte die ab 01.07.2023 geltenden Sanktionsregeln und "
            "Freibeitragsgrenzen nach § 11b SGB II anwenden."
        ),
        REGIME_2025: (
            "ACHTUNG RECHTSLAGE: Für diesen Zeitraum gilt die Rechtslage vom "
            "01.01.2025 bis 30.06.2026 (a.F., Regelbedarfsstufen 2025). "
            "Bitte die ab 01.01.2025 geltenden Regelbedarfssätze und "
            "Freibeitragsgrenzen anwenden."
        ),
        REGIME_2026: (
            "ACHTUNG RECHTSLAGE: Für diesen Zeitraum gilt die Rechtslage ab "
            "01.07.2026 (n.F.). Bitte die neuen Altersstufen, die neuen "
            "Vermögensfreibeträge und die geänderten Sanktionsregeln anwenden."
        ),
    }

    banner = _banners.get(regime)
    if banner is None:
        valid = ", ".join(sorted(_banners))
        raise ValueError(f"Unbekanntes Regime: {regime!r}. Gültige Werte: {valid}")
    return banner
