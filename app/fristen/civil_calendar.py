"""Current civil-law calendar (module API 3.4; WP-131).

Statewide holidays from 2024 onward. Local holidays (including Augsburg,
Bavarian Assumption and local Corpus Christi) are supplied separately after
user confirmation. Legacy administrative calendar behavior stays unchanged.
"""

from __future__ import annotations

from datetime import date, timedelta

_STATES = frozenset("BB BE BW BY HB HE HH MV NI NW RP SH SL SN ST TH".split())
_FIXED_ALL = frozenset({(1, 1), (5, 1), (10, 3), (12, 25), (12, 26)})
_EPIPHANY = frozenset({"BW", "BY", "ST"})
_CORPUS_CHRISTI = frozenset({"BW", "BY", "HE", "NW", "RP", "SL"})
_REFORMATION = frozenset({"BB", "HB", "HH", "MV", "NI", "SH", "SN", "ST", "TH"})
_ALL_SAINTS = frozenset({"BW", "BY", "NW", "RP", "SL"})


def _easter(year: int) -> date:
    # Gregorian computus, avoiding the legacy boundary-year lookup fallback.
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    correction = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * correction) // 451
    month, day = divmod(h + correction - 7 * m + 114, 31)
    return date(year, month, day + 1)


def civil_is_holiday(day: date, land: str) -> bool:
    """Statewide public holiday; rejects dates before the supported 2024 regime."""
    if land not in _STATES or day.year < 2024:
        raise ValueError("Civil calendar requires a known Bundesland and year >= 2024")
    md = (day.month, day.day)
    if land == "BE" and day == date(2025, 5, 8):
        return True
    if md in _FIXED_ALL:
        return True
    fixed = (
        (md == (1, 6) and land in _EPIPHANY)
        or (md == (3, 8) and land in {"BE", "MV"})
        or (md == (8, 15) and land == "SL")
        or (md == (9, 20) and land == "TH")
        or (md == (10, 31) and land in _REFORMATION)
        or (md == (11, 1) and land in _ALL_SAINTS)
    )
    easter = _easter(day.year)
    delta = (day - easter).days
    if fixed or delta in {-2, 1, 39, 50} or (delta == 60 and land in _CORPUS_CHRISTI):
        return True
    # Buß- und Bettag is the Wednesday before 23 November, statewide only in SN.
    nov23 = date(day.year, 11, 23)
    penitence = nov23 - timedelta(days=(nov23.weekday() - 2) % 7 or 7)
    return land == "SN" and day == penitence


def civil_next_workday(day: date, land: str, additional: tuple[date, ...] = ()) -> date:
    """§ 193 BGB: Saturdays, Sundays and confirmed local/statewide holidays."""
    candidate = day
    while civil_is_holiday(candidate, land) or candidate.weekday() >= 5 or candidate in additional:
        candidate += timedelta(days=1)
    return candidate
