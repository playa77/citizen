"""Fristen banner of the dossier (ARCHITECTURE.md § 3.7 item 3).

Every deadline in the dossier comes from the Fristen core evaluating the case
modules' deadline specs (``fristen.yaml``) — never from LLM output (AGENTS.md
rule). The inputs are case facts:

* explicit user facts (``facts`` of the chronology confirmation step) win;
* otherwise the letter's date is taken from the chronology: a **confirmed**
  ``document_date`` entry gives a ``computed`` deadline, an unconfirmed
  proposal only a ``provisional`` one (shown, but flagged);
* no date at all → ``missing_input`` (the banner tells the person what to
  confirm instead of guessing).

Defaults are the *conservative* reading for the citizen and are listed as
``assumptions``: Rechtsbehelfsbelehrung treated as correct (the shorter
regular deadline), Aufgabe zur Post = date of the letter (earliest possible
Bekanntgabe), document treated as a Verwaltungsakt (a deadline is shown
rather than hidden), Bundesland = the Fristen core default.
"""

# Semantic Version: 1.0.0 | 2026-11-16 — WP-103 initial.

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

from app.dossier.chronology import KIND_DOCUMENT_DATE, STATUS_CONFIRMED, ChronologyEntry
from app.fristen.evaluator import FristInput, evaluate_spec
from app.fristen.results import FristResult
from app.fristen.specs import DeadlineSpec

STATUS_COMPUTED = "computed"
STATUS_PROVISIONAL = "provisional"
STATUS_NOT_APPLICABLE = "not_applicable"
STATUS_MISSING_INPUT = "missing_input"

RBB_STATUSES = ("korrekt", "fehlerhaft", "fehlt")
BUNDESLAENDER = (
    "BB", "BE", "BW", "BY", "HB", "HE", "HH", "MV",
    "NI", "NW", "RP", "SH", "SL", "SN", "ST", "TH",
)  # fmt: skip
#: The Fristen core's default Bundesland (``FristInput.bundesland``).
_DEFAULT_BUNDESLAND: str = str(FristInput.__dataclass_fields__["bundesland"].default)

FACT_KEYS = (
    "bescheid_datum",
    "aufgabe_zur_post",
    "bekanntgabe_tatsaechlich",
    "rbb_status",
    "ist_verwaltungsakt",
    "bundesland",
    "zustellung_tatsaechlich",
    "document_type",
    "zustellungsart",
)
_DATE_FACTS = (
    "bescheid_datum",
    "aufgabe_zur_post",
    "bekanntgabe_tatsaechlich",
    "zustellung_tatsaechlich",
)


def validate_facts(raw: Any) -> dict[str, Any]:
    """Validate the ``facts`` object of a chronology PUT; returns stored form."""
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError("'facts' must be an object")
    unknown = set(raw) - set(FACT_KEYS)
    if unknown:
        raise ValueError(f"unknown facts {sorted(unknown)}; allowed: {list(FACT_KEYS)}")
    facts: dict[str, Any] = {}
    if raw.get("document_type") is not None:
        value = raw["document_type"]
        if not isinstance(value, str) or not value or len(value) > 64:
            raise ValueError("facts.document_type must contain 1–64 characters")
        facts["document_type"] = value
    if raw.get("zustellungsart") is not None:
        if raw["zustellungsart"] not in ("inland", "ausland", "oeffentlich"):
            raise ValueError("facts.zustellungsart must be inland, ausland or oeffentlich")
        facts["zustellungsart"] = raw["zustellungsart"]
    for key in _DATE_FACTS:
        if raw.get(key) is not None:
            try:
                facts[key] = date.fromisoformat(str(raw[key])).isoformat()
            except ValueError as exc:
                raise ValueError(f"facts.{key}: invalid ISO date {raw[key]!r}") from exc
    if raw.get("rbb_status") is not None:
        if raw["rbb_status"] not in RBB_STATUSES:
            raise ValueError(f"facts.rbb_status must be one of {list(RBB_STATUSES)}")
        facts["rbb_status"] = raw["rbb_status"]
    if raw.get("ist_verwaltungsakt") is not None:
        if not isinstance(raw["ist_verwaltungsakt"], bool):
            raise ValueError("facts.ist_verwaltungsakt must be a boolean")
        facts["ist_verwaltungsakt"] = raw["ist_verwaltungsakt"]
    if raw.get("bundesland") is not None:
        if raw["bundesland"] not in BUNDESLAENDER:
            raise ValueError(f"facts.bundesland must be one of {list(BUNDESLAENDER)}")
        facts["bundesland"] = raw["bundesland"]
    return facts


@dataclass(frozen=True)
class ModuleSpecs:
    module_id: str
    specs: tuple[DeadlineSpec, ...]


def _letter_date(
    facts: Mapping[str, Any], chronology: Sequence[ChronologyEntry]
) -> tuple[date | None, str, str | None]:
    """(date, status, source description) of the letter the deadline runs from."""
    if facts.get("bescheid_datum"):
        return date.fromisoformat(facts["bescheid_datum"]), STATUS_COMPUTED, "facts.bescheid_datum"
    candidates = [e for e in chronology if e.kind == KIND_DOCUMENT_DATE]
    # The analysed input text is the primary document; attachments follow.
    candidates.sort(key=lambda e: 0 if (e.source or {}).get("document") == "case_input" else 1)
    for entry in candidates:
        if entry.status == STATUS_CONFIRMED:
            return entry.date, STATUS_COMPUTED, f"chronology:{entry.entry_id}"
    for entry in candidates:
        if entry.status == "proposed":
            return entry.date, STATUS_PROVISIONAL, f"chronology:{entry.entry_id}"
    return None, STATUS_MISSING_INPUT, None


def _iso(value: date | None) -> str | None:
    return value.isoformat() if value is not None else None


def _result_item(
    module_id: str,
    spec: DeadlineSpec,
    status: str,
    result: FristResult | None,
    assumptions: list[str],
    inputs: dict[str, Any],
) -> dict[str, Any]:
    return {
        "module_id": module_id,
        "spec_id": spec.id,
        "label_de": spec.label_de,
        "severity": spec.severity,
        "basis": spec.basis,
        "status": status,
        "frist_typ": result.frist_typ if result else None,
        "bekanntgabe": _iso(result.bekanntgabe) if result else None,
        "frist_ende": (
            _iso(result.frist_ende) if result and status != STATUS_NOT_APPLICABLE else None
        ),
        "rollover_applied": result.rollover_applied if result else None,
        "oq1_flag": result.oq1_flag if result else None,
        "oq1_alternate_ende": _iso(result.oq1_alternate_ende) if result else None,
        "explanation_de": result.explanation_de if result else None,
        "assumptions": assumptions,
        "inputs": inputs,
    }


def compute_deadlines(
    modules: Sequence[ModuleSpecs],
    facts: Mapping[str, Any],
    chronology: Sequence[ChronologyEntry],
) -> dict[str, Any]:
    """Evaluate every spec of every case module; returns the schema section."""
    letter_date, base_status, letter_source = _letter_date(facts, chronology)
    assumptions: list[str] = []
    if base_status == STATUS_PROVISIONAL:
        assumptions.append(
            "Datum des Schreibens automatisch erkannt, aber noch nicht bestätigt — "
            "bitte in der Chronologie bestätigen."
        )
    aufgabe = facts.get("aufgabe_zur_post")
    if aufgabe is None and facts.get("bekanntgabe_tatsaechlich") is None:
        assumptions.append(
            "Tag der Aufgabe zur Post unbekannt — angenommen: Datum des Schreibens "
            "(frühestmögliche Bekanntgabe)."
        )
    rbb = facts.get("rbb_status")
    if rbb is None:
        rbb = "korrekt"
        assumptions.append(
            "Rechtsbehelfsbelehrung als ordnungsgemäß angenommen (kürzere, regelmäßige "
            "Frist); ob sie fehlerhaft ist, im Termin klären."
        )
    ist_va = facts.get("ist_verwaltungsakt")
    if ist_va is None:
        ist_va = True
        assumptions.append(
            "Schreiben als anfechtbare Entscheidung behandelt, damit keine Frist "
            "übersehen wird — im Termin klären."
        )
    bundesland = facts.get("bundesland")
    if bundesland is None:
        bundesland = _DEFAULT_BUNDESLAND
        assumptions.append(
            f"Bundesland nicht angegeben — Feiertage für {_DEFAULT_BUNDESLAND} angenommen."
        )

    used: dict[str, Any] = {
        "bescheid_datum": _iso(letter_date),
        "bescheid_datum_source": letter_source,
        "aufgabe_zur_post": aufgabe,
        "bekanntgabe_tatsaechlich": facts.get("bekanntgabe_tatsaechlich"),
        "rbb_status": rbb,
        "ist_verwaltungsakt": ist_va,
        "bundesland": bundesland,
    }
    used.update(
        {
            key: facts[key]
            for key in ("zustellung_tatsaechlich", "document_type", "zustellungsart")
            if key in facts
        }
    )

    items: list[dict[str, Any]] = []
    for module in modules:
        for spec in module.specs:
            if spec.trigger == "zustellung":
                items.append(_service_item(module.module_id, spec, facts, bundesland))
                continue
            if letter_date is None:
                items.append(
                    _result_item(
                        module.module_id,
                        spec,
                        STATUS_MISSING_INPUT,
                        None,
                        [
                            "Kein Datum des Schreibens gefunden — bitte in der "
                            "Chronologie ergänzen oder bestätigen."
                        ],
                        used,
                    )
                )
                continue
            if not ist_va and spec.not_applicable is None:
                # The spec declares no outcome for a non-applicable document.
                items.append(
                    _result_item(
                        module.module_id, spec, STATUS_NOT_APPLICABLE, None, assumptions, used
                    )
                )
                continue
            frist_input = FristInput(
                bescheid_datum=letter_date,
                aufgabe_zur_post=(date.fromisoformat(aufgabe) if aufgabe else None),
                bekanntgabe_tatsaechlich=(
                    date.fromisoformat(facts["bekanntgabe_tatsaechlich"])
                    if facts.get("bekanntgabe_tatsaechlich")
                    else None
                ),
                rbb_status=rbb,
                ist_verwaltungsakt=ist_va,
                bundesland=bundesland,
            )
            result = evaluate_spec(spec, frist_input, module_id=module.module_id)
            status = STATUS_NOT_APPLICABLE if not ist_va else base_status
            items.append(
                _result_item(module.module_id, spec, status, result, list(assumptions), used)
            )

    open_items = [i for i in items if i["frist_ende"] is not None]
    open_items.sort(key=lambda i: i["frist_ende"])
    return {
        "facts_used": used,
        "items": items,
        "earliest_frist_ende": open_items[0]["frist_ende"] if open_items else None,
    }


def _service_item(
    module_id: str, spec: DeadlineSpec, facts: Mapping[str, Any], bundesland: str
) -> dict[str, Any]:
    """Select a service rule without borrowing VA assumptions or a letter date."""
    used = {
        key: facts.get(key)
        for key in ("zustellung_tatsaechlich", "document_type", "zustellungsart", "bundesland")
    }
    required_type = spec.applies_when.get("document_type")
    actual_type = facts.get("document_type")
    if actual_type and required_type and actual_type != required_type:
        return _result_item(module_id, spec, STATUS_NOT_APPLICABLE, None, [], used)
    if (
        not actual_type
        or not facts.get("zustellung_tatsaechlich")
        or not facts.get("zustellungsart")
        or (spec.rollover is not None and not facts.get("bundesland"))
        or any(facts.get(key) != value for key, value in spec.applies_when.items())
    ):
        return _result_item(
            module_id,
            spec,
            STATUS_MISSING_INPUT,
            None,
            [
                "Art des Schreibens, Zustelltag, Zustellungsart und Bundesland bestätigen. "
                "Auslandszustellung und öffentliche Zustellung gesondert prüfen lassen."
            ],
            used,
        )
    served = date.fromisoformat(facts["zustellung_tatsaechlich"])
    result = evaluate_spec(
        spec,
        FristInput(
            bescheid_datum=served,
            zustellung_tatsaechlich=served,
            document_type=actual_type,
            zustellungsart=facts["zustellungsart"],
            bundesland=bundesland,
        ),
        module_id=module_id,
    )
    assumptions = (
        []
        if facts.get("bundesland")
        else [f"Bundesland nicht angegeben — Feiertage für {bundesland} angenommen."]
    )
    return _result_item(module_id, spec, STATUS_COMPUTED, result, assumptions, used)


def frist_result_for_drafts(section: Mapping[str, Any]) -> FristResult | None:
    """The critical deadline as ``FristResult`` for the draft generator."""
    for item in section.get("items", []):
        if item["severity"] != "critical" or item["bekanntgabe"] is None:
            continue
        if item["status"] == STATUS_NOT_APPLICABLE:
            return FristResult(
                bekanntgabe=date.fromisoformat(item["bekanntgabe"]),
                frist_ende=date.fromisoformat(item["bekanntgabe"]),
                frist_typ=str(item["frist_typ"]),
                rollover_applied=False,
                oq1_flag=False,
                oq1_alternate_ende=None,
                explanation_de=str(item["explanation_de"] or ""),
                module_id=item["module_id"],
                spec_id=item["spec_id"],
            )
        if item["frist_ende"] is None:
            continue
        alt = item.get("oq1_alternate_ende")
        return FristResult(
            bekanntgabe=date.fromisoformat(item["bekanntgabe"]),
            frist_ende=date.fromisoformat(item["frist_ende"]),
            frist_typ=str(item["frist_typ"]),
            rollover_applied=bool(item["rollover_applied"]),
            oq1_flag=bool(item["oq1_flag"]),
            oq1_alternate_ende=date.fromisoformat(alt) if alt else None,
            explanation_de=str(item["explanation_de"] or ""),
            module_id=item["module_id"],
            spec_id=item["spec_id"],
        )
    return None
