"""Deterministic German deadline computation — compatibility shim (WP-92).

The v2.0.0 engine that lived here was split (roadmap WP-92): the generic
calendar, Bekanntgabe fiction library, rollover library, Rechtsbehelfsbelehrung
extension and the ``fristen.yaml`` spec evaluator now live in ``app/fristen/``;
the SGB X/SGG rules are expressed as data in
``modules/sozialrecht/fristen.yaml``.

This module remains only for the pre-split callers
(``app/api/routes/documents.py``, ``eval/metrics.py``,
``tests/unit/test_document_generators.py``, ``tests/unit/test_fristen.py``):
``compute_widerspruchsfrist`` evaluates the sozialrecht spec through the
generic evaluator, and the moved calendar helpers are re-exported under
their historical underscore names so the unchanged test suite keeps its
import surface. The shim is transitional — WP-93 moves the callers into the
module and this file shrinks to nothing.
"""

# Semantic Version: 0.2.0

from __future__ import annotations

from datetime import date
from typing import Literal

from app.fristen.calendar import (
    is_holiday as _is_holiday,
)
from app.fristen.calendar import (
    is_workday as _is_workday,
)
from app.fristen.calendar import (
    next_workday as _next_workday,
)
from app.fristen.calendar import (
    same_day_next_month as _same_day_next_month,
)
from app.fristen.evaluator import FristInput, evaluate_spec
from app.fristen.results import FristResult
from app.fristen.specs import DeadlineSpec, find_spec, load_specs
from app.modules.registry import default_modules_root

__all__ = [
    "FristResult",
    "compute_widerspruchsfrist",
    "_is_holiday",
    "_is_workday",
    "_next_workday",
    "_same_day_next_month",
]

_specs: list[DeadlineSpec] | None = None


def _widerspruch_spec() -> DeadlineSpec:
    """Load (once) the sozialrecht Widerspruchsfrist spec.

    Reads module data (YAML), not module code — the spec path is the
    WP-92 contract; the file location moves with the module extraction
    (WP-93) behind ``default_modules_root()``.
    """
    global _specs
    if _specs is None:
        _specs = load_specs(default_modules_root() / "sozialrecht" / "fristen.yaml")
    return find_spec(_specs, "widerspruch_sgg_84")


def compute_widerspruchsfrist(
    bescheid_datum: date,
    aufgabe_zur_post: date | None = None,
    bekanntgabe_tatsaechlich: date | None = None,
    rbb_status: Literal["korrekt", "fehlerhaft", "fehlt"] = "korrekt",
    ist_verwaltungsakt: bool = True,
    bundesland: str = "NW",
) -> FristResult:
    """Compute the Widerspruchsfrist for a German Verwaltungsakt.

    Signature and semantics are identical to the pre-split engine; the
    computation now runs through the generic spec evaluator with the
    sozialrecht deadline spec (§ 37 Abs. 2 SGB X, § 84 Abs. 1 SGG,
    § 64 Abs. 3 SGG, § 66 Abs. 2 SGG).

    Raises
    ------
    ValueError
        If ``rbb_status`` is not one of the allowed values.
    """
    return evaluate_spec(
        _widerspruch_spec(),
        FristInput(
            bescheid_datum=bescheid_datum,
            aufgabe_zur_post=aufgabe_zur_post,
            bekanntgabe_tatsaechlich=bekanntgabe_tatsaechlich,
            rbb_status=rbb_status,
            ist_verwaltungsakt=ist_verwaltungsakt,
            bundesland=bundesland,
        ),
        module_id="sozialrecht",
    )
