"""Bekanntgabe/Zustellung fiction library (WP-92; ARCHITECTURE.md § 3.5).

Each fiction maps the dispatch date ("Aufgabe zur Post" or equivalent) to
the date of legal receipt. Ids are the ones named in module spec files
(``bekanntgabe_fiction: …``). A fiction that no shipped module needs is
**not** pre-implemented — unknown ids raise ``NotImplementedError`` so a
half-remembered day offset can never silently produce a wrong deadline.

``sgbx_37_2`` carries the OQ-1 ambiguity flag: when the fiction lands on a
weekend or holiday the conservative (authority-favorable) date is used as
Bekanntgabe and the citizen-favorable reading is reported alongside.
"""

# Semantic Version: 0.3.0 | 2026-11-28 — AO domestic four-day fiction.
# 0.2.0 | 2026-11-16 — sgbx_37_2 is intertemporal: three days
# for dispatch before 2025-01-01, four days from then on (PostModG, D-065);
# found by the dossier goldset (WP-104).
# 0.1.0

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Protocol

from app.fristen.calendar import is_workday, next_workday, non_workday_name


@dataclass(frozen=True)
class FictionResult:
    """Outcome of applying a Bekanntgabe fiction to a dispatch date."""

    bekanntgabe: date
    explanation: str
    ambiguous: bool  # OQ-1-style: fiction lands on a non-workday
    citizen_reading: date | None  # citizen-favorable alternative date


class FictionFn(Protocol):
    """Signature every Bekanntgabe fiction implements."""

    def __call__(self, effective_post: date, bundesland: str) -> FictionResult: ...


#: § 37 Abs. 2 S. 1 SGB X: "drei" → "vier" Tage by Art. 33 PostModG for
#: dispatch from this date on; earlier dispatch keeps the three-day fiction.
SGBX_37_2_FOUR_DAYS_FROM = date(2025, 1, 1)


def _sgbx_37_2(effective_post: date, bundesland: str) -> FictionResult:
    """§ 37 Abs. 2 S. 1 SGB X: VA gilt am 4. Tag nach Aufgabe zur Post als
    bekanntgegeben (geändert von "drei" auf "vier" durch Art. 33 PostModG
    zum 01.01.2025); bei Aufgabe zur Post vor dem 01.01.2025 am 3. Tag."""
    days = 4 if effective_post >= SGBX_37_2_FOUR_DAYS_FROM else 3
    basis = "§ 37 Abs. 2 SGB X" if days == 4 else "§ 37 Abs. 2 SGB X a.F. (bis 31.12.2024)"
    bekanntgabe = effective_post + timedelta(days=days)

    if not is_workday(bekanntgabe, bundesland):
        citizen_reading = next_workday(bekanntgabe, bundesland)
        explanation = (
            f"Bekanntgabe am {bekanntgabe.strftime('%d.%m.%Y')} "
            f"(Aufgabe zur Post {effective_post.strftime('%d.%m.%Y')} + {days} "
            f"Tage gem. {basis}). "
            f"HINWEIS: {bekanntgabe.strftime('%d.%m.%Y')} ist ein "
            f"{non_workday_name(bekanntgabe)} "
            f"— die Bekanntgabefiktion ist an dieser Stelle umstritten "
            f"(OQ-1). Die konservative Lesung (Behörden-favorabel) wird "
            f"als Bekanntgabe angesetzt; die bürgerfreundliche Lesung "
            f"geht vom {citizen_reading.strftime('%d.%m.%Y')} aus."
        )
        return FictionResult(
            bekanntgabe=bekanntgabe,
            explanation=explanation,
            ambiguous=True,
            citizen_reading=citizen_reading,
        )

    explanation = (
        f"Bekanntgabe am {bekanntgabe.strftime('%d.%m.%Y')} "
        f"(Aufgabe zur Post {effective_post.strftime('%d.%m.%Y')} + {days} "
        f"Tage gem. {basis})"
    )
    return FictionResult(
        bekanntgabe=bekanntgabe,
        explanation=explanation,
        ambiguous=False,
        citizen_reading=None,
    )


def _ao_122_2_inland(effective_post: date, bundesland: str) -> FictionResult:
    """Current domestic postal presumption; callers confirm regime and receipt."""
    from app.fristen.civil_calendar import civil_next_workday

    if effective_post < date(2025, 1, 1):
        raise ValueError("Historical AO notification regime is unsupported")
    presumed = civil_next_workday(effective_post + timedelta(days=4), bundesland)
    return FictionResult(
        bekanntgabe=presumed,
        explanation=(
            f"Bekanntgabe am {presumed.strftime('%d.%m.%Y')} "
            f"(bestätigte Aufgabe zur Post {effective_post.strftime('%d.%m.%Y')} + vier Tage; "
            "§ 122 Abs. 2 Nr. 1 AO, Verschiebung nach § 108 Abs. 3 AO)"
        ),
        ambiguous=False,
        citizen_reading=None,
    )


_FICTIONS: dict[str, FictionFn] = {
    "ao_122_2_inland": _ao_122_2_inland,
    "sgbx_37_2": _sgbx_37_2,
}


def get_fiction(fiction_id: str) -> FictionFn:
    """Return the fiction callable ``(effective_post, bundesland) -> FictionResult``.

    Raises ``NotImplementedError`` for library ids a module may declare but
    that no shipped implementation covers yet.
    """
    fiction = _FICTIONS.get(fiction_id)
    if fiction is None:
        raise NotImplementedError(
            f"Bekanntgabe fiction {fiction_id!r} is declared but not implemented "
            "in the Fristen core library (implemented: "
            f"{sorted(_FICTIONS)}); implement it together with the module "
            "that needs it, with golden date tests."
        )
    return fiction
