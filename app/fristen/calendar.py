"""German holiday calendar per Bundesland (moved verbatim from
``app/services/fristen.py``, WP-92).

Covers fixed common holidays, Bundesland-specific fixed holidays and
movable holidays (Easter-relative, incl. Fronleichnam and Mariä
Himmelfahrt per state) for 2024-2027. Years outside the table reuse the
boundary year's pattern — see ``_movable_holidays``.

Names are public here (``is_holiday``, ``is_workday``, ``next_workday``,
``same_day_next_month``, ``same_day_next_year``, ``weekday_name``); the
pre-split underscore spellings remain importable via the
``app.services.fristen`` compatibility shim.
"""

# Semantic Version: 0.1.0

from __future__ import annotations

import calendar
from datetime import date, timedelta

# ---------------------------------------------------------------------------
# Holiday tables
# ---------------------------------------------------------------------------

# Fixed holidays common to all Bundesländer.
_FIXED_ALL: list[tuple[int, int]] = [
    (1, 1),  # Neujahr
    (5, 1),  # Tag der Arbeit
    (10, 3),  # Tag der Deutschen Einheit
    (12, 25),  # 1. Weihnachtstag
    (12, 26),  # 2. Weihnachtstag
]

# Bundesland-specific fixed holidays.
# Key: Bundesland ISO code.
_FIXED_BY_STATE: dict[str, list[tuple[int, int]]] = {
    "NW": [
        (11, 1),  # Allerheiligen
        (10, 31),  # Reformationstag (seit 2018)
    ],
    "BY": [
        (1, 6),  # Heilige Drei Könige
        (8, 15),  # Mariä Himmelfahrt
    ],
    "BW": [
        (1, 6),  # Heilige Drei Könige
        (8, 15),  # Mariä Himmelfahrt
    ],
    "ST": [
        (1, 6),  # Heilige Drei Könige
        (10, 31),  # Reformationstag
    ],
    "RP": [
        (8, 15),  # Mariä Himmelfahrt
    ],
    "SL": [
        (8, 15),  # Mariä Himmelfahrt
    ],
    "SN": [
        (10, 31),  # Reformationstag
    ],
    "TH": [
        (10, 31),  # Reformationstag
    ],
    "BB": [
        (10, 31),  # Reformationstag
    ],
    "MV": [
        (10, 31),  # Reformationstag
    ],
    "HB": [
        (10, 31),  # Reformationstag (seit 2018)
    ],
    "SH": [
        (10, 31),  # Reformationstag (seit 2018)
    ],
    "NI": [
        (10, 31),  # Reformationstag (seit 2018)
    ],
    "HH": [
        (10, 31),  # Reformationstag (seit 2018)
    ],
    "HE": [],  # Hessen has no additional state-specific fixed holidays beyond common
    "BE": [],  # Berlin
}

# Easter dates for years 2024-2027.
_EASTER: dict[int, tuple[int, int]] = {
    2024: (3, 31),
    2025: (4, 20),
    2026: (4, 5),
    2027: (3, 28),
}

# States that observe Fronleichnam.
_FRONLEICHNAM_STATES: frozenset[str] = frozenset({"BY", "BW", "HE", "NW", "RP", "SL"})

# States that observe Mariä Himmelfahrt (full state — varies within BY).
_MARIA_HIMMELFAHRT_STATES: frozenset[str] = frozenset({"BW", "BY", "NW", "RP", "SL"})

_WEEKDAY_NAMES: dict[int, str] = {
    0: "Montag",
    1: "Dienstag",
    2: "Mittwoch",
    3: "Donnerstag",
    4: "Freitag",
    5: "Samstag",
    6: "Sonntag",
}

_NON_WORKDAY_NAMES: dict[int, str] = {5: "Samstag", 6: "Sonntag"}


def _movable_holidays(year: int) -> list[tuple[int, int]]:
    """Return list of (month, day) for movable holidays in *year* (2024-2027).

    If the year falls outside the lookup range, the boundary year's pattern
    is repeated (last available).
    """
    clamped = max(min(year, max(_EASTER.keys())), min(_EASTER.keys()))
    em, ed = _EASTER[clamped]
    easter = date(clamped, em, ed)

    holidays: list[tuple[int, int]] = [
        _date_to_tuple(easter - timedelta(days=2)),  # Karfreitag
        _date_to_tuple(easter + timedelta(days=1)),  # Ostermontag
        _date_to_tuple(easter + timedelta(days=39)),  # Christi Himmelfahrt
        _date_to_tuple(easter + timedelta(days=50)),  # Pfingstmontag
    ]

    return holidays


def _fronleichnam(year: int) -> date:
    """Return the Fronleichnam date for *year* (60 days after Easter)."""
    clamped = max(min(year, max(_EASTER.keys())), min(_EASTER.keys()))
    em, ed = _EASTER[clamped]
    easter = date(clamped, em, ed)
    return easter + timedelta(days=60)


def _date_to_tuple(d: date) -> tuple[int, int]:
    """Convert a date to (month, day) tuple for holiday lookup."""
    return (d.month, d.day)


def is_holiday(d: date, bundesland: str) -> bool:
    """Check whether *d* is a public holiday in *bundesland*."""
    md = (d.month, d.day)

    # Fixed common holidays
    if md in _FIXED_ALL:
        return True

    # Bundesland-specific fixed holidays
    state_fixed = _FIXED_BY_STATE.get(bundesland, [])
    if md in state_fixed:
        return True

    # Movable holidays
    movables = _movable_holidays(d.year)
    if md in movables:
        return True

    # Fronleichnam (state-dependent)
    if bundesland in _FRONLEICHNAM_STATES:
        f = _fronleichnam(d.year)
        if (f.month, f.day) == md:
            return True

    # Mariä Himmelfahrt (state-dependent)
    return bundesland in _MARIA_HIMMELFAHRT_STATES and md == (8, 15)


def is_workday(d: date, bundesland: str) -> bool:
    """Check whether *d* is a workday (not Sat, Sun, or holiday)."""
    if d.weekday() >= 5:  # Saturday=5, Sunday=6
        return False
    return not is_holiday(d, bundesland)


def next_workday(d: date, bundesland: str) -> date:
    """Return the next workday on or after *d* in *bundesland*."""
    candidate = d
    while not is_workday(candidate, bundesland):
        candidate += timedelta(days=1)
    return candidate


def non_workday_name(d: date) -> str:
    """Return the German name of why *d* is not a workday (or a weekday name)."""
    if d.weekday() in _NON_WORKDAY_NAMES:
        return _NON_WORKDAY_NAMES[d.weekday()]
    if d.weekday() < 5:
        return "Feiertag"
    return "Unbekannt"


def weekday_name(d: date) -> str:
    """Return German weekday name for *d*."""
    return _WEEKDAY_NAMES.get(d.weekday(), "Unbekannt")


# ---------------------------------------------------------------------------
# Date arithmetic helpers (§ 188 BGB family)
# ---------------------------------------------------------------------------


def same_day_next_month(d: date) -> date:
    """Return the date in the next month with the same day number.

    Per § 188 Abs. 2 BGB: the period ends with the day of the following
    month that bears the same number.  If the following month lacks that
    day, use the last day of the month (e.g. 31.01 → 28.02 or 29.02).

    Examples
    --------
    >>> same_day_next_month(date(2025, 3, 15))
    datetime.date(2025, 4, 15)
    >>> same_day_next_month(date(2025, 1, 31))
    datetime.date(2025, 2, 28)
    >>> same_day_next_month(date(2024, 1, 31))
    datetime.date(2024, 2, 29)
    """
    return add_months(d, 1)


def same_day_next_year(d: date) -> date:
    """Return the date one year later with the same month and day.

    Handles leap-year edge cases (Feb 29 → Feb 28 in non-leap years).
    """
    return add_years(d, 1)


def add_months(d: date, months: int) -> date:
    """Same day number *months* later, clamped to the target month's end."""
    total = (d.month - 1) + months
    target_year = d.year + total // 12
    target_month = total % 12 + 1
    last_day = calendar.monthrange(target_year, target_month)[1]
    return date(target_year, target_month, min(d.day, last_day))


def add_years(d: date, years: int) -> date:
    """Same month and day *years* later, clamped for leap-year edges."""
    target_year = d.year + years
    last_day = calendar.monthrange(target_year, d.month)[1]
    return date(target_year, d.month, min(d.day, last_day))
