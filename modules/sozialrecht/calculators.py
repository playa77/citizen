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

# Semantic Version: 1.0.0

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
    """LLM-extracted monetary values from an SGB II document."""

    regelbedarf_authority: float | None = Field(
        None, description="Vom Jobcenter angesetzter Regelbedarf in EUR"
    )
    regelbedarf_stufe: int | None = Field(
        None, description="Angewendete Regelbedarfsstufe (1 oder 2)"
    )
    brutto_einkommen: float | None = Field(None, description="Monatliches Bruttoeinkommen in EUR")
    netto_einkommen: float | None = Field(None, description="Monatliches Nettoeinkommen in EUR")
    freibetrag_authority: float | None = Field(
        None, description="Vom Jobcenter angesetzter Freibetrag in EUR"
    )
    aufrechnung_authority: float | None = Field(
        None, description="Vom Jobcenter angesetzte monatliche Aufrechnung in EUR"
    )
    aufrechnung_regelbedarf_used: float | None = Field(
        None,
        description="Der für die Aufrechnung zugrunde gelegte Regelbedarf in EUR",
    )
    kdu_unterkunft: float | None = Field(None, description="Kaltmiete in EUR")
    kdu_heizung: float | None = Field(None, description="Heizkosten in EUR")
    kdu_nebenkosten: float | None = Field(None, description="Nebenkosten in EUR")
    kdu_gesamt_authority: float | None = Field(
        None, description="Von der Behörde angegebener KdU-Gesamtbetrag in EUR"
    )
    anrechenbares_einkommen_authority: float | None = Field(
        None,
        description="Von der Behörde als anrechenbar angesetztes Einkommen in EUR",
    )
    auszahlungsbetrag_authority: float | None = Field(
        None,
        description="Von der Behörde festgesetzter Auszahlungsbetrag in EUR",
    )
    sanktion_authority: float | None = Field(None, description="Sanktionsbetrag in EUR")
    mehrbedarf_authority: float | None = Field(None, description="Mehrbedarf in EUR")
    unterhaltszahlung: float | None = Field(None, description="Unterhaltszahlung in EUR")
    kindergeld: float | None = Field(None, description="Kindergeld in EUR")


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

_EXTRACTION_SYSTEM = (
    "Du bist ein präziser Datenextraktor für deutsche Sozialrechtsdokumente "
    "(SGB II / Bürgergeld).\n\n"
    "Dir wird der Text eines behördlichen Dokuments vorgelegt (z. B. "
    "Jobcenter-Bescheid).\n\n"
    "Deine Aufgabe: Extrahiere strukturierte Daten aus dem Dokument — "
    "ausschließlich die im Dokument genannten Werte. **Berechne nichts.** "
    "Führe keine Additionen, Multiplikationen oder Prozentrechnungen durch.\n\n"
    "Regeln:\n"
    "- **Extrahiere ausschließlich Werte, die explizit im Dokument genannt "
    "werden.**\n"
    "- Setze jeden numerischen Wert, der nicht explizit im Dokument genannt "
    "wird, auf ``null``.\n"
    "- Setze jeden Wert, der nicht explizit mit einer Zahl genannt wird, auf "
    "null. Auch wenn du ihn erschließen oder ableiten könntest.\n"
    "- Wenn ein Wert unsicher ist oder interpretiert werden muss, setze ihn "
    "auf ``null`` und vermerke die Unsicherheit in ``extraction_notes``.\n"
    "- Wenn du unsicher bist, ob ein Wert korrekt ist, setze ihn auf null.\n"
    "- Erfinde keine Zahlen, Personentypen, Zeiträume oder Haushaltsdaten.\n"
    "- Verwende Punkt als Dezimaltrenner in JSON-Zahlenwerten.\n"
    "- Alle Textfelder auf Deutsch.\n\n"
    "Das JSON-Schema unten entspricht dem Pydantic-Modell. "
    "Halte dich exakt an diese Struktur.\n"
    "Gib NUR ein JSON-Objekt mit folgender Struktur zurück:\n"
    "{\n"
    '  "person_type": "alleinstehend" | "partner" | "alleinerziehend" | null,\n'
    '  "has_minor_child": true | false | null,\n'
    '  "period_year": 2025 | null,\n'
    '  "extracted_values": {\n'
    '    "regelbedarf_authority": 563.00 | null,\n'
    '    "regelbedarf_stufe": 1 | 2 | null,\n'
    '    "brutto_einkommen": 1200.00 | null,\n'
    '    "netto_einkommen": 950.00 | null,\n'
    '    "freibetrag_authority": 184.00 | null,\n'
    '    "aufrechnung_authority": 28.15 | null,\n'
    '    "aufrechnung_regelbedarf_used": 563.00 | null,\n'
    '    "kdu_unterkunft": 540.00 | null,\n'
    '    "kdu_heizung": 80.00 | null,\n'
    '    "kdu_nebenkosten": null,\n'
    '    "kdu_gesamt_authority": 620.00 | null,\n'
    '    "anrechenbares_einkommen_authority": 900.00 | null,\n'
    '    "auszahlungsbetrag_authority": 500.00 | null,\n'
    '    "sanktion_authority": null,\n'
    '    "mehrbedarf_authority": null,\n'
    '    "unterhaltszahlung": null,\n'
    '    "kindergeld": null\n'
    "  },\n"
    '  "authority_calculation_text": "Freitext: Wie das Jobcenter die '
    'Berechnung beschreibt (im Dokument genannter Text)",\n'
    '  "extraction_notes": "Freitext: Unsicherheiten oder fehlende Angaben"\n'
    "}\n\n"
    "Kein Prosatext außerhalb des JSON. Keine Markdown-Fences. Keine "
    "zusätzlichen Schlüssel."
)


_EXPLANATION_SYSTEM = (
    "Du bist ein sorgfältiger Erklärer für sozialrechtliche Berechnungen "
    "(SGB II / Bürgergeld).\n\n"
    "Dir werden vorgelegt:\n"
    "1. Der Text des Originaldokuments (Jobcenter-Bescheid o. Ä.).\n"
    "2. Extrahierte Werte aus dem Dokument (von einem Extraktor ermittelt).\n"
    "3. Berechnungsergebnisse einer deterministischen Prüf-Engine, "
    "die bereits erkannt hat, bei welchen Posten eine Abweichung "
    "zwischen Behördenangabe und gesetzlichem Sollwert vorliegt.\n\n"
    "Deine Aufgabe:\n"
    "- Erkläre in verständlichem Deutsch, was die Prüf-Engine gefunden hat.\n"
    "- Wenn Abweichungen vorliegen: Erkläre, warum die Behördenberechnung "
    "möglicherweise falsch ist und woran der Fehler liegen könnte.\n"
    "- Nenne, was die betroffene Person bei der Behörde erfragen oder "
    "beanstanden kann.\n"
    "- Formuliere eine Gesamtbewertung (summary) und eine konkrete "
    "Handlungsempfehlung (recommended_action).\n\n"
    "Wichtige Regeln:\n"
    "- **Die von der Prüf-Engine berechneten Werte sind die autoritativen "
    "Zahlen.** Du darfst sie nicht in Frage stellen oder neu berechnen.\n"
    "- Verwende die von der Engine vorgegebene discrepancy_direction und "
    "den discrepancy_amount_eur unverändert.\n"
    "- Wenn die Engine keine Abweichung festgestellt hat, bestätige das, "
    "weise aber darauf hin, dass nur die prüfbaren Posten kontrolliert "
    "wurden.\n"
    "- Wenn Daten fehlen und die Engine deshalb nichts prüfen konnte, "
    "erkläre, welche Angaben für eine vollständige Prüfung fehlen.\n"
    "- Erfinde keine Paragraphen, Rechtsprechung oder Tatsachen.\n"
    "- Alle Texte auf Deutsch.\n\n"
    "Gib NUR ein JSON-Objekt mit folgender Struktur zurück:\n"
    "{\n"
    '  "enriched_calculations": [\n'
    "    {\n"
    '      "index": 0,\n'
    '      "commentary": "Erläuterung auf Deutsch"\n'
    "    }\n"
    "  ],\n"
    '  "overall_assessment": {\n'
    '    "summary": "Gesamteindruck zu den Berechnungen",\n'
    '    "recommended_action": "Was der Nutzer tun sollte '
    '(z. B. Widerspruch einlegen, Behörde um Aufschlüsselung bitten)"\n'
    "  }\n"
    "}\n\n"
    "Kein Prosatext außerhalb des JSON. Keine Markdown-Fences. Keine "
    "zusätzlichen Schlüssel."
)


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
