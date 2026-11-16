"""Sozialrecht calculators (WP-93; ARCHITECTURE.md § 2.4).

The SGB II calculation check as an ``app.modules.sdk.Calculator``: the
extraction schema and prompts, the parameter loader (versioned parameters
from the store, domain per ``module.yaml``) and the deterministic engine
(``rules_engine.process_extraction``). Moved from
``app/services/calculation.py`` (prompts, schema, cross-check, parameter
fetch) and ``app/services/parameter_store.build_legal_snapshot``; prompt
texts and parameter keys are byte-identical to v2.0.0.

The core harness (``app.services.calculation``) owns the LLM calls, retries,
timeouts and result assembly; nothing here performs I/O except through the
``ParameterSource`` the core passes in.
"""

# Semantic Version: 1.1.0 | 2026-11-16 — prompt set 3.0.0: P-14/P-15 rewritten
# (tagged layout, field definitions, values from ## DOKUMENT only, no model
# arithmetic in explanations); cross_check covers the document only (CR-16).
# 1.0.0

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, Field

from app.modules.sdk import Calculator, ParameterSource

from .rules_engine import process_extraction

# ---------------------------------------------------------------------------
# Pydantic extraction schema (single source of truth)
# ---------------------------------------------------------------------------


class ExtractionValues(BaseModel):
    """LLM-extracted values from an SGB II document (EUR per month unless noted).

    The field descriptions are the definitions the extraction prompt (P-14)
    shows the model: the prompt's field list is generated from this model, so
    schema and prompt cannot drift apart (prompt set 3.0.0).
    """

    regelbedarf_authority: float | None = Field(
        None, description="von der Behörde angesetzter Regelbedarf"
    )
    regelbedarf_stufe: int | None = Field(
        None, description="angewendete Regelbedarfsstufe (ganze Zahl, 1 oder 2)"
    )
    brutto_einkommen: float | None = Field(None, description="monatliches Bruttoeinkommen")
    netto_einkommen: float | None = Field(None, description="monatliches Nettoeinkommen")
    freibetrag_authority: float | None = Field(
        None, description="von der Behörde angesetzter Freibetrag"
    )
    aufrechnung_authority: float | None = Field(
        None, description="von der Behörde angesetzte monatliche Aufrechnung"
    )
    aufrechnung_regelbedarf_used: float | None = Field(
        None, description="der Aufrechnung zugrunde gelegter Regelbedarf"
    )
    kdu_unterkunft: float | None = Field(None, description="Kaltmiete")
    kdu_heizung: float | None = Field(None, description="Heizkosten")
    kdu_nebenkosten: float | None = Field(None, description="Nebenkosten")
    kdu_gesamt_authority: float | None = Field(
        None, description="von der Behörde angegebener Gesamtbetrag der Kosten der Unterkunft"
    )
    anrechenbares_einkommen_authority: float | None = Field(
        None, description="von der Behörde als anrechenbar angesetztes Einkommen"
    )
    auszahlungsbetrag_authority: float | None = Field(
        None, description="von der Behörde festgesetzter Auszahlungsbetrag"
    )
    sanktion_authority: float | None = Field(None, description="Minderungsbetrag (Sanktion)")
    mehrbedarf_authority: float | None = Field(None, description="Mehrbedarf")
    unterhaltszahlung: float | None = Field(None, description="Unterhaltszahlung")
    kindergeld: float | None = Field(None, description="Kindergeld")


class ExtractionResult(BaseModel):
    """Full structured extraction from an SGB II document."""

    person_type: str | None = Field(None, description="alleinstehend | partner | alleinerziehend")
    has_minor_child: bool | None = Field(
        None, description="Minderjähriges Kind in der Bedarfsgemeinschaft"
    )
    period_year: int | None = Field(None, description="Jahr des Leistungszeitraums")
    extracted_values: ExtractionValues = Field(
        default_factory=ExtractionValues,  # type: ignore[arg-type]
    )
    authority_calculation_text: str = Field(
        "", description="Wie das Jobcenter die Berechnung beschreibt"
    )
    extraction_notes: str = Field("", description="Unsicherheiten oder fehlende Angaben")


def cross_check_extraction(extraction: dict[str, Any], document_text: str) -> list[str]:
    """Verify that extracted numbers appear in the document text.

    Returns a list of warnings for values not found in the document.
    """
    warnings: list[str] = []
    values = extraction.get("extracted_values") or {}

    for field_name, value in values.items():
        if value is None or not isinstance(value, int | float):
            continue
        # Check if the numeric value appears in the document text
        # Try common formats: "563.00", "563,00", "563", "563.0"
        candidates = [
            f"{value:.2f}",
            f"{value:.2f}".replace(".", ","),
            str(int(value)) if value == int(value) else None,
            f"{value:.1f}".replace(".", ","),
        ]
        found = any(c and c in document_text for c in candidates if c is not None)
        if not found:
            warnings.append(
                f"Extrahierter Wert '{field_name}' = {value} konnte nicht "
                f"im Dokumenttext gefunden werden. Wert könnte falsch extrahiert sein."
            )

    return warnings


# ---------------------------------------------------------------------------
# Phase 1: Extraction system prompt
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Prompts (extraction: values only; explanation: engine numbers are authoritative)
# ---------------------------------------------------------------------------

# Prompt set 3.0.0 (docs/prompt-upgrade-proposal.md, P-14/P-15). Module
# code may import only app.modules.sdk, so the JSON-discipline block (S-02 of
# the core prompt set) is kept here as module data, verbatim.
_JSON_OBJECT_ONLY = (
    "Antworte ausschließlich mit einem einzigen JSON-Objekt.\n"
    "- Erstes Zeichen „{“, letztes Zeichen „}“; kein Text davor oder danach, keine "
    "Markdown-Zäune, keine Kommentare.\n"
    "- Genau die angegebenen Schlüssel (englisch): keiner fehlt, keiner kommt hinzu.\n"
    '- Ohne Inhalt: "" für Text, [] für Listen; null nur, wo das Format es zeigt.\n'
    "- Alle Textwerte auf Deutsch; Zeilenumbrüche in Strings als \\n."
)

#: Field definitions shown to the extractor; taken from the descriptions of
#: ``ExtractionValues`` above (single source of truth for the schema).
_EXTRACTION_FIELDS: list[tuple[str, str]] = [
    (name, str(info.description)) for name, info in ExtractionValues.model_fields.items()
]


def _extraction_prompt() -> str:
    null_values = ",\n".join(f'    "{k}": null' for k, _ in _EXTRACTION_FIELDS)
    return (
        "<rolle>\n"
        "Du extrahierst Werte aus deutschen Sozialrechtsdokumenten (SGB II / Bürgergeld). "
        "Eine nachgelagerte Prüf-Engine rechnet; du rechnest nicht.\n"
        "</rolle>\n\n"
        "<eingaben>\n"
        "„## DOKUMENT“ (z. B. Jobcenter-Bescheid, ggf. gekürzt), danach eventuell "
        "„## KONTEXT: CLAIMS“ und „## KONTEXT: ABSCHNITTE“ aus der rechtlichen Analyse. "
        "Entnimm Werte nur aus „## DOKUMENT“; der Kontext dient nur dem Verständnis.\n"
        "</eingaben>\n\n"
        "<felder>\n"
        "extracted_values (Euro-Beträge je Monat, soweit nicht anders angegeben):\n"
        + "\n".join(f"- {k}: {d}" for k, d in _EXTRACTION_FIELDS)
        + '\nperson_type: "alleinstehend", "partner" oder "alleinerziehend". '
        "has_minor_child: minderjähriges Kind in der Bedarfsgemeinschaft. period_year: Jahr "
        "des Leistungszeitraums, nicht des Schreibens.\n"
        "</felder>\n\n"
        "<regeln>\n"
        "- Übernimm nur Werte, die im Dokument als Zahl stehen. Berechne nichts: keine "
        "Summen, Differenzen, Prozente, auch nicht aus Teilbeträgen.\n"
        "- Steht ein Wert nicht als Zahl im Dokument, ist er mehrdeutig oder mit „[OCR "
        "unsicher]“ markiert: null, und Grund in extraction_notes.\n"
        "- Nennt das Dokument mehrere Monate mit verschiedenen Werten: Werte des ersten "
        "vollen Monats; vermerke das in extraction_notes.\n"
        "- Zahlen als JSON-Zahlen mit Punkt als Dezimaltrenner, ohne Tausenderpunkt "
        "(„1.234,56 €“ → 1234.56).\n"
        "- authority_calculation_text: die Berechnungsdarstellung des Dokuments wörtlich, "
        'höchstens 1.000 Zeichen; sonst "".\n'
        "- Erfinde keine Zahlen, Personentypen, Zeiträume oder Haushaltsdaten.\n"
        "</regeln>\n\n"
        "<ausgabeformat>\n"
        "{\n"
        '  "person_type": null,\n'
        '  "has_minor_child": null,\n'
        '  "period_year": null,\n'
        '  "extracted_values": {\n' + null_values + "\n  },\n"
        '  "authority_calculation_text": "",\n'
        '  "extraction_notes": ""\n'
        "}\n\n" + _JSON_OBJECT_ONLY + "\n</ausgabeformat>"
    )


def _explanation_prompt() -> str:
    return (
        "<rolle>\n"
        "Du erklärst einer betroffenen Person die Ergebnisse einer deterministischen "
        "Prüf-Engine für Berechnungen nach SGB II (Bürgergeld). Die Werte der Engine sind "
        "maßgeblich; du stellst sie nicht in Frage und rechnest nicht nach.\n"
        "</rolle>\n\n"
        "<eingaben>\n"
        "„## DOKUMENT“ (ggf. mit Kontext aus der rechtlichen Analyse), „## EXTRAHIERTE "
        "DATEN“ (JSON) und „## ERGEBNISSE DER PRÜF-ENGINE“: Liste mit index, label, "
        "computation_detail, deterministic_result, discrepancy_found, "
        "discrepancy_amount_eur, discrepancy_direction, relevant_rule.\n"
        "</eingaben>\n\n"
        "<aufgabe>\n"
        "Schreibe für jeden Engine-Eintrag eine commentary (index = sein index) und danach "
        "overall_assessment.\n"
        "</aufgabe>\n\n"
        "<regeln>\n"
        "- commentary: höchstens 2 Sätze in Alltagssprache.\n"
        "- Nenne nur Zahlen, die wörtlich in den Engine-Ergebnissen oder im Dokument stehen; "
        "bilde keine Summen, Differenzen oder Prozente.\n"
        "- discrepancy_direction und discrepancy_amount_eur unverändert übernehmen; deute "
        "die Richtung nur, wenn computation_detail sie erklärt.\n"
        "- relevant_rule unverändert nennen; keine weiteren Normen.\n"
        "- discrepancy_found true: Die Angabe im Bescheid weicht möglicherweise ab. Ursache "
        "nur aus computation_detail oder authority_calculation_text, sonst „Ursache aus den "
        "Unterlagen nicht erkennbar“.\n"
        "- Keine Abweichung: bestätigen und sagen, dass nur die prüfbaren Posten geprüft "
        "wurden.\n"
        "- deterministic_result null: nennen, welche Angabe für die Prüfung fehlt "
        "(extraction_notes).\n"
        "- summary: höchstens 3 Sätze. recommended_action: 1 bis 2 Schritte der Person, z. B. "
        "Aufschlüsselung der Berechnung erbitten oder Widerspruch prüfen.\n"
        "- Erfinde keine Normen, Rechtsprechung oder Tatsachen.\n"
        "</regeln>\n\n"
        "<ausgabeformat>\n"
        "{\n"
        '  "enriched_calculations": [ { "index": 0, "commentary": "..." } ],\n'
        '  "overall_assessment": { "summary": "...", "recommended_action": "..." }\n'
        "}\n\n" + _JSON_OBJECT_ONLY + "\n</ausgabeformat>"
    )


# ---------------------------------------------------------------------------
# P-16 regime banner (module data) and the core wrapper (CR-06)
# ---------------------------------------------------------------------------


_EXTRACTION_SYSTEM = _extraction_prompt()
_EXPLANATION_SYSTEM = _explanation_prompt()


# ---------------------------------------------------------------------------
# Parameters
# ---------------------------------------------------------------------------

#: Period year used when the extraction names none (v2.0.0 behaviour).
_DEFAULT_PERIOD_YEAR = 2025

#: Parameters whose versions are recorded in the audit snapshot.
_SNAPSHOT_KEYS = ("sgb2.regelbedarf.rbs1", "sgb2.regelbedarf.rbs2")


def _period_year(extraction: dict[str, Any]) -> int:
    period_year_val = extraction.get("period_year")
    try:
        return int(period_year_val) if period_year_val else _DEFAULT_PERIOD_YEAR
    except (TypeError, ValueError):
        return _DEFAULT_PERIOD_YEAR


async def _legal_snapshot(source: ParameterSource, year: int) -> dict[str, Any]:
    """Record which parameter versions were used (``case_run.legal_snapshot``)."""
    as_of = date(year, 7, 1)  # mid-year lookup
    snapshot: dict[str, Any] = {"year": year, "parameter_versions": []}
    for key in _SNAPSHOT_KEYS:
        result = await source.numeric(key, as_of)
        if result["value"] is not None:
            regime = result.get("regime") or ""
            version_str = f"{key}@{result['valid_from']}" + (f"({regime})" if regime else "")
            snapshot["parameter_versions"].append(version_str)
    return snapshot


async def load_parameters(
    extraction: dict[str, Any], source: ParameterSource
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Fetch the rules-engine overrides for the extraction's period year."""
    period_year_int = _period_year(extraction)
    param_overrides: dict[str, Any] = {}
    as_of = date(period_year_int, 7, 1)  # mid-year

    # Regelbedarf parameters
    param_overrides["rbs1"] = await source.numeric("sgb2.regelbedarf.rbs1", as_of)
    param_overrides["rbs2"] = await source.numeric("sgb2.regelbedarf.rbs2", as_of)

    # Freibetrag brackets (if available)
    brackets = await source.json("sgb2.einkommen.erwerbstaetigenfreibetrag.band", as_of)
    if brackets["value"] is not None:
        param_overrides["freibetrag_brackets"] = brackets["value"].get("bands", [])
        param_overrides["freibetrag_base_allowance"] = float(
            brackets["value"].get("base_allowance", 100.0)
        )
        param_overrides["freibetrag_child_upper_limit"] = float(
            brackets["value"].get("minor_child_upper", 1500.0)
        )

    legal_snapshot = await _legal_snapshot(source, period_year_int)
    return param_overrides, legal_snapshot


def summarise_extraction(extraction: dict[str, Any]) -> dict[str, Any]:
    """Context the explanation LLM sees about the extraction."""
    return {
        "person_type": extraction.get("person_type"),
        "period_year": extraction.get("period_year"),
        "has_minor_child": extraction.get("has_minor_child"),
        "authority_calculation_text": extraction.get("authority_calculation_text", ""),
        "extraction_notes": extraction.get("extraction_notes", ""),
    }


SGB2_CALCULATOR = Calculator(
    id="sgb2_leistungsberechnung",
    extraction_prompt=_EXTRACTION_SYSTEM,
    explanation_prompt=_EXPLANATION_SYSTEM,
    load_parameters=load_parameters,
    process=process_extraction,
    summarise_extraction=summarise_extraction,
    cross_check=cross_check_extraction,
    referral_hint=(
        "Bitte lassen Sie die Berechnung von einer Fachstelle "
        "oder einem Rechtsanwalt für Sozialrecht überprüfen."
    ),
)

#: Declared in ``module.yaml`` as ``calculators: calculators:CALCULATORS``.
CALCULATORS: tuple[Calculator, ...] = (SGB2_CALCULATOR,)
