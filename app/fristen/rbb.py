"""Rechtsbehelfsbelehrung-defect extension (WP-92; ARCHITECTURE.md § 3.5).

The generic rule: when a decision letter omits or misstates the
Rechtsbehelfsbelehrung, the (longer) substitute deadline defined in the
module's spec (``missing_rechtsbehelfsbelehrung:``) applies instead of the
regular duration. The status vocabulary is administrative-law generic:

- ``korrekt`` — proper Rechtsbehelfsbelehrung → regular duration
- ``fehlerhaft`` — wrong period stated → substitute duration
- ``fehlt`` — no Rechtsbehelfsbelehrung at all → substitute duration
"""

# Semantic Version: 0.1.0

from __future__ import annotations

from typing import Literal

RbbStatus = Literal["korrekt", "fehlerhaft", "fehlt"]

_ALLOWED: tuple[str, ...] = ("korrekt", "fehlerhaft", "fehlt")

# Rationale text per status; ``{basis}`` comes from the module spec.
_EXPLANATIONS: dict[str, str] = {
    "korrekt": ("Die Rechtsbehelfsbelehrung ist ordnungsgemäß → Monatsfrist gem. {basis}"),
    "fehlerhaft": (
        "Die Rechtsbehelfsbelehrung ist fehlerhaft (falsche Fristangabe) "
        "→ Jahresfrist gem. {basis}"
    ),
    "fehlt": "Die Rechtsbehelfsbelehrung fehlt vollständig → Jahresfrist gem. {basis}",
}


def validate_rbb_status(rbb_status: str) -> None:
    """Raise ``ValueError`` for an unknown status (mirrors the pre-split engine)."""
    if rbb_status not in _ALLOWED:
        raise ValueError(f"Unbekannter rbb_status: {rbb_status!r}")


def is_defective(rbb_status: str) -> bool:
    """True when the RBB defect triggers the substitute (longer) duration."""
    return rbb_status in ("fehlerhaft", "fehlt")


def explanation(rbb_status: str, basis: str) -> str:
    """Rationale sentence for the chosen duration, citing the spec's basis."""
    template = _EXPLANATIONS.get(rbb_status)
    if template is None:
        raise ValueError(f"Unbekannter rbb_status: {rbb_status!r}")
    return template.format(basis=basis)
