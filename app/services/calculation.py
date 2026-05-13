"""Calculation verification service: LLM-driven numerical audit of SGB II documents.

Checks all monetary calculations in Jobcenter / SGB II documents for correctness
against current German social law calculation rules. Extracts monetary figures,
applies SGB II rules (Bürgergeld / Sozialhilfe), compares with Jobcenter
calculations, and flags discrepancies.

Uses the same shared OpenRouterClient singleton and JSON parsing helpers as the
reasoning engine in :mod:`app.services.reasoning`.
"""

# Semantic Version: 0.1.0

from __future__ import annotations

import logging
from typing import Any

from app.services.reasoning import (
    JSONParseError,
    _STRICT_SUFFIX,
    _get_client,
    _parse_json_response,
)
from app.utils.tokens import trim_text

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Reset / close helpers (re-exported for test convenience)
# ---------------------------------------------------------------------------

# The shared _client singleton lives in reasoning.py; these aliases exist so
# that callers can reset or close the client without importing reasoning.py.

reset_client = __import__("app.services.reasoning", fromlist=["reset_client"]).reset_client
close_client = __import__("app.services.reasoning", fromlist=["close_client"]).close_client


# ---------------------------------------------------------------------------
# System prompt — calculation verification for SGB II documents
# ---------------------------------------------------------------------------

_CALCULATION_SYSTEM = (
    "Du bist ein präziser, mathematisch exakter Rechnungsprüfer für "
    "deutsches Sozialrecht (SGB II / SGB XII).\n\n"
    "Dir wird der Text eines behördlichen Dokuments vorgelegt (z. B. "
    "Jobcenter-Bescheid über Leistungen nach dem SGB II / Bürgergeld).\n\n"
    "Deine Aufgabe:\n"
    "1. Finde ALLE monetären Berechnungen im Dokument (Bedarf, Einkommen, "
    "Freibeträge, Abzüge, Aufrechnungen, Auszahlungsbetrag usw.).\n"
    "2. Extrahiere die vom Jobcenter verwendeten Zahlenwerte.\n"
    "3. Berechne selbst, was nach den aktuellen SGB-II-Regeln korrekt wäre.\n"
    "4. Vergleiche deine Berechnung mit der Behördenberechnung.\n"
    "5. Gib für jede gefundene Berechnung an, ob und in welcher Höhe eine "
    "Abweichung vorliegt.\n\n"
    "Aktuelle SGB-II-Berechnungsregeln (2024/2025, Bürgergeld-Reform):\n\n"
    "**Freibetrag bei Erwerbstätigkeit (§ 11b SGB II):**\n"
    "- Grundfreibetrag: 100,00 EUR\n"
    "- 20 % für den Bruttoeinkommensteil von 100,01 EUR bis 520,00 EUR\n"
    "- 30 % für den Bruttoeinkommensteil von 520,01 EUR bis 1.000,00 EUR\n"
    "- 10 % für den Bruttoeinkommensteil von 1.000,01 EUR bis 1.200,00 EUR\n"
    "  (falls mindestens ein minderjähriges Kind im Haushalt lebt; sonst\n"
    "   bis 1.500,00 EUR)\n\n"
    "**Aufrechnung bei Darlehen (§ 42a SGB II):**\n"
    "- Die laufende monatliche Aufrechnung beträgt 5 % des maßgebenden\n"
    "  monatlichen Regelbedarfs (NICHT 10 %!)\n\n"
    "**Regelbedarf 2025:**\n"
    "- Regelbedarfsstufe 1 (Alleinstehende / Alleinerziehende): 563,00 EUR\n"
    "- Regelbedarfsstufe 2 (Partner in Bedarfsgemeinschaft): 506,00 EUR\n\n"
    "Gib NUR ein JSON-Objekt mit folgender Struktur zurück:\n"
    "{\n"
    '  "calculations_found": [\n'
    "    {\n"
    '      "label": "Beschreibung der Berechnung (z. B. '
    '\\"Erwerbstätigenfreibetrag\\")",\n'
    '      "document_values": {\n'
    '        "extracted_numbers": {\n'
    '          "brutto": 780.00,\n'
    '          "netto": 710.10,\n'
    '          "regelbedarf": 563.00,\n'
    '          "unterkunft": 540.00\n'
    "        },\n"
    '        "authority_calculation": "Wie das Jobcenter gerechnet hat '
    '(als Text)"\n'
    "      },\n"
    '      "correct_calculation": "Die korrekte Berechnung Schritt für '
    'Schritt (als Text)",\n'
    '      "discrepancy_found": true,\n'
    '      "discrepancy_amount_eur": 26.00,\n'
    '      "discrepancy_direction": "zulasten",\n'
    '      "relevant_rule": "z. B. § 11b SGB II – Freibetrag: 20 % für '
    '100,01–520 EUR, 30 % für 520,01–1.000 EUR",\n'
    '      "commentary": "Erläuterung des Fehlers auf Deutsch"\n'
    "    }\n"
    "  ],\n"
    '  "overall_assessment": {\n'
    '    "total_discrepancies": 1,\n'
    '    "total_amount_eur": 26.00,\n'
    '    "direction": "zulasten",\n'
    '    "summary": "Gesamteindruck zu den Berechnungsfehlern",\n'
    '    "recommended_action": "Was der Nutzer tun sollte '
    '(z. B. Widerspruch einlegen)"\n'
    "  }\n"
    "}\n\n"
    "Wichtige Regeln:\n"
    "- Verwende deutsche Zahlenformate im Text, aber numerische Werte im JSON "
    "(Punkt als Dezimaltrenner).\n"
    "- Wenn keine Berechnungen im Dokument gefunden werden, gib ein leeres "
    'calculations_found-Array und eine entsprechende Bewertung zurück.\n'
    "- Wenn die Behördenberechnung korrekt ist, setze discrepancy_found auf "
    'false und discrepancy_direction auf "keine".\n'
    "- discrepancy_direction: \"zulasten\" = Behörde hat zu wenig berechnet; "
    '"zugunsten" = Behörde hat zu viel berechnet; "keine" = kein Fehler.\n'
    "- Alle Texte und Erläuterungen auf Deutsch verfassen.\n"
    "- Erfinde keine Zahlen, die nicht im Dokument genannt werden.\n"
    "- Gib ausschließlich gültiges JSON zurück. Kein Prosatext. Keine "
    "Markdown-Formatierung."
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
    """Verify all monetary calculations in *normalized_text* against current
    SGB II calculation rules using a specialised LLM call.

    Extracts monetary figures from the document, applies the current
    Bürgergeld / SGB II rules (freibeträge, aufrechnung, regelbedarf),
    compares with the authority's calculation, and flags any discrepancies.

    Parameters
    ----------
    normalized_text :
        The cleaned document text (e.g. from OCR / synthesis pipeline).
    claims :
        Optional list of claims from the reasoning pipeline.  Used as
        additional context for the calculation check.  When ``None`` the
        function still extracts numbers from just the document text.
    sections :
        Optional output sections from the reasoning pipeline.  Used as
        additional context for the calculation check.

    Returns
    -------
    dict[str, Any]
        A dict with keys:

        - ``calculations_found``: ``list[dict]`` — one entry per identified
          calculation, each containing the document values, the correct
          calculation, discrepancy info, and the relevant rule.
        - ``overall_assessment``: ``dict`` — summary of all discrepancies
          with total amount, direction, and recommended action.

        When the feature is disabled (``ENABLE_CALCULATION_CHECK = False``),
        returns an early "skipped" result::

            {
                "calculations_found": [],
                "overall_assessment": {
                    "total_discrepancies": 0,
                    "total_amount_eur": 0.0,
                    "direction": "keine",
                    "summary": (
                        "Berechnungsprüfung ist deaktiviert. "
                        "Zum Aktivieren ENABLE_CALCULATION_CHECK=True setzen."
                    ),
                    "recommended_action": "",
                },
            }

        When no monetary calculations are found in the text or the LLM call
        fails, returns an empty result with the same structure.
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

    # ── Build the user prompt ────────────────────────────────────────
    user_parts: list[str] = []

    user_parts.append("## DOKUMENT\n")
    # Trim the document to a reasonable budget to avoid token overflow.
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
                # Only include non-empty sections, trimmed to a reasonable length.
                user_parts.append(f"**{key}:** {trim_text(val, 1500)}")

    user_content = "\n".join(user_parts)

    # ── Call the LLM ─────────────────────────────────────────────────
    client = _get_client()

    messages = [
        {"role": "system", "content": _CALCULATION_SYSTEM + _STRICT_SUFFIX},
        {"role": "user", "content": user_content},
    ]

    logger.info(
        "check_calculations: prompt ~%d chars (user=%d, system=%d)",
        len(user_content) + len(_CALCULATION_SYSTEM) + len(_STRICT_SUFFIX),
        len(user_content),
        len(_CALCULATION_SYSTEM) + len(_STRICT_SUFFIX),
    )

    raw = await client.chat_completion(
        messages,
        temperature=0.1,
        model=calculation_model,
        timeout=calculation_timeout,
        max_retries=1,
    )

    # ── Parse JSON with retry ────────────────────────────────────────
    try:
        result = _parse_json_response(raw, context="calculation check")
    except JSONParseError:
        logger.warning(
            "JSON parse error in check_calculations, retrying with stricter prompt"
        )
        messages_minimal = [
            {"role": "system", "content": _CALCULATION_SYSTEM + _STRICT_SUFFIX},
            {
                "role": "user",
                "content": user_content[: s.MAX_FINAL_INPUT_CHARS],
            },
        ]
        raw2 = await client.chat_completion(
            messages_minimal,
            temperature=0.0,
            model=calculation_model,
            timeout=calculation_timeout,
            max_retries=1,
        )
        result = _parse_json_response(raw2, context="calculation check (retry)")

    # ── Validate the result structure ────────────────────────────────
    if not isinstance(result, dict):
        logger.warning(
            "check_calculations: LLM returned non-dict result (%s); "
            "returning empty result",
            type(result).__name__,
        )
        return _empty_result(
            "Die Berechnungsprüfung konnte kein gültiges Ergebnis liefern."
        )

    calculations = result.get("calculations_found", [])
    if not isinstance(calculations, list):
        logger.warning(
            "check_calculations: 'calculations_found' is not a list (%s); "
            "returning empty result",
            type(calculations).__name__,
        )
        return _empty_result(
            "Die Berechnungsprüfung konnte keine Berechnungen identifizieren."
        )

    # Validate each calculation entry.
    validated_calculations: list[dict[str, Any]] = []
    for calc in calculations:
        if not isinstance(calc, dict):
            continue

        # Normalize discrepancy_direction.
        dd = calc.get("discrepancy_direction", "keine")
        if dd not in ("zulasten", "zugunsten", "keine"):
            dd = "keine"

        # Normalize discrepancy_amount_eur to float.
        da = calc.get("discrepancy_amount_eur", 0.0)
        try:
            da = float(da)
        except (TypeError, ValueError):
            da = 0.0

        # Normalize discrepancy_found to bool.
        df = bool(calc.get("discrepancy_found", False))

        validated_calculations.append({
            "label": str(calc.get("label", "")).strip(),
            "document_values": {
                "extracted_numbers": dict(
                    calc.get("document_values", {}).get("extracted_numbers", {})
                ),
                "authority_calculation": str(
                    calc.get("document_values", {}).get("authority_calculation", "")
                ).strip(),
            },
            "correct_calculation": str(calc.get("correct_calculation", "")).strip(),
            "discrepancy_found": df,
            "discrepancy_amount_eur": da,
            "discrepancy_direction": dd,
            "relevant_rule": str(calc.get("relevant_rule", "")).strip(),
            "commentary": str(calc.get("commentary", "")).strip(),
        })

    # Validate overall assessment.
    raw_overall = result.get("overall_assessment", {})
    if not isinstance(raw_overall, dict):
        logger.warning(
            "check_calculations: 'overall_assessment' is not a dict (%s); "
            "using defaults",
            type(raw_overall).__name__,
        )
        raw_overall = {}

    total_discrepancies = raw_overall.get("total_discrepancies", 0)
    try:
        total_discrepancies = int(total_discrepancies)
    except (TypeError, ValueError):
        total_discrepancies = 0

    total_amount_eur = raw_overall.get("total_amount_eur", 0.0)
    try:
        total_amount_eur = float(total_amount_eur)
    except (TypeError, ValueError):
        total_amount_eur = 0.0

    overall_direction = raw_overall.get("direction", "keine")
    if overall_direction not in ("zulasten", "zugunsten", "keine"):
        overall_direction = "keine"

    overall_assessment = {
        "total_discrepancies": total_discrepancies,
        "total_amount_eur": total_amount_eur,
        "direction": overall_direction,
        "summary": str(raw_overall.get("summary", "")).strip(),
        "recommended_action": str(raw_overall.get("recommended_action", "")).strip(),
    }

    # If the LLM returned no calculations at all, use a neutral assessment.
    if not validated_calculations and not raw_overall.get("summary"):
        overall_assessment["summary"] = (
            "Es wurden keine Berechnungen im Dokument gefunden oder "
            "die Berechnungsprüfung konnte keine eindeutigen Ergebnisse liefern."
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
