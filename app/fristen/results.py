"""Result contract of the Fristen core.

``FristResult`` is unchanged in shape from the pre-split engine
(``app/services/fristen.py``, v2.0.0); ``module_id`` and ``spec_id`` are
additive fields (default ``None``) so every pre-existing caller keeps
working (ARCHITECTURE.md § 3.5).
"""

# Semantic Version: 0.1.0

from dataclasses import dataclass
from datetime import date


@dataclass
class FristResult:
    """Result of a deadline computation.

    Attributes
    ----------
    bekanntgabe :
        Date of legal receipt (Bekanntgabe).
    frist_ende :
        Deadline date.
    frist_typ :
        ``"monat"`` | ``"jahr"`` | ``"kein_va"`` (spec-defined).
    rollover_applied :
        Whether the deadline rolled to the next workday.
    oq1_flag :
        Whether the 4-day fiction is ambiguous (Bekanntgabe on weekend/holiday).
    oq1_alternate_ende :
        Alternate date under citizen-favorable reading (OQ-1), if applicable.
    explanation_de :
        Human-readable German explanation of the derivation.
    module_id :
        Id of the module whose spec produced this result (additive, WP-92).
    spec_id :
        Id of the deadline spec within that module (additive, WP-92).
    """

    bekanntgabe: date
    frist_ende: date
    frist_typ: str
    rollover_applied: bool
    oq1_flag: bool
    oq1_alternate_ende: date | None
    explanation_de: str
    # Additive fields (WP-92): defaults keep every v2.0.0 caller valid.
    module_id: str | None = None
    spec_id: str | None = None
