"""Workday rollover library (WP-92; ARCHITECTURE.md § 3.5).

Each entry maps a candidate deadline date to the legally effective date
when the deadline falls on a non-workday. Ids are the ones named in module
spec files (``rollover: …``). As with the fiction library, unimplemented
ids raise ``NotImplementedError`` — never silently guess an offset.

Implemented family (identical mechanics — roll to the next workday):
``sgg_64_3`` (§ 64 Abs. 3 SGG), the reference case. Other procedure codes
(``zpo_222``, ``vwgo_57``, ``stpo_43``, ``ao_108``) are deliberately NOT
pre-registered: their exact semantics (e.g. § 108 Abs. 2 AO treats
Saturdays as Werkstage) must land together with the module that needs
them, with golden date tests.
"""

# Semantic Version: 0.1.0

from __future__ import annotations

from collections.abc import Callable
from datetime import date

from app.fristen.calendar import next_workday, non_workday_name, weekday_name

#: Callable signature shared by every rollover entry.
Roller = Callable[[date, str], date]

#: Human-readable legal basis per rollover id, used in explanations.
ROLLER_LABELS: dict[str, str] = {
    "sgg_64_3": "§ 64 Abs. 3 SGG",
    "zpo_222": "§ 222 Abs. 2 ZPO",
    "bgb_193": "§ 193 BGB",
}

_ROLLERS: dict[str, Roller] = {
    "sgg_64_3": next_workday,
    "zpo_222": next_workday,
}


def get_rollover(rollover_id: str) -> Roller:
    """Return the rollover callable ``(candidate, bundesland) -> date``.

    Raises ``NotImplementedError`` for ids declared in a spec but not yet
    implemented in the core library.
    """
    roller = _ROLLERS.get(rollover_id)
    if roller is None:
        raise NotImplementedError(
            f"Rollover {rollover_id!r} is declared but not implemented in the "
            f"Fristen core library (implemented: {sorted(_ROLLERS)}); implement "
            "it together with the module that needs it, with golden date tests."
        )
    return roller


def rollover_explanation(rollover_id: str, raw_ende: date, effective: date) -> str:
    """Explanation text for a rollover that was applied."""
    return (
        f"{raw_ende.strftime('%d.%m.%Y')} ist ein {non_workday_name(raw_ende)}"
        f" → Verschiebung auf {effective.strftime('%d.%m.%Y')} "
        f"({weekday_name(effective)}, {ROLLER_LABELS.get(rollover_id, rollover_id)})"
    )
