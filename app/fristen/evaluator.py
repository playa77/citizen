"""Generic deadline-spec evaluator (WP-92; ARCHITECTURE.md § 3.5).

Evaluates one ``DeadlineSpec`` against case inputs and produces the
``FristResult`` contract. The evaluation flow is the one the pre-split
SGG/SGB X engine used, generalised:

1. non-applicability hook (spec ``not_applicable``; non-VA detection is the
   caller's job — the core only reports the declared outcome),
2. Bekanntgabe via the spec's fiction library entry (with OQ-1 ambiguity),
3. duration selection: spec duration, or the spec's substitute duration
   when the Rechtsbehelfsbelehrung is defective,
4. month/year-end arithmetic (§ 188 BGB family, core calendar),
5. rollover via the spec's rollover library entry.

Explanation text is composed so that the legal bases quoted come from the
spec/module data; only BGB-generic phrases are core text.
"""

# Semantic Version: 0.1.0

from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date, timedelta

from app.fristen.calendar import (
    add_months,
    add_years,
    is_workday,
)
from app.fristen.fictions import get_fiction
from app.fristen.rbb import explanation as rbb_explanation
from app.fristen.rbb import is_defective, validate_rbb_status
from app.fristen.results import FristResult
from app.fristen.rollover import get_rollover, rollover_explanation
from app.fristen.specs import DeadlineSpec, Duration


@dataclass(frozen=True)
class FristInput:
    """Case inputs for one deadline evaluation.

    ``ist_verwaltungsakt`` is the non-Verwaltungsakt detection hook output
    (detection itself stays with the pipeline/module, § 3.5).
    """

    bescheid_datum: date
    aufgabe_zur_post: date | None = None
    bekanntgabe_tatsaechlich: date | None = None
    rbb_status: str = "korrekt"
    ist_verwaltungsakt: bool = True
    bundesland: str = "NW"
    # D-071: service-based rules require explicit facts; never use a letter-date fiction.
    zustellung_tatsaechlich: date | None = None
    document_type: str | None = None
    zustellungsart: str | None = None
    zugang_tatsaechlich: date | None = None
    ereignis_datum: date | None = None
    qualifikationen: dict[str, bool] = field(default_factory=dict)
    feiertage_zusaetzlich: tuple[date, ...] = ()
    feiertagskalender_bestaetigt: bool = False


def _unit_phrase(duration: Duration) -> str:
    """German phrase for 'X nach Bekanntgabe' in explanations."""
    if duration.years:
        return "ein Jahr" if duration.years == 1 else f"{duration.years} Jahre"
    if duration.months:
        return "einen Monat" if duration.months == 1 else f"{duration.months} Monate"
    return f"{duration.days} Tage"


def _frist_typ(duration: Duration) -> str:
    if duration.years:
        return "jahr"
    if duration.months:
        return "monat"
    return "tag"


def _add_duration(d: date, duration: Duration) -> date:
    """Apply a Duration to a date: days, then months, then years."""
    result = d + timedelta(days=duration.days)
    if duration.months:
        result = add_months(result, duration.months)
    if duration.years:
        result = add_years(result, duration.years)
    return result


def _bekanntgabe(
    spec: DeadlineSpec, frist_input: FristInput
) -> tuple[date, str, bool, date | None]:
    """Derive Bekanntgabe; returns (date, explanation, oq1_flag, citizen_reading)."""
    if frist_input.bekanntgabe_tatsaechlich is not None:
        return (
            frist_input.bekanntgabe_tatsaechlich,
            f"tatsächliche Bekanntgabe am "
            f"{frist_input.bekanntgabe_tatsaechlich.strftime('%d.%m.%Y')}",
            False,
            None,
        )

    if spec.bekanntgabe_fiction is None:
        # No fiction declared: the trigger date itself is the Bekanntgabe.
        return (
            frist_input.bescheid_datum,
            "Bekanntgabe dem Grunde nach am Bescheidtag (keine Fiktion in der Spezifikation)",
            False,
            None,
        )

    effective_post = (
        frist_input.aufgabe_zur_post
        if frist_input.aufgabe_zur_post is not None
        else frist_input.bescheid_datum
    )
    fiction = get_fiction(spec.bekanntgabe_fiction)
    result = fiction(effective_post, frist_input.bundesland)
    return (
        result.bekanntgabe,
        result.explanation,
        result.ambiguous,
        result.citizen_reading,
    )


def evaluate_spec(
    spec: DeadlineSpec, frist_input: FristInput, module_id: str | None = None
) -> FristResult:
    """Evaluate *spec* for *frist_input* and return the deadline result."""
    if any(frist_input.qualifikationen.get(key) is not True for key in spec.requires_confirmed):
        raise ValueError("Rule requires explicitly confirmed qualifications")
    if spec.trigger in ("zugang", "ereignis"):
        return _evaluate_explicit_event(spec, frist_input, module_id)
    if spec.trigger == "zustellung":
        return _evaluate_service(spec, frist_input, module_id)
    validate_rbb_status(frist_input.rbb_status)

    # ── Step 1: non-applicability hook ─────────────────────────────────
    if not frist_input.ist_verwaltungsakt:
        if spec.not_applicable is None:
            raise ValueError(
                f"spec {spec.id!r} defines no not_applicable outcome; the caller "
                "must not evaluate it for a non-applicable document"
            )
        return FristResult(
            bekanntgabe=frist_input.bescheid_datum,
            frist_ende=frist_input.bescheid_datum,
            frist_typ=spec.not_applicable.frist_typ,
            rollover_applied=False,
            oq1_flag=False,
            oq1_alternate_ende=None,
            explanation_de=(
                f"Das Schreiben vom "
                f"{frist_input.bescheid_datum.strftime('%d.%m.%Y')} ist "
                f"{spec.not_applicable.explanation_de}"
            ),
            module_id=module_id,
            spec_id=spec.id,
        )

    # ── Step 2: Bekanntgabe ────────────────────────────────────────────
    bekanntgabe, bekanntgabe_expl, oq1_flag, citizen_reading = _bekanntgabe(spec, frist_input)

    # ── Step 3: duration selection (regular vs. defective-RBB substitute) ──
    if is_defective(frist_input.rbb_status):
        if spec.missing_rechtsbehelfsbelehrung is None:
            raise ValueError(
                f"spec {spec.id!r} declares no substitute duration for a "
                "defective Rechtsbehelfsbelehrung"
            )
        duration = spec.missing_rechtsbehelfsbelehrung.duration
        basis = spec.missing_rechtsbehelfsbelehrung.basis
    else:
        duration = spec.duration
        if spec.basis is None:
            raise ValueError(f"spec {spec.id!r} declares no basis for the regular duration")
        basis = spec.basis

    # ── Step 4: raw deadline (§ 188 BGB family) ────────────────────────
    raw_ende = _add_duration(bekanntgabe, duration)

    # ── Step 5: rollover ───────────────────────────────────────────────
    rollover_applied = False
    rollover_expl = ""
    if spec.rollover is not None:
        roller = get_rollover(spec.rollover)
        if not is_workday(raw_ende, frist_input.bundesland):
            raw_ende_workday = roller(raw_ende, frist_input.bundesland)
            frist_ende = raw_ende_workday
            rollover_applied = True
            rollover_expl = rollover_explanation(spec.rollover, raw_ende, frist_ende)
        else:
            frist_ende = raw_ende
    else:
        frist_ende = raw_ende

    # ── Step 6: explanation composition ────────────────────────────────
    rbb_expl = rbb_explanation(frist_input.rbb_status, basis)
    frist_end_expl = (
        f"Fristende rechnerisch: {raw_ende.strftime('%d.%m.%Y')} "
        f"({_unit_phrase(duration)} nach Bekanntgabe, {basis}, § 188 Abs. 2 BGB)"
    )

    fristbeginn = bekanntgabe + timedelta(days=1)
    parts = [
        f"Bescheid vom {frist_input.bescheid_datum.strftime('%d.%m.%Y')}. " f"{bekanntgabe_expl}.",
        rbb_expl + ".",
        f"Fristbeginn: {fristbeginn.strftime('%d.%m.%Y')} ({spec.fristbeginn_basis}).",
    ]
    parts.append(frist_end_expl + ".")
    if rollover_expl:
        parts.append(rollover_expl + ".")

    oq1_alternate_ende: date | None = None
    if oq1_flag and citizen_reading is not None:
        oq1_alternate_ende = _add_duration(citizen_reading, duration)
        parts.append(
            f"Alternativberechnung (OQ-1, bürgerfreundlich): "
            f"Bekanntgabe am {citizen_reading.strftime('%d.%m.%Y')}, "
            f"Fristende am {oq1_alternate_ende.strftime('%d.%m.%Y')}."
        )

    explanation_de = " ".join(parts)

    return FristResult(
        bekanntgabe=bekanntgabe,
        frist_ende=frist_ende,
        frist_typ=_frist_typ(duration),
        rollover_applied=rollover_applied,
        oq1_flag=oq1_flag,
        oq1_alternate_ende=oq1_alternate_ende,
        explanation_de=explanation_de,
        module_id=module_id,
        spec_id=spec.id,
    )


def _evaluate_service(spec: DeadlineSpec, facts: FristInput, module_id: str | None) -> FristResult:
    """Evaluate confirmed service; missing/unsupported facts are handled by dossier status."""
    if facts.zustellung_tatsaechlich is None:
        raise ValueError("Service date must be explicitly confirmed")
    for key, expected in spec.applies_when.items():
        if getattr(facts, key, None) != expected:
            raise ValueError(f"Service rule requires {key}={expected!r}")
    if not spec.basis:
        raise ValueError(f"spec {spec.id!r} declares no basis")
    served = facts.zustellung_tatsaechlich
    raw_end = _add_duration(served, spec.duration)
    if spec.rollover == "bgb_193":
        from app.fristen.civil_calendar import civil_next_workday

        if not facts.feiertagskalender_bestaetigt:
            raise ValueError("Civil holiday calendar requires explicit confirmation")
        end = civil_next_workday(raw_end, facts.bundesland, facts.feiertage_zusaetzlich)
    else:
        end = get_rollover(spec.rollover)(raw_end, facts.bundesland) if spec.rollover else raw_end
    explanation = (
        f"Bestätigte Zustellung am {served.strftime('%d.%m.%Y')}. "
        f"Fristbeginn: {(served + timedelta(days=1)).strftime('%d.%m.%Y')} "
        f"({spec.fristbeginn_basis}). Fristende rechnerisch: {raw_end.strftime('%d.%m.%Y')} "
        f"({_unit_phrase(spec.duration)} nach Zustellung, {spec.basis})."
    )
    if end != raw_end and spec.rollover:
        explanation += " " + rollover_explanation(spec.rollover, raw_end, end) + "."
    return FristResult(
        bekanntgabe=served,
        frist_ende=end,
        frist_typ=_frist_typ(spec.duration),
        rollover_applied=end != raw_end,
        oq1_flag=False,
        oq1_alternate_ende=None,
        explanation_de=explanation,
        module_id=module_id,
        spec_id=spec.id,
    )


def _evaluate_explicit_event(
    spec: DeadlineSpec, facts: FristInput, module_id: str | None
) -> FristResult:
    """Receipt/event paths never inherit administrative dates or assumptions."""
    start = facts.zugang_tatsaechlich if spec.trigger == "zugang" else facts.ereignis_datum
    if start is None:
        raise ValueError("Receipt/event date must be explicitly confirmed")
    if any(getattr(facts, key, None) != value for key, value in spec.applies_when.items()):
        raise ValueError("Rule applicability must be confirmed")
    if not spec.basis:
        raise ValueError("Receipt/event rule requires a legal basis")
    raw_end = _add_duration(start, spec.duration)
    if spec.anchor == "month_end":
        raw_end = raw_end.replace(day=calendar.monthrange(raw_end.year, raw_end.month)[1])
    end = raw_end
    if spec.rollover == "bgb_193":
        from app.fristen.civil_calendar import civil_next_workday

        if not facts.feiertagskalender_bestaetigt:
            raise ValueError("Civil holiday calendar requires explicit confirmation")
        end = civil_next_workday(raw_end, facts.bundesland, facts.feiertage_zusaetzlich)
    elif spec.rollover:
        end = get_rollover(spec.rollover)(raw_end, facts.bundesland)
    label = "Zugang" if spec.trigger == "zugang" else "Bezugsdatum"
    anchor = "Kalendermonatsende" if spec.anchor == "month_end" else "taggenaue Berechnung"
    explanation = (
        f"Bestätigter {label}: {start.strftime('%d.%m.%Y')}. "
        f"Rechnerisches Ende: {raw_end.strftime('%d.%m.%Y')} ({anchor}; {spec.basis})."
    )
    if end != raw_end and spec.rollover:
        explanation += " " + rollover_explanation(spec.rollover, raw_end, end) + "."
    return FristResult(
        bekanntgabe=start,
        frist_ende=end,
        frist_typ=_frist_typ(spec.duration),
        rollover_applied=end != raw_end,
        oq1_flag=False,
        oq1_alternate_ende=None,
        explanation_de=explanation,
        module_id=module_id,
        spec_id=spec.id,
    )
