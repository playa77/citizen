"""Calculation verification service: three-phase numerical audit of SGB II documents.

Architecture (trustworthiness split):
    1. LLM **extracts** structured monetary data from the document text.
    2. **Deterministic rules engine** (:mod:`app.services.rules_engine`) computes
       correct values and flags discrepancies.
    3. LLM **explains** the findings in natural language and suggests actions.

This replaces the earlier approach where a single LLM call performed extraction,
calculation, AND explanation inside a single ``_CALCULATION_SYSTEM`` prompt.
"""

# Semantic Version: 0.2.0

from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import BaseModel, Field

from app.services.reasoning import (
    JSONParseError,
    _STRICT_SUFFIX,
    _get_client,
    _parse_json_response,
)
from app.services.rules_engine import process_extraction
from app.utils.tokens import trim_text

logger = logging.getLogger(__name__)

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
    brutto_einkommen: float | None = Field(
        None, description="Monatliches Bruttoeinkommen in EUR"
    )
    netto_einkommen: float | None = Field(
        None, description="Monatliches Nettoeinkommen in EUR"
    )
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
    kdu_unterkunft: float | None = Field(
        None, description="Kaltmiete in EUR"
    )
    kdu_heizung: float | None = Field(
        None, description="Heizkosten in EUR"
    )
    kdu_nebenkosten: float | None = Field(
        None, description="Nebenkosten in EUR"
    )
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
    sanktion_authority: float | None = Field(
        None, description="Sanktionsbetrag in EUR"
    )
    mehrbedarf_authority: float | None = Field(
        None, description="Mehrbedarf in EUR"
    )
    unterhaltszahlung: float | None = Field(
        None, description="Unterhaltszahlung in EUR"
    )
    kindergeld: float | None = Field(
        None, description="Kindergeld in EUR"
    )


class ExtractionResult(BaseModel):
    """Full structured extraction from an SGB II document."""

    person_type: str | None = Field(
        None, description="alleinstehend | partner | alleinerziehend"
    )
    has_minor_child: bool | None = Field(
        None, description="Minderjähriges Kind in der Bedarfsgemeinschaft"
    )
    period_year: int | None = Field(
        None, description="Jahr des Leistungszeitraums"
    )
    extracted_values: ExtractionValues = Field(default_factory=ExtractionValues)
    authority_calculation_text: str = Field(
        "", description="Wie das Jobcenter die Berechnung beschreibt"
    )
    extraction_notes: str = Field(
        "", description="Unsicherheiten oder fehlende Angaben"
    )


def cross_check_extraction(
    extraction: dict[str, Any], document_text: str
) -> list[str]:
    """Verify that extracted numbers appear in the document text.

    Returns a list of warnings for values not found in the document.
    """
    warnings: list[str] = []
    values = extraction.get("extracted_values") or {}

    for field_name, value in values.items():
        if value is None or not isinstance(value, (int, float)):
            continue
        # Check if the numeric value appears in the document text
        # Try common formats: "563.00", "563,00", "563", "563.0"
        candidates = [
            f"{value:.2f}",
            f"{value:.2f}".replace(".", ","),
            str(int(value)) if value == int(value) else None,
            f"{value:.1f}".replace(".", ","),
        ]
        found = any(
            c and c in document_text for c in candidates if c is not None
        )
        if not found:
            warnings.append(
                f"Extrahierter Wert '{field_name}' = {value} konnte nicht "
                f"im Dokumenttext gefunden werden. Wert könnte falsch extrahiert sein."
            )

    return warnings


# ---------------------------------------------------------------------------
# Reset / close helpers (re-exported for test convenience)
# ---------------------------------------------------------------------------

reset_client = __import__("app.services.reasoning", fromlist=["reset_client"]).reset_client
close_client = __import__("app.services.reasoning", fromlist=["close_client"]).close_client


# ---------------------------------------------------------------------------
# Phase 1: Extraction system prompt
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


# ---------------------------------------------------------------------------
# Phase 3: Explanation system prompt
# ---------------------------------------------------------------------------

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
# Calculation check entry point
# ---------------------------------------------------------------------------


async def check_calculations(
    normalized_text: str,
    *,
    claims: list[dict[str, Any]] | None = None,
    sections: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Verify all monetary calculations in *normalized_text* against SGB II rules.

    Three-phase architecture:
        1. LLM extracts structured monetary data from the document.
        2. Deterministic rules engine computes correct values and flags
           discrepancies.
        3. LLM explains the findings in natural language.

    Parameters
    ----------
    normalized_text :
        The cleaned document text (e.g. from OCR / synthesis pipeline).
    claims :
        Optional list of claims from the reasoning pipeline.
    sections :
        Optional output sections from the reasoning pipeline.

    Returns
    -------
    dict[str, Any]
        A dict with keys ``calculations_found`` and ``overall_assessment``,
        matching the format expected by the pipeline and frontend.
    """
    from app.core.config import settings as s

    # ── Early return when calculation check is disabled ──────────────
    if not s.ENABLE_CALCULATION_CHECK:
        logger.info("check_calculations: skipped (ENABLE_CALCULATION_CHECK=False)")
        return _empty_result(
            "Berechnungsprüfung ist deaktiviert. "
            "Zum Aktivieren ENABLE_CALCULATION_CHECK=True setzen."
        )

    calculation_model = s.CALCULATION_MODEL or s.PRIMARY_MODEL
    calculation_timeout = s.CALCULATION_TIMEOUT_SEC

    logger.info(
        "check_calculations: starting (input=%d chars, model=%s, timeout=%.1fs)",
        len(normalized_text),
        calculation_model,
        calculation_timeout,
    )

    client = _get_client()

    # ── Build the user prompt (shared between extraction and explanation) ──
    user_parts: list[str] = []
    user_parts.append("## DOKUMENT\n")
    user_parts.append(trim_text(normalized_text, s.MAX_FINAL_INPUT_CHARS * 2))

    if claims:
        user_parts.append("\n\n## KONTEXT: CLAIMS (aus der rechtlichen Analyse)\n")
        for i, claim in enumerate(claims):
            ct = claim.get("claim_type", "?")
            text = claim.get("claim_text", "")
            cs = claim.get("confidence_score", 0.0)
            user_parts.append(f"{i + 1}. [{ct}] (confidence={cs:.2f}) {text}")

    if sections:
        user_parts.append("\n\n## KONTEXT: ABSCHNITTE (aus der rechtlichen Analyse)\n")
        for key, val in sections.items():
            if val and val.strip():
                user_parts.append(f"**{key}:** {trim_text(val, 1500)}")

    user_content = "\n".join(user_parts)

    # ==================================================================
    # Phase 1: Extraction
    # ==================================================================

    logger.info("check_calculations: phase 1 — extracting structured data from document")

    extraction = await _llm_extract(
        client,
        user_content,
        model=calculation_model,
        timeout=calculation_timeout,
    )

    if extraction is None:
        # Extraction completely failed — return empty result.
        return _empty_result(
            "Die Extraktion strukturierter Daten aus dem Dokument ist "
            "fehlgeschlagen. Eine Berechnungsprüfung war nicht möglich."
        )

    # ==================================================================
    # Phase 2: Deterministic rules engine
    # ==================================================================

    logger.info("check_calculations: phase 2 — running deterministic rules engine")

    # ── Fetch legal parameters from the DB ───────────────────────────
    from datetime import date as dt_date
    from app.services.parameter_store import (
        build_legal_snapshot,
        get_parameter_numeric,
        get_parameter_json,
    )

    period_year_val = extraction.get("period_year")
    try:
        period_year_int = int(period_year_val) if period_year_val else 2025
    except (TypeError, ValueError):
        period_year_int = 2025

    param_overrides: dict[str, Any] = {}
    legal_snapshot: dict[str, Any] | None = None
    from app.db.session import get_session_factory

    session_factory = get_session_factory()
    try:
        async with session_factory() as db_session:
            as_of = dt_date(period_year_int, 7, 1)  # mid-year

            # Fetch Regelbedarf parameters
            rbs1 = await get_parameter_numeric(db_session, "sgb2.regelbedarf.rbs1", as_of)
            rbs2 = await get_parameter_numeric(db_session, "sgb2.regelbedarf.rbs2", as_of)
            param_overrides["rbs1"] = rbs1
            param_overrides["rbs2"] = rbs2

            # Fetch Freibetrag brackets from the DB (if available)
            brackets = await get_parameter_json(
                db_session, "sgb2.einkommen.erwerbstaetigenfreibetrag.band", as_of
            )
            if brackets["value"] is not None:
                param_overrides["freibetrag_brackets"] = brackets["value"].get("bands", [])
                param_overrides["freibetrag_base_allowance"] = float(
                    brackets["value"].get("base_allowance", 100.0)
                )
                param_overrides["freibetrag_child_upper_limit"] = float(
                    brackets["value"].get("minor_child_upper", 1500.0)
                )

            # Build the legal snapshot for audit trail
            legal_snapshot = await build_legal_snapshot(db_session, year=period_year_int)
    except Exception as exc:
        logger.warning(
            "Failed to fetch legal parameters from DB: %s. Using hardcoded fallbacks.",
            exc,
        )
        param_overrides = {}
        legal_snapshot = None

    calculations = process_extraction(extraction, param_overrides=param_overrides)

    logger.info(
        "check_calculations: engine produced %d calculation entries",
        len(calculations),
    )

    # ==================================================================
    # Phase 3: Explanation
    # ==================================================================

    logger.info("check_calculations: phase 3 — explaining findings")

    explanation = await _llm_explain(
        client,
        user_content,
        calculations,
        extraction,
        model=calculation_model,
        timeout=calculation_timeout,
    )

    # ── Merge explanation into calculations ──────────────────────────
    validated_calculations = _merge_explanations(calculations, explanation)

    # ── Build overall assessment ─────────────────────────────────────
    overall_assessment = _build_overall_assessment(
        validated_calculations, explanation
    )

    logger.info(
        "check_calculations: complete (model=%s, %d calculations found, "
        "%d discrepancies, total_amount=%.2f EUR)",
        calculation_model,
        len(validated_calculations),
        overall_assessment["total_discrepancies"],
        overall_assessment["total_amount_eur"],
    )

    return {
        "calculations_found": validated_calculations,
        "overall_assessment": overall_assessment,
        "legal_snapshot": legal_snapshot if legal_snapshot else None,
    }


# ---------------------------------------------------------------------------
# Phase 1: LLM extraction call
# ---------------------------------------------------------------------------


async def _llm_extract(
    client: Any,
    user_content: str,
    *,
    model: str,
    timeout: float,
) -> dict[str, Any] | None:
    """Call the extraction LLM and return parsed JSON, or ``None`` on failure."""
    from app.core.config import settings as s

    messages = [
        {"role": "system", "content": _EXTRACTION_SYSTEM + _STRICT_SUFFIX},
        {"role": "user", "content": user_content},
    ]

    logger.info(
        "_llm_extract: prompt ~%d chars (user=%d, system=%d)",
        len(user_content) + len(_EXTRACTION_SYSTEM) + len(_STRICT_SUFFIX),
        len(user_content),
        len(_EXTRACTION_SYSTEM) + len(_STRICT_SUFFIX),
    )

    try:
        raw = await client.chat_completion(
            messages,
            temperature=0.1,
            model=model,
            timeout=timeout,
            max_retries=1,
        )
        result = _parse_json_response(raw, context="calculation extraction")
    except JSONParseError:
        logger.warning("JSON parse error in extraction, retrying with stricter prompt")
        messages_minimal = [
            {"role": "system", "content": _EXTRACTION_SYSTEM + _STRICT_SUFFIX},
            {"role": "user", "content": user_content[: s.MAX_FINAL_INPUT_CHARS]},
        ]
        try:
            raw2 = await client.chat_completion(
                messages_minimal,
                temperature=0.0,
                model=model,
                timeout=timeout,
                max_retries=1,
            )
            result = _parse_json_response(raw2, context="calculation extraction (retry)")
        except JSONParseError:
            logger.warning("Extraction JSON parse failed even after retry")
            return None

    if not isinstance(result, dict):
        logger.warning(
            "_llm_extract: LLM returned non-dict result (%s)",
            type(result).__name__,
        )
        return None

    # Cross-check: verify extracted numbers appear in the document text.
    document_text = user_content
    if document_text.startswith("## DOKUMENT\n"):
        document_text = document_text[len("## DOKUMENT\n") :]
    cross_check_warnings = cross_check_extraction(result, document_text)
    for warning in cross_check_warnings:
        logger.warning("cross_check: %s", warning)

    return result


# ---------------------------------------------------------------------------
# Phase 3: LLM explanation call
# ---------------------------------------------------------------------------


async def _llm_explain(
    client: Any,
    document_content: str,
    engine_calculations: list[dict[str, Any]],
    extraction: dict[str, Any],
    *,
    model: str,
    timeout: float,
) -> dict[str, Any] | None:
    """Call the explanation LLM to enrich engine output with natural language.

    Returns the parsed JSON, or ``None`` if the call fails (caller falls back
    to the engine's templated commentary).
    """
    from app.core.config import settings as s

    # Build an explanation prompt that includes the engine output so the
    # LLM can produce detailed commentary.
    engine_summary = json.dumps(
        _summarise_engine_output(engine_calculations),
        ensure_ascii=False,
        indent=2,
    )

    extraction_summary = json.dumps(
        {
            "person_type": extraction.get("person_type"),
            "period_year": extraction.get("period_year"),
            "has_minor_child": extraction.get("has_minor_child"),
            "authority_calculation_text": extraction.get(
                "authority_calculation_text", ""
            ),
            "extraction_notes": extraction.get("extraction_notes", ""),
        },
        ensure_ascii=False,
        indent=2,
    )

    explanation_user = (
        f"{document_content}\n\n"
        f"## EXTRAHIERTE DATEN\n{extraction_summary}\n\n"
        f"## ERGEBNISSE DER PRÜF-ENGINE\n{engine_summary}\n"
    )

    messages = [
        {"role": "system", "content": _EXPLANATION_SYSTEM + _STRICT_SUFFIX},
        {"role": "user", "content": explanation_user},
    ]

    logger.info(
        "_llm_explain: prompt ~%d chars (user=%d, system=%d)",
        len(explanation_user) + len(_EXPLANATION_SYSTEM) + len(_STRICT_SUFFIX),
        len(explanation_user),
        len(_EXPLANATION_SYSTEM) + len(_STRICT_SUFFIX),
    )

    try:
        raw = await client.chat_completion(
            messages,
            temperature=0.1,
            model=model,
            timeout=timeout,
            max_retries=1,
        )
        result = _parse_json_response(raw, context="calculation explanation")
    except JSONParseError:
        logger.warning(
            "JSON parse error in explanation LLM — using engine commentary as fallback"
        )
        return None

    if not isinstance(result, dict):
        logger.warning(
            "_llm_explain: LLM returned non-dict result (%s)",
            type(result).__name__,
        )
        return None

    return result


# ---------------------------------------------------------------------------
# Result assembly helpers
# ---------------------------------------------------------------------------


def _summarise_engine_output(
    calculations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build a compact summary of the engine output for the explanation LLM.

    Includes only the fields the LLM needs to write good commentary.
    """
    summary: list[dict[str, Any]] = []
    for i, calc in enumerate(calculations):
        summary.append({
            "index": i,
            "label": calc.get("label"),
            "computation_detail": calc.get("computed_values", {}).get(
                "computation_detail", ""
            ),
            "deterministic_result": calc.get("computed_values", {}).get(
                "deterministic_result"
            ),
            "discrepancy_found": calc.get("discrepancy_found"),
            "discrepancy_amount_eur": calc.get("discrepancy_amount_eur"),
            "discrepancy_direction": calc.get("discrepancy_direction"),
            "relevant_rule": calc.get("relevant_rule"),
        })
    return summary


def _merge_explanations(
    engine_calculations: list[dict[str, Any]],
    explanation: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Merge LLM-produced commentary into the engine's calculation entries.

    If *explanation* is ``None`` or parsing fails, the engine's templated
    commentary is kept as-is.
    """
    enriched: list[dict[str, Any]] = []

    # Build a lookup: index → commentary text.
    commentary_by_index: dict[int, str] = {}
    if explanation is not None:
        enriched_list = explanation.get("enriched_calculations", [])
        if isinstance(enriched_list, list):
            for item in enriched_list:
                if isinstance(item, dict):
                    idx = item.get("index", -1)
                    try:
                        idx = int(idx)
                    except (TypeError, ValueError):
                        continue
                    commentary_by_index[idx] = str(
                        item.get("commentary", "")

                    ).strip()

    for i, calc in enumerate(engine_calculations):
        entry = dict(calc)  # shallow copy

        # Override commentary with LLM explanation if available.
        if i in commentary_by_index and commentary_by_index[i]:
            entry["commentary"] = commentary_by_index[i]

        # Add extracted_numbers from the document_values for backward compat.
        if "document_values" not in entry:
            entry["document_values"] = {
                "extracted_numbers": {},
                "authority_calculation": "",
            }

        # Ensure all required fields are valid.
        dd = entry.get("discrepancy_direction", "keine")
        if dd not in ("zulasten", "zugunsten", "keine"):
            dd = "keine"
        entry["discrepancy_direction"] = dd

        try:
            entry["discrepancy_amount_eur"] = float(
                entry.get("discrepancy_amount_eur", 0.0)
            )
        except (TypeError, ValueError):
            entry["discrepancy_amount_eur"] = 0.0

        entry["discrepancy_found"] = bool(entry.get("discrepancy_found", False))

        enriched.append(entry)

    return enriched


def _build_overall_assessment(
    calculations: list[dict[str, Any]],
    explanation: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build the ``overall_assessment`` dict from the engine + LLM results."""
    # Compute totals from the engine output (deterministic, not LLM-derived).
    total_discrepancies = 0
    total_amount_eur = 0.0
    directions: list[str] = []

    for calc in calculations:
        if calc.get("discrepancy_found"):
            total_discrepancies += 1
            total_amount_eur += calc.get("discrepancy_amount_eur", 0.0)
            directions.append(calc.get("discrepancy_direction", "keine"))

    # Determine overall direction.
    if not directions:
        overall_direction = "keine"
    elif all(d == "zulasten" for d in directions):
        overall_direction = "zulasten"
    elif all(d == "zugunsten" for d in directions):
        overall_direction = "zugunsten"
    else:
        overall_direction = "gemischt"
        # Normalize to one of the three allowed values.
        overall_direction = "zulasten"  # default when mixed

    # Round total.
    total_amount_eur = round(total_amount_eur, 2)

    # Use LLM summary and recommendation if available.
    summary = ""
    recommended_action = ""
    if explanation is not None:
        oa = explanation.get("overall_assessment", {})
        if isinstance(oa, dict):
            summary = str(oa.get("summary", "")).strip()
            recommended_action = str(oa.get("recommended_action", "")).strip()

    if not summary:
        if not calculations:
            summary = (
                "Es wurden keine Berechnungen im Dokument gefunden oder "
                "die Berechnungsprüfung konnte keine eindeutigen Ergebnisse "
                "liefern."
            )
        elif total_discrepancies == 0:
            summary = (
                "Die Prüf-Engine hat bei den prüfbaren Posten keine "
                "Abweichungen festgestellt. Nicht alle Berechnungen "
                "konnten geprüft werden."
            )
        else:
            summary = (
                f"Es wurden {total_discrepancies} Abweichung(en) mit "
                f"einem Gesamtbetrag von {total_amount_eur:.2f} EUR "
                f"festgestellt."
            )

    if not recommended_action and total_discrepancies > 0:
        recommended_action = (
            "Bitte lassen Sie die Berechnung von einer Fachstelle "
            "oder einem Rechtsanwalt für Sozialrecht überprüfen."
        )

    return {
        "total_discrepancies": total_discrepancies,
        "total_amount_eur": total_amount_eur,
        "direction": overall_direction,
        "summary": summary,
        "recommended_action": recommended_action,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _empty_result(summary: str) -> dict[str, Any]:
    """Return a standardised empty result dict."""
    return {
        "calculations_found": [],
        "overall_assessment": {
            "total_discrepancies": 0,
            "total_amount_eur": 0.0,
            "direction": "keine",
            "summary": summary,
            "recommended_action": "",
        },
    }
