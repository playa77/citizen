"""Deterministic German Widerspruchsfrist calculator.

Pure functions computing Widerspruchsfrist deadlines under §§ 64, 66 Abs. 2,
84 Abs. 1 SGG, § 37 Abs. 2 SGB X.  No I/O, no LLM calls — all computation
is locally verifiable.

Architecture:
    The LLM *extracts* Bescheid metadata (date, posting date, RBB status, etc.)
    from a document.  This module *computes* the correct Frist deadline.  The
    result can be compared against a pipeline's claim for verification.

Rules implemented:
    - Non-VA check (§ 31 SGB X)
    - Bekanntgabe fiction (§ 37 Abs. 2 SGB X, post-2025 reform: +4 days)
    - Jahresfrist for missing/wrong RBB (§ 66 Abs. 2 SGG)
    - 1-month Widerspruchsfrist (§ 84 Abs. 1 SGG + § 188 Abs. 2 BGB)
    - Workday rollover (§ 64 Abs. 3 SGG)
    - OQ-1 flag (ambiguous 4-day fiction on weekends/holidays)
    - Bundesland-specific holiday table with movable holidays (2024-2027)
"""

# Semantic Version: 0.1.0

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

# ---------------------------------------------------------------------------
# Public data types
# ---------------------------------------------------------------------------


@dataclass
class FristResult:
    """Result of a Widerspruchsfrist computation.

    Attributes
    ----------
    bekanntgabe :
        Date of legal receipt (Bekanntgabe).
    frist_ende :
        Deadline date.
    frist_typ :
        ``"monat"`` | ``"jahr"`` | ``"kein_va"``.
    rollover_applied :
        Whether the deadline rolled to the next workday.
    oq1_flag :
        Whether the 4-day fiction is ambiguous (Bekanntgabe on weekend/holiday).
    oq1_alternate_ende :
        Alternate date under citizen-favorable reading (OQ-1), if applicable.
    explanation_de :
        Human-readable German explanation of the derivation.
    """

    bekanntgabe: date
    frist_ende: date
    frist_typ: str
    rollover_applied: bool
    oq1_flag: bool
    oq1_alternate_ende: date | None
    explanation_de: str


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


def _fronleichnam(year: int) -> date | None:
    """Return Fronleichnam date for *year* (60 days after Easter), or ``None``."""
    clamped = max(min(year, max(_EASTER.keys())), min(_EASTER.keys()))
    em, ed = _EASTER[clamped]
    easter = date(clamped, em, ed)
    return easter + timedelta(days=60)


def _date_to_tuple(d: date) -> tuple[int, int]:
    """Convert a date to (month, day) tuple for holiday lookup."""
    return (d.month, d.day)


# ---------------------------------------------------------------------------
# Holiday helpers
# ---------------------------------------------------------------------------


def _is_holiday(d: date, bundesland: str) -> bool:
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
        if f is not None and (f.month, f.day) == md:
            return True

    # Mariä Himmelfahrt (state-dependent)
    return bundesland in _MARIA_HIMMELFAHRT_STATES and md == (8, 15)


def _is_workday(d: date, bundesland: str) -> bool:
    """Check whether *d* is a workday (not Sat, Sun, or holiday)."""
    if d.weekday() >= 5:  # Saturday=5, Sunday=6
        return False
    return not _is_holiday(d, bundesland)


def _next_workday(d: date, bundesland: str) -> date:
    """Return the next workday on or after *d* in *bundesland*."""
    candidate = d
    while not _is_workday(candidate, bundesland):
        candidate += timedelta(days=1)
    return candidate


# ---------------------------------------------------------------------------
# Date arithmetic helpers
# ---------------------------------------------------------------------------


def _same_day_next_month(d: date) -> date:
    """Return the date in the next month with the same day number.

    Per § 188 Abs. 2 BGB: the period ends with the day of the following
    month that bears the same number.  If the following month lacks that
    day, use the last day of the month (e.g. 31.01 → 28.02 or 29.02).

    Examples
    --------
    >>> _same_day_next_month(date(2025, 3, 15))
    2025-04-15
    >>> _same_day_next_month(date(2025, 1, 31))
    2025-02-28
    >>> _same_day_next_month(date(2024, 1, 31))
    2024-02-29
    """
    target_month = d.month + 1
    target_year = d.year
    if target_month > 12:
        target_month = 1
        target_year += 1

    # Clamp to last day of target month if needed.
    import calendar

    last_day = calendar.monthrange(target_year, target_month)[1]
    target_day = min(d.day, last_day)

    return date(target_year, target_month, target_day)


def _same_day_next_year(d: date) -> date:
    """Return the date one year later with the same month and day.

    Handles leap-year edge cases (Feb 29 → Feb 28 in non-leap years).
    """
    target_year = d.year + 1
    import calendar

    last_day = calendar.monthrange(target_year, d.month)[1]
    target_day = min(d.day, last_day)
    return date(target_year, d.month, target_day)


# ---------------------------------------------------------------------------
# Main computation
# ---------------------------------------------------------------------------


def compute_widerspruchsfrist(
    bescheid_datum: date,
    aufgabe_zur_post: date | None = None,
    bekanntgabe_tatsaechlich: date | None = None,
    rbb_status: Literal["korrekt", "fehlerhaft", "fehlt"] = "korrekt",
    ist_verwaltungsakt: bool = True,
    bundesland: str = "NW",
) -> FristResult:
    """Compute the Widerspruchsfrist for a German Verwaltungsakt.

    Parameters
    ----------
    bescheid_datum :
        The date printed on the Bescheid.
    aufgabe_zur_post :
        The date the Bescheid was mailed (``None`` = unknown, falls back to
        ``bescheid_datum``).
    bekanntgabe_tatsaechlich :
        Actual receipt date if known (overrides the 4-day fiction).
    rbb_status :
        Quality of the Rechtsbehelfsbelehrung:
        ``"korrekt"`` — proper RBB → 1 month.
        ``"fehlerhaft"`` — wrong period stated → 1 year (§ 66 Abs. 2 SGG).
        ``"fehlt"`` — no RBB at all → 1 year (§ 66 Abs. 2 SGG).
    ist_verwaltungsakt :
        Whether the document is a Verwaltungsakt (``False`` → no deadline).
    bundesland :
        Bundesland ISO code (e.g. ``"NW"``, ``"BY"``, ``"BW"``) for holiday
        lookup.

    Returns
    -------
    FristResult
        The computed deadline with metadata.

    Raises
    ------
    ValueError
        If ``rbb_status`` is not one of the allowed values.
    """
    if rbb_status not in ("korrekt", "fehlerhaft", "fehlt"):
        raise ValueError(f"Unbekannter rbb_status: {rbb_status!r}")

    # ── Step 1: Non-VA check ──────────────────────────────────────────
    if not ist_verwaltungsakt:
        return FristResult(
            bekanntgabe=bescheid_datum,
            frist_ende=bescheid_datum,
            frist_typ="kein_va",
            rollover_applied=False,
            oq1_flag=False,
            oq1_alternate_ende=None,
            explanation_de=(
                f"Das Schreiben vom {bescheid_datum.strftime('%d.%m.%Y')} ist "
                f"kein Verwaltungsakt (keine Regelungswirkung gem. § 31 SGB X). "
                f"Eine Widerspruchsfrist besteht nicht."
            ),
        )

    # ── Step 2: Bekanntgabe ───────────────────────────────────────────
    if bekanntgabe_tatsaechlich is not None:
        bekanntgabe = bekanntgabe_tatsaechlich
        bekanntgabe_expl = (
            f"tatsächliche Bekanntgabe am " f"{bekanntgabe_tatsaechlich.strftime('%d.%m.%Y')}"
        )
        oq1_flag = False
        oq1_alternate_ende = None
    else:
        effective_post = aufgabe_zur_post if aufgabe_zur_post is not None else bescheid_datum
        # § 37 Abs. 2 S. 1 SGB X: VA gilt am 4. Tag nach Aufgabe zur Post als
        # bekanntgegeben (geändert von "drei" auf "vier" durch Art. 33 PostModG
        # zum 01.01.2025).
        bekanntgabe = effective_post + timedelta(days=4)

        # OQ-1: Check if bekanntgabe falls on a non-workday.
        if not _is_workday(bekanntgabe, bundesland):
            oq1_flag = True
            # Conservative reading: bekanntgabe stays (Behörden-favorable).
            # Citizen-favorable: roll to next workday.
            citizen_reading = _next_workday(bekanntgabe, bundesland)
            oq1_alternate_ende = _same_day_next_month(citizen_reading)

            _weekday = bekanntgabe.weekday()
            _day_name = "Samstag" if _weekday == 5 else "Sonntag" if _weekday == 6 else "Feiertag"
            bekanntgabe_expl = (
                f"Bekanntgabe am {bekanntgabe.strftime('%d.%m.%Y')} "
                f"(Aufgabe zur Post {effective_post.strftime('%d.%m.%Y')} + 4 "
                f"Tage gem. § 37 Abs. 2 SGB X). "
                f"HINWEIS: {bekanntgabe.strftime('%d.%m.%Y')} ist ein "
                f"{_day_name} "
                f"— die Bekanntgabefiktion ist an dieser Stelle umstritten "
                f"(OQ-1). Die konservative Lesung (Behörden-favorabel) wird "
                f"als Bekanntgabe angesetzt; die bürgerfreundliche Lesung "
                f"geht vom {citizen_reading.strftime('%d.%m.%Y')} aus."
            )
        else:
            oq1_flag = False
            oq1_alternate_ende = None
            bekanntgabe_expl = (
                f"Bekanntgabe am {bekanntgabe.strftime('%d.%m.%Y')} "
                f"(Aufgabe zur Post {effective_post.strftime('%d.%m.%Y')} + 4 "
                f"Tage gem. § 37 Abs. 2 SGB X)"
            )

    # ── Step 3: Determine Frist type and base end date ─────────────────
    if rbb_status in ("fehlerhaft", "fehlt"):
        # § 66 Abs. 2 SGG: Jahresfrist.
        frist_typ = "jahr"
        raw_ende = _same_day_next_year(bekanntgabe)

        if rbb_status == "fehlt":
            rbb_expl = (
                "Die Rechtsbehelfsbelehrung fehlt vollständig → " "Jahresfrist gem. § 66 Abs. 2 SGG"
            )
        else:
            rbb_expl = (
                "Die Rechtsbehelfsbelehrung ist fehlerhaft (falsche Fristangabe) "
                "→ Jahresfrist gem. § 66 Abs. 2 SGG"
            )

        frist_end_expl = (
            f"Fristende rechnerisch: {_same_day_next_year(bekanntgabe).strftime('%d.%m.%Y')} "
            f"(ein Jahr nach Bekanntgabe, § 66 Abs. 2 SGG, § 188 Abs. 2 BGB)"
        )
    else:
        # § 84 Abs. 1 SGG: 1 month Widerspruchsfrist.
        frist_typ = "monat"
        raw_ende = _same_day_next_month(bekanntgabe)

        rbb_expl = "Die Rechtsbehelfsbelehrung ist ordnungsgemäß → Monatsfrist gem. § 84 Abs. 1 SGG"
        frist_end_expl = (
            f"Fristende rechnerisch: {raw_ende.strftime('%d.%m.%Y')} "
            f"(einen Monat nach Bekanntgabe, § 84 Abs. 1 SGG, § 188 Abs. 2 BGB)"
        )

    # ── Step 4: Workday rollover (§ 64 Abs. 3 SGG) ────────────────────
    if not _is_workday(raw_ende, bundesland):
        frist_ende = _next_workday(raw_ende, bundesland)
        rollover_applied = True
        _weekday = raw_ende.weekday()
        _day_name = "Samstag" if _weekday == 5 else "Sonntag" if _weekday == 6 else "Feiertag"
        rollover_expl = (
            f"{raw_ende.strftime('%d.%m.%Y')} ist ein {_day_name}"
            f" → Verschiebung auf {frist_ende.strftime('%d.%m.%Y')} "
            f"({_weekday_name(frist_ende)}, § 64 Abs. 3 SGG)"
        )
    else:
        frist_ende = raw_ende
        rollover_applied = False
        rollover_expl = ""

    # ── Step 5: Build explanation ─────────────────────────────────────
    fristbeginn = bekanntgabe + timedelta(days=1)
    parts = [
        f"Bescheid vom {bescheid_datum.strftime('%d.%m.%Y')}. {bekanntgabe_expl}.",
        rbb_expl + ".",
        f"Fristbeginn: {fristbeginn.strftime('%d.%m.%Y')} (§ 64 Abs. 1 SGG, § 187 Abs. 1 BGB).",
    ]
    if frist_end_expl:
        parts.append(frist_end_expl + ".")
    if rollover_expl:
        parts.append(rollover_expl + ".")

    if oq1_flag and oq1_alternate_ende is not None:
        parts.append(
            f"Alternativberechnung (OQ-1, bürgerfreundlich): "
            f"Bekanntgabe am {_next_workday(bekanntgabe, bundesland).strftime('%d.%m.%Y')}, "
            f"Fristende am {oq1_alternate_ende.strftime('%d.%m.%Y')}."
        )

    explanation_de = " ".join(parts)

    return FristResult(
        bekanntgabe=bekanntgabe,
        frist_ende=frist_ende,
        frist_typ=frist_typ,
        rollover_applied=rollover_applied,
        oq1_flag=oq1_flag,
        oq1_alternate_ende=oq1_alternate_ende,
        explanation_de=explanation_de,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _weekday_name(d: date) -> str:
    """Return German weekday name for *d*."""
    names = {
        0: "Montag",
        1: "Dienstag",
        2: "Mittwoch",
        3: "Donnerstag",
        4: "Freitag",
        5: "Samstag",
        6: "Sonntag",
    }
    return names.get(d.weekday(), "Unbekannt")
