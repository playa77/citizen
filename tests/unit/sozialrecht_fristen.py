"""Sozialrecht Widerspruchsfrist through the Fristen core (WP-93 test helper).

Replaces the removed ``app.services.fristen`` compatibility shim (D-046) for
the module's golden date tests: the same call signature, evaluated as the
``widerspruch_sgg_84`` spec of ``modules/sozialrecht/fristen.yaml`` via
``app.modules.runtime.compute_deadline``.
"""

from __future__ import annotations

from datetime import date

from app.fristen.evaluator import FristInput
from app.fristen.results import FristResult
from app.modules.runtime import compute_deadline

__all__ = ["FristResult", "compute_widerspruchsfrist"]


def compute_widerspruchsfrist(
    bescheid_datum: date,
    aufgabe_zur_post: date | None = None,
    bekanntgabe_tatsaechlich: date | None = None,
    rbb_status: str = "korrekt",
    ist_verwaltungsakt: bool = True,
    bundesland: str = "NW",
) -> FristResult:
    return compute_deadline(
        "sozialrecht",
        "widerspruch_sgg_84",
        FristInput(
            bescheid_datum=bescheid_datum,
            aufgabe_zur_post=aufgabe_zur_post,
            bekanntgabe_tatsaechlich=bekanntgabe_tatsaechlich,
            rbb_status=rbb_status,
            ist_verwaltungsakt=ist_verwaltungsakt,
            bundesland=bundesland,
        ),
    )
