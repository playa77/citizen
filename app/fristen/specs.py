"""Deadline spec data model and loader (WP-92; ARCHITECTURE.md § 2.3).

Module deadline specs are YAML lists (``modules/<id>/fristen.yaml``). The
core owns the *semantics* (fiction library, rollover library, calendar);
the spec declares *which* library entries and durations apply for the
module's area of law — data, not code.
"""

# Semantic Version: 0.1.0

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

#: Valid trigger keys (ARCHITECTURE.md § 2.3). ``bekanntgabe`` and
#: ``zustellung`` have evaluator paths; others raise at load time so a spec
#: that the evaluator cannot yet run never enters the registry silently.
TRIGGERS: frozenset[str] = frozenset(
    {"bekanntgabe", "zustellung", "zugang", "kenntnis", "ereignis"}
)

_EVALUABLE_TRIGGERS: frozenset[str] = frozenset(
    {"bekanntgabe", "zustellung", "zugang", "ereignis", "kenntnis"}
)

_SEVERITIES: frozenset[str] = frozenset({"low", "normal", "high", "critical"})


@dataclass(frozen=True)
class Duration:
    """A deadline length; at most one component is expected in practice."""

    days: int = 0
    months: int = 0
    years: int = 0


@dataclass(frozen=True)
class MissingRbb:
    """Substitute deadline when the Rechtsbehelfsbelehrung is defective."""

    duration: Duration
    basis: str


@dataclass(frozen=True)
class NotApplicable:
    """Declares the outcome when the document is outside the spec's scope
    (e.g. no Verwaltungsakt): the frist_typ to report and the area-specific
    explanation text (module data, composed by the core evaluator)."""

    frist_typ: str
    explanation_de: str


@dataclass(frozen=True)
class DeadlineSpec:
    """One module deadline rule (parsed ``fristen.yaml`` entry)."""

    id: str
    label_de: str
    trigger: str
    bekanntgabe_fiction: str | None
    duration: Duration
    rollover: str | None
    missing_rechtsbehelfsbelehrung: MissingRbb | None
    basis: str | None
    severity: str
    applies_when: dict[str, str]
    # Area-specific Fristbeginn citation, e.g. "§ 64 Abs. 1 SGG, § 187 Abs. 1 BGB".
    fristbeginn_basis: str
    not_applicable: NotApplicable | None
    anchor: str = "same_day"
    requires_confirmed: tuple[str, ...] = ()


def _parse_duration(raw: dict[str, Any] | None, context: str) -> Duration:
    if raw is None:
        raise ValueError(f"{context}: missing duration")
    unknown = set(raw) - {"days", "months", "years"}
    if unknown:
        raise ValueError(f"{context}: unknown duration keys {sorted(unknown)}")
    return Duration(
        days=int(raw.get("days", 0)),
        months=int(raw.get("months", 0)),
        years=int(raw.get("years", 0)),
    )


def _parse_spec(raw: dict[str, Any], path: Path) -> DeadlineSpec:
    spec_id = raw.get("id")
    if not spec_id or not isinstance(spec_id, str):
        raise ValueError(f"{path}: spec entry without string 'id'")

    trigger = raw.get("trigger")
    if trigger not in TRIGGERS:
        raise ValueError(f"{path}: spec {spec_id!r} has unknown trigger {trigger!r}")
    if trigger not in _EVALUABLE_TRIGGERS:
        raise NotImplementedError(
            f"{path}: spec {spec_id!r} uses trigger {trigger!r}, which the "
            "evaluator does not support yet (evaluable: "
            f"{sorted(_EVALUABLE_TRIGGERS)})"
        )

    if trigger == "zustellung" and raw.get("bekanntgabe_fiction") not in (None, "none"):
        raise ValueError(f"{path}: service trigger must not use a Bekanntgabe fiction")

    severity = raw.get("severity")
    if severity not in _SEVERITIES:
        raise ValueError(f"{path}: spec {spec_id!r} has unknown severity {severity!r}")

    missing_raw = raw.get("missing_rechtsbehelfsbelehrung")
    missing = (
        MissingRbb(
            duration=_parse_duration(missing_raw.get("duration"), f"{spec_id}.missing"),
            basis=str(missing_raw.get("basis", "")),
        )
        if isinstance(missing_raw, dict)
        else None
    )

    not_applicable_raw = raw.get("not_applicable")
    not_applicable = (
        NotApplicable(
            frist_typ=str(not_applicable_raw["frist_typ"]),
            explanation_de=str(not_applicable_raw["explanation_de"]),
        )
        if isinstance(not_applicable_raw, dict)
        else None
    )

    applies_when = raw.get("applies_when") or {}
    if not isinstance(applies_when, dict):
        raise ValueError(f"{path}: spec {spec_id!r} has a non-mapping applies_when")

    anchor = raw.get("anchor", "same_day")
    if anchor not in ("same_day", "month_end"):
        raise ValueError(f"{path}: invalid anchor {anchor!r}")
    duration = _parse_duration(raw.get("duration"), spec_id)
    components = (duration.days, duration.months, duration.years)
    if trigger in ("zugang", "ereignis", "kenntnis"):
        if sum(value != 0 for value in components) != 1:
            raise ValueError(f"{path}: receipt/event rules require one nonzero duration component")
        if anchor == "month_end" and (not duration.months or duration.months < 0):
            raise ValueError(f"{path}: month_end anchor requires positive months")
        if any(value < 0 for value in components) and (
            trigger != "ereignis" or raw.get("rollover") is not None
        ):
            raise ValueError(f"{path}: backward rules require event trigger and no rollover")
        if raw.get("bekanntgabe_fiction") not in (None, "none") or missing is not None:
            raise ValueError(f"{path}: receipt/event rules cannot use administrative fictions/RBB")
        # A confirmed event may be established by different document types.
        # Existing explicit qualifications can gate such a rule instead of a
        # single document label (e.g. registration following dismissal/contract).
        if not applies_when.get("document_type") and not raw.get("requires_confirmed"):
            raise ValueError(
                f"{path}: explicit-date rules require a document_type selector or qualifications"
            )
    elif anchor != "same_day":
        raise ValueError(f"{path}: anchor supported only for receipt/event rules")
    required = raw.get("requires_confirmed", [])
    if not isinstance(required, list) or any(
        not isinstance(key, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", key)
        for key in required
    ):
        raise ValueError(f"{path}: invalid requires_confirmed qualification keys")

    return DeadlineSpec(
        id=spec_id,
        label_de=str(raw.get("label_de", "")),
        trigger=str(trigger),
        bekanntgabe_fiction=raw.get("bekanntgabe_fiction"),
        duration=duration,
        rollover=raw.get("rollover"),
        missing_rechtsbehelfsbelehrung=missing,
        basis=raw.get("basis"),
        severity=str(severity),
        applies_when={str(k): str(v) for k, v in applies_when.items()},
        fristbeginn_basis=str(raw.get("fristbeginn_basis", "")),
        not_applicable=not_applicable,
        anchor=anchor,
        requires_confirmed=tuple(required),
    )


def load_specs(path: Path) -> list[DeadlineSpec]:
    """Load and validate a ``fristen.yaml`` spec file."""
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(f"unreadable deadline spec file {path}: {exc}") from exc
    if not isinstance(raw, list):
        raise ValueError(f"{path}: expected a YAML list of deadline specs")
    return [_parse_spec(entry, path) for entry in raw]


def find_spec(specs: list[DeadlineSpec], spec_id: str) -> DeadlineSpec:
    """Return the spec with *spec_id*; ``KeyError`` names the missing id."""
    for spec in specs:
        if spec.id == spec_id:
            return spec
    raise KeyError(f"unknown deadline spec id: {spec_id!r}")
