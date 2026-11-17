"""Dossier generator (WP-103; ARCHITECTURE.md § 3.7).

Assembles the Mandatsvorbereitungs-Dossier for one case across its modules
from already-loaded case data. Pure apart from reading module content files:
no database, no LLM. The API layer (``app/services/dossier_service.py``)
loads the case; the eval harness (``eval/dossier_eval.py``) feeds goldset
inputs directly.

Which sections are AI-derived: ``evidence`` (claims written by the pipeline's
model, quotes verified deterministically) and ``drafts`` (templates filled
from those claims). Everything else is deterministic: the chronology is
regex extraction plus user decisions, deadlines come from the Fristen core,
calculations from module calculators, checklist and questions from module
data. The dossier therefore always carries the Art. 50 disclosure and
provenance objects.
"""

# Semantic Version: 1.0.0 | 2026-11-16 — WP-103 initial.

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import jsonschema

from app.dossier.chronology import (
    STATUS_CONFIRMED,
    STATUS_PROPOSED,
    STATUS_REJECTED,
    STATUS_USER_ADDED,
    ChronologyDecisions,
    SourceText,
    apply_decisions,
    propose_entries,
)
from app.dossier.deadlines import ModuleSpecs, compute_deadlines, frist_result_for_drafts
from app.dossier.module_content import (
    all_cues,
    module_dossier,
    select_checklist,
    select_questions,
)
from app.fristen.results import FristResult
from app.modules.runtime import deadline_specs, get_manifest

DOSSIER_SCHEMA_VERSION = "citizen-dossier-v1.0"
_SCHEMA_PATH = Path(__file__).with_name("citizen-dossier-v1.0.schema.json")

#: Files embedded in the PDF export (WP-103: provenance in both formats).
PDF_ATTACHMENTS = ("dossier.json", "provenance.json")

NOTICE_DE = (
    "Dieses Dossier hilft Ihnen, einen Termin bei einer Beratungsstelle oder "
    "einer Anwältin bzw. einem Anwalt vorzubereiten. Es ist keine "
    "Rechtsberatung und ersetzt sie nicht. Teile wurden von einem KI-System "
    "erstellt; Fristen und Beträge stammen aus festen Rechenregeln, beruhen "
    "aber auf Ihren Angaben. Prüfen Sie alles vor der Verwendung und nehmen "
    "Sie die Originalunterlagen zum Termin mit."
)


@lru_cache(maxsize=1)
def dossier_schema() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    return data


def validate_dossier(dossier: dict[str, Any]) -> None:
    """Raise ``jsonschema.ValidationError`` unless *dossier* is schema-valid."""
    jsonschema.validate(
        dossier, dossier_schema(), format_checker=jsonschema.Draft202012Validator.FORMAT_CHECKER
    )


@dataclass
class DossierInputs:
    """Everything the generator needs about one case (already loaded)."""

    case_id: str
    title: str | None
    created_at: str | None
    legal_areas: list[str]
    module_ids: list[str]
    sources: list[SourceText]
    decisions: ChronologyDecisions = field(default_factory=ChronologyDecisions)
    facts: dict[str, Any] = field(default_factory=dict)
    #: Claims: {claim_id, claim_text, claim_type, confidence_score,
    #: user_adjudication, bindings: [{quote_excerpt, binding_strength, source}]}
    claims: list[dict[str, Any]] = field(default_factory=list)
    #: {"result": <full calculation result>} or {"summary": {...}} or None
    calculation: dict[str, Any] | None = None
    revision: int = 0
    generated_at: str = ""
    disclosure: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)
    disclaimer_version: str = ""


#: Builds the draft annex from the dossier's critical deadline, the claims and
#: the deadline section (for the letter date the deadline was computed from).
DraftFactory = Callable[
    [FristResult | None, list[dict[str, Any]], dict[str, Any]], list[dict[str, Any]]
]


def chronology_entries(inputs: DossierInputs) -> list[Any]:
    """Proposals merged with the user's decisions (rejected ones included)."""
    contents = [c for c in (module_dossier(m) for m in inputs.module_ids) if c is not None]
    proposals = propose_entries(inputs.sources, all_cues(contents))
    return apply_decisions(proposals, inputs.decisions)


def _chronology_section(entries: Sequence[Any]) -> dict[str, Any]:
    counts = {STATUS_PROPOSED: 0, STATUS_CONFIRMED: 0, STATUS_USER_ADDED: 0, STATUS_REJECTED: 0}
    for entry in entries:
        counts[entry.status] = counts.get(entry.status, 0) + 1
    return {
        "entries": [e.as_dict() for e in entries if e.status != STATUS_REJECTED],
        "counts": counts,
    }


def _verification(bindings: Sequence[dict[str, Any]]) -> str:
    # Same rule as the draft generator's claim view (routes/documents.py).
    status = "unverifiziert"
    for binding in bindings:
        if float(binding.get("binding_strength", 0.0)) >= 0.8:
            return "exakt"
        status = "normalisiert"
    return status


def _evidence_section(claims: Sequence[dict[str, Any]]) -> dict[str, Any]:
    items = []
    for claim in claims:
        bindings = [
            {
                "quote_excerpt": str(b.get("quote_excerpt", "")),
                "binding_strength": float(b.get("binding_strength", 0.0)),
                "source": b.get("source"),
            }
            for b in claim.get("bindings", [])
        ]
        items.append(
            {
                "claim_id": str(claim["claim_id"]),
                "claim_text": str(claim.get("claim_text", "")),
                "claim_type": str(claim.get("claim_type", "")),
                "confidence_score": float(claim.get("confidence_score", 0.0)),
                "verification": _verification(bindings),
                "user_adjudication": claim.get("user_adjudication") or None,
                "bindings": bindings,
            }
        )
    return {"items": items}


def _disputed_questions(claims: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    questions: list[dict[str, Any]] = []
    for claim in claims:
        adjudication = claim.get("user_adjudication") or {}
        if adjudication.get("status") != "disputed":
            continue
        text = " ".join(str(claim.get("claim_text", "")).split())
        if len(text) > 300:
            text = text[:299] + "…"
        note = adjudication.get("note")
        question = (
            f"Ich halte diese Aussage der Analyse für unzutreffend: „{text}“"
            + (f" (meine Anmerkung: {note})" if note else "")
            + " — wie ist das zu bewerten?"
        )
        questions.append(
            {
                "id": f"disputed_{claim['claim_id']}",
                "module_id": None,
                "modules": [],
                "text_de": question,
                "topic": "strittige_aussagen",
                "origin": "disputed_claim",
            }
        )
    return questions


def _number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _calculations_section(calculation: dict[str, Any] | None) -> dict[str, Any]:
    """Only deterministic engine fields; the LLM commentary stays out."""
    if not calculation:
        return {"status": "none", "summary": None, "items": []}
    result = calculation.get("result")
    if isinstance(result, dict):
        items = []
        for calc in result.get("calculations_found") or []:
            if not isinstance(calc, dict):
                continue
            computed = calc.get("computed_values") or {}
            document_values = calc.get("document_values") or {}
            items.append(
                {
                    "label": str(calc.get("label", "")),
                    "relevant_rule": calc.get("relevant_rule"),
                    "deterministic_result": computed.get("deterministic_result"),
                    "computation_detail": computed.get("computation_detail"),
                    "authority_values": dict(document_values.get("extracted_numbers") or {}),
                    "discrepancy_found": bool(calc.get("discrepancy_found", False)),
                    "discrepancy_amount_eur": _number(calc.get("discrepancy_amount_eur")),
                    "discrepancy_direction": str(calc.get("discrepancy_direction", "keine")),
                }
            )
        overall = result.get("overall_assessment") or {}
        summary = {
            "total_discrepancies": int(overall.get("total_discrepancies", 0) or 0),
            "total_amount_eur": _number(overall.get("total_amount_eur")),
            "direction": overall.get("direction"),
        }
        return {"status": "available" if items else "none", "summary": summary, "items": items}
    summary_raw = calculation.get("summary")
    if isinstance(summary_raw, dict):
        return {
            "status": "summary_only",
            "summary": {
                "total_discrepancies": int(summary_raw.get("discrepancies", 0) or 0),
                "total_amount_eur": _number(summary_raw.get("total_amount_eur")),
                "direction": None,
            },
            "items": [],
        }
    return {"status": "none", "summary": None, "items": []}


def _modules_header(module_ids: Sequence[str]) -> list[dict[str, str]]:
    header = []
    for module_id in module_ids:
        manifest = get_manifest(module_id)
        title = manifest.raw.get("title") or {}
        header.append(
            {
                "id": module_id,
                "version": str(manifest.raw.get("version", "")),
                "title_de": str(title.get("de", module_id)),
            }
        )
    return header


def build_dossier(
    inputs: DossierInputs, draft_factory: DraftFactory | None = None
) -> dict[str, Any]:
    """Build and schema-validate the dossier for *inputs*."""
    contents = [c for c in (module_dossier(m) for m in inputs.module_ids) if c is not None]
    texts = [s.text for s in inputs.sources]
    entries = chronology_entries(inputs)
    warnings: list[str] = []

    deadlines = compute_deadlines(
        [ModuleSpecs(m, deadline_specs(m)) for m in inputs.module_ids],
        inputs.facts,
        [e for e in entries if e.status != STATUS_REJECTED],
    )
    for item in deadlines["items"]:
        if item["status"] == "missing_input":
            warnings.append(
                f"{item['label_de']}: nicht berechnet — Datum des Schreibens fehlt "
                "(in der Chronologie bestätigen oder ergänzen)."
            )
        elif item["status"] == "provisional":
            warnings.append(
                f"{item['label_de']}: vorläufig berechnet — Datum des Schreibens noch "
                "nicht bestätigt."
            )
    without_dossier = [m for m in inputs.module_ids if module_dossier(m) is None]
    if without_dossier:
        warnings.append(
            "Für folgende Rechtsgebiete liegt noch keine Checkliste/Fragenliste vor: "
            + ", ".join(without_dossier)
            + "."
        )
    if not inputs.claims:
        warnings.append("Keine Analyse-Aussagen vorhanden — Abschnitt Belege ist leer.")

    drafts: list[dict[str, Any]] = []
    if draft_factory is not None:
        drafts = draft_factory(frist_result_for_drafts(deadlines), inputs.claims, deadlines)

    dossier: dict[str, Any] = {
        "schema_version": DOSSIER_SCHEMA_VERSION,
        "revision": inputs.revision,
        "generated_at": inputs.generated_at,
        "case": {
            "case_id": inputs.case_id,
            "title": inputs.title,
            "created_at": inputs.created_at,
            "legal_areas": list(inputs.legal_areas),
            "modules": _modules_header(inputs.module_ids),
        },
        "notice": {"de": NOTICE_DE, "disclaimer_version": inputs.disclaimer_version},
        "sections": {
            "chronology": _chronology_section(entries),
            "document_checklist": {"items": select_checklist(contents, texts)},
            "deadlines": deadlines,
            "calculations": _calculations_section(inputs.calculation),
            "evidence": _evidence_section(inputs.claims),
            "questions": {
                "items": select_questions(contents, texts) + _disputed_questions(inputs.claims)
            },
            "drafts": {"items": drafts},
            "export": {"formats": ["json", "pdf"], "pdf_attachments": list(PDF_ATTACHMENTS)},
        },
        "warnings": warnings,
        "disclosure": inputs.disclosure,
        "provenance": inputs.provenance,
    }
    validate_dossier(dossier)
    return dossier
