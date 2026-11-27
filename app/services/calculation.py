"""Calculation verification harness: three-phase numerical audit (module calculators).

Architecture (trustworthiness split):
    1. LLM **extracts** structured monetary data from the document text.
    2. A **deterministic module calculator** computes correct values and
       flags discrepancies.
    3. LLM **explains** the findings in natural language and suggests actions.

WP-93: everything area-specific — extraction schema and prompts, parameter
keys, the rules engine, the referral wording — is module code behind the
typed ``app.modules.sdk.Calculator`` interface (e.g.
``modules/sozialrecht/calculators.py``). This file is the generic harness:
LLM calls with retry, parameter-store access, result assembly. The request's
modules (``app.modules.runtime.request_modules``) decide which calculators
run; a request whose modules ship none gets an empty result.
"""

# Semantic Version: 0.4.2 | 2026-11-27 — WP-134: unavailable checks retain deterministic
# refusal commentary/assessment; mixed results keep an explicit review requirement.
# 0.4.1 | 2026-11-26 — preserve qualified engine status and
# report unavailable checks without a successful-arithmetic assessment.
# 0.4.0 | 2026-11-16 — prompt set 3.0.0: cross-check scoped to
# the document (CR-16), document truncation marked (CR-07), stage
# temperatures/caps (CR-03/CR-04).
# 0.3.0

from __future__ import annotations

import json
import logging
from datetime import date
from typing import Any

from app.core.router import get_shared_client
from app.modules.sdk import Calculator, ParameterLookup
from app.services.prompts import stage_max_tokens, stage_temperature
from app.services.reasoning import (
    _STRICT_SUFFIX,
    JSONParseError,
    _parse_json_response,
)
from app.utils.tokens import trim_document, trim_text

#: Heading that starts the analysis context appended after the document.
_CONTEXT_HEADING = "\n\n## KONTEXT:"


def _document_part(user_content: str) -> str:
    """The ``## DOKUMENT`` part of the extraction message (CR-16, F-22).

    The cross-check must search only the document: a number that appears
    only in the appended analysis context (claims/sections written by a
    model) is exactly what it exists to catch.
    """
    text = user_content
    if text.startswith("## DOKUMENT\n"):
        text = text[len("## DOKUMENT\n") :]
    return text.split(_CONTEXT_HEADING, 1)[0]


logger = logging.getLogger(__name__)


class _StoreParameterSource:
    """``sdk.ParameterSource`` bound to one DB session and parameter domain."""

    def __init__(self, session: Any, domain: str) -> None:
        self._session = session
        self._domain = domain

    async def numeric(self, key: str, as_of: date) -> ParameterLookup:
        from app.services.parameter_store import get_parameter_numeric

        return await get_parameter_numeric(self._session, key, as_of, domain=self._domain)

    async def json(self, key: str, as_of: date) -> ParameterLookup:
        from app.services.parameter_store import get_parameter_json

        return await get_parameter_json(self._session, key, as_of, domain=self._domain)


# ---------------------------------------------------------------------------
# Calculation check entry point
# ---------------------------------------------------------------------------


async def check_calculations(
    normalized_text: str,
    *,
    claims: list[dict[str, Any]] | None = None,
    sections: dict[str, str] | None = None,
    module_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Verify all monetary calculations in *normalized_text* with module calculators.

    Three-phase architecture (per calculator):
        1. LLM extracts structured monetary data from the document.
        2. The module's deterministic calculator computes correct values
           and flags discrepancies.
        3. LLM explains the findings in natural language.

    Parameters
    ----------
    normalized_text :
        The cleaned document text (e.g. from OCR / synthesis pipeline).
    claims :
        Optional list of claims from the reasoning pipeline.
    sections :
        Optional output sections from the reasoning pipeline.
    module_ids :
        Modules the request runs with (``app.modules.runtime.request_modules``);
        ``None`` or ``[]`` → no calculator runs.

    Returns
    -------
    dict[str, Any]
        A dict with keys ``calculations_found`` and ``overall_assessment``
        (plus ``legal_snapshot``), matching the format expected by the
        pipeline and frontend.
    """
    from app.core.config import settings as s
    from app.modules.runtime import calculators_for, request_modules

    # ── Early return when calculation check is disabled ──────────────
    if not s.ENABLE_CALCULATION_CHECK:
        logger.info("check_calculations: skipped (ENABLE_CALCULATION_CHECK=False)")
        return _empty_result(
            "Berechnungsprüfung ist deaktiviert. "
            "Zum Aktivieren ENABLE_CALCULATION_CHECK=True setzen."
        )

    # Omitted and empty selections both run no module (D-070).
    resolved_modules = module_ids if module_ids is not None else request_modules(None)
    calculators = calculators_for(resolved_modules)
    if not calculators:
        logger.info("check_calculations: no calculator for modules %s", resolved_modules)
        return _empty_result(
            "Für die Rechtsgebiete dieses Falls ist keine deterministische "
            "Berechnungsprüfung verfügbar."
        )

    calculation_model = s.CALCULATION_MODEL or s.PRIMARY_MODEL
    calculation_timeout = s.CALCULATION_TIMEOUT_SEC

    logger.info(
        "check_calculations: starting (input=%d chars, model=%s, timeout=%.1fs, calculators=%s)",
        len(normalized_text),
        calculation_model,
        calculation_timeout,
        [f"{mid}:{calc.id}" for mid, calc in calculators],
    )

    client = get_shared_client()

    # ── Build the user prompt (shared between extraction and explanation) ──
    user_parts: list[str] = []
    user_parts.append("## DOKUMENT\n")
    user_parts.append(trim_document(normalized_text, s.MAX_FINAL_INPUT_CHARS * 2))

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

    results = [
        await _run_calculator(
            module_id,
            calculator,
            client,
            user_content,
            model=calculation_model,
            timeout=calculation_timeout,
        )
        for module_id, calculator in calculators
    ]
    if len(results) == 1:
        return results[0]
    return _merge_results(results)


async def _run_calculator(
    module_id: str,
    calculator: Calculator,
    client: Any,
    user_content: str,
    *,
    model: str,
    timeout: float,
) -> dict[str, Any]:
    """Run extraction → deterministic engine → explanation for one calculator."""
    from app.modules.runtime import parameter_domain

    # ==================================================================
    # Phase 1: Extraction
    # ==================================================================

    logger.info("check_calculations: phase 1 — extracting structured data from document")

    extraction = await _llm_extract(
        client,
        user_content,
        model=model,
        timeout=timeout,
        calculator=calculator,
    )

    if extraction is None:
        # Extraction completely failed — return empty result.
        return _empty_result(
            "Die Extraktion strukturierter Daten aus dem Dokument ist "
            "fehlgeschlagen. Eine Berechnungsprüfung war nicht möglich."
        )

    # ==================================================================
    # Phase 2: Deterministic module calculator
    # ==================================================================

    logger.info("check_calculations: phase 2 — running deterministic rules engine")

    # ── Fetch legal parameters from the store (module domain) ────────
    from app.db.session import get_session_factory

    param_overrides: dict[str, Any] = {}
    legal_snapshot: dict[str, Any] | None = None
    domain = parameter_domain(module_id)

    session_factory = get_session_factory()
    try:
        if domain is None:
            raise LookupError(f"module {module_id!r} declares no parameter domain")
        async with session_factory() as db_session:
            param_overrides, legal_snapshot = await calculator.load_parameters(
                extraction, _StoreParameterSource(db_session, domain)
            )
    except Exception as exc:
        logger.warning(
            "Failed to fetch legal parameters from DB: %s. Using hardcoded fallbacks.",
            exc,
        )
        param_overrides = {}
        legal_snapshot = None

    calculations = calculator.process(extraction, param_overrides)

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
        model=model,
        timeout=timeout,
        calculator=calculator,
    )

    # ── Merge explanation into calculations ──────────────────────────
    validated_calculations = _merge_explanations(calculations, explanation)

    # ── Build overall assessment ─────────────────────────────────────
    overall_assessment = _build_overall_assessment(
        validated_calculations, explanation, referral_hint=calculator.referral_hint
    )

    logger.info(
        "check_calculations: complete (model=%s, %d calculations found, "
        "%d discrepancies, total_amount=%.2f EUR)",
        model,
        len(validated_calculations),
        overall_assessment["total_discrepancies"],
        overall_assessment["total_amount_eur"],
    )

    return {
        "calculations_found": validated_calculations,
        "overall_assessment": overall_assessment,
        "legal_snapshot": legal_snapshot if legal_snapshot else None,
    }


def _merge_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Combine several calculators' results (multi-module case).

    Totals are recomputed from the merged entries (deterministic); the
    textual summaries and actions are concatenated in calculator order.
    """
    calculations = [c for r in results for c in r.get("calculations_found", [])]
    explanation = {
        "overall_assessment": {
            "summary": " ".join(
                r["overall_assessment"]["summary"]
                for r in results
                if r["overall_assessment"].get("summary")
            ),
            "recommended_action": " ".join(
                r["overall_assessment"]["recommended_action"]
                for r in results
                if r["overall_assessment"].get("recommended_action")
            ),
        }
    }
    snapshots = [r["legal_snapshot"] for r in results if r.get("legal_snapshot")]
    return {
        "calculations_found": calculations,
        "overall_assessment": _build_overall_assessment(calculations, explanation),
        "legal_snapshot": {"calculators": snapshots} if snapshots else None,
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
    calculator: Calculator,
) -> dict[str, Any] | None:
    """Call the extraction LLM and return parsed JSON, or ``None`` on failure."""
    from app.core.config import settings as s

    extraction_system = calculator.extraction_prompt

    messages = [
        {"role": "system", "content": extraction_system + _STRICT_SUFFIX},
        {"role": "user", "content": user_content},
    ]

    logger.info(
        "_llm_extract: prompt ~%d chars (user=%d, system=%d)",
        len(user_content) + len(extraction_system) + len(_STRICT_SUFFIX),
        len(user_content),
        len(extraction_system) + len(_STRICT_SUFFIX),
    )

    try:
        raw = await client.chat_completion(
            messages,
            temperature=stage_temperature("calc_extraction"),
            max_tokens=stage_max_tokens("calc_extraction"),
            model=model,
            timeout=timeout,
            max_retries=1,
        )
        result = _parse_json_response(raw, context="calculation extraction")
    except JSONParseError:
        logger.warning("JSON parse error in extraction, retrying with stricter prompt")
        messages_minimal = [
            {"role": "system", "content": extraction_system + _STRICT_SUFFIX},
            {"role": "user", "content": user_content[: s.MAX_FINAL_INPUT_CHARS]},
        ]
        try:
            raw2 = await client.chat_completion(
                messages_minimal,
                temperature=0.0,
                max_tokens=stage_max_tokens("calc_extraction"),
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
    document_text = _document_part(user_content)
    cross_check_warnings = calculator.cross_check(result, document_text)
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
    calculator: Calculator,
) -> dict[str, Any] | None:
    """Call the explanation LLM to enrich engine output with natural language.

    Returns the parsed JSON, or ``None`` if the call fails (caller falls back
    to the engine's templated commentary).
    """

    # Build an explanation prompt that includes the engine output so the
    # LLM can produce detailed commentary.
    engine_summary = json.dumps(
        _summarise_engine_output(engine_calculations),
        ensure_ascii=False,
        indent=2,
    )

    extraction_summary = json.dumps(
        calculator.summarise_extraction(extraction),
        ensure_ascii=False,
        indent=2,
    )
    explanation_system = calculator.explanation_prompt

    explanation_user = (
        f"{document_content}\n\n"
        f"## EXTRAHIERTE DATEN\n{extraction_summary}\n\n"
        f"## ERGEBNISSE DER PRÜF-ENGINE\n{engine_summary}\n"
    )

    messages = [
        {"role": "system", "content": explanation_system + _STRICT_SUFFIX},
        {"role": "user", "content": explanation_user},
    ]

    logger.info(
        "_llm_explain: prompt ~%d chars (user=%d, system=%d)",
        len(explanation_user) + len(explanation_system) + len(_STRICT_SUFFIX),
        len(explanation_user),
        len(explanation_system) + len(_STRICT_SUFFIX),
    )

    try:
        raw = await client.chat_completion(
            messages,
            temperature=stage_temperature("calc_explanation"),
            max_tokens=stage_max_tokens("calc_explanation"),
            model=model,
            timeout=timeout,
            max_retries=1,
        )
        result = _parse_json_response(raw, context="calculation explanation")
    except JSONParseError:
        logger.warning("JSON parse error in explanation LLM — using engine commentary as fallback")
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
        summary.append(
            {
                "index": i,
                "label": calc.get("label"),
                "computation_detail": calc.get("computed_values", {}).get("computation_detail", ""),
                "deterministic_result": calc.get("computed_values", {}).get("deterministic_result"),
                "discrepancy_found": calc.get("discrepancy_found"),
                "discrepancy_amount_eur": calc.get("discrepancy_amount_eur"),
                "discrepancy_direction": calc.get("discrepancy_direction"),
                "relevant_rule": calc.get("relevant_rule"),
                **({"status": calc["status"]} if "status" in calc else {}),
            }
        )
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
                    commentary_by_index[idx] = str(item.get("commentary", "")).strip()

    for i, calc in enumerate(engine_calculations):
        entry = dict(calc)  # shallow copy

        # Override commentary with LLM explanation if available.
        if commentary_by_index.get(i) and calc.get("status") not in (
            "missing_input",
            "unavailable",
        ):
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
            entry["discrepancy_amount_eur"] = float(entry.get("discrepancy_amount_eur", 0.0))
        except (TypeError, ValueError):
            entry["discrepancy_amount_eur"] = 0.0

        entry["discrepancy_found"] = bool(entry.get("discrepancy_found", False))

        enriched.append(entry)

    return enriched


def _build_overall_assessment(
    calculations: list[dict[str, Any]],
    explanation: dict[str, Any] | None,
    *,
    referral_hint: str = "",
) -> dict[str, Any]:
    """Build the ``overall_assessment`` dict from the engine + LLM results."""
    # Missing inputs are an unavailable check, not evidence that the amounts
    # agree. Keep this outcome deterministic even if the explanation claims
    # success. A provisional result (including a date without an amount) still
    # counts as a result; legacy calculators without status retain their path.
    if calculations and all(
        calc.get("status") in ("missing_input", "unavailable") for calc in calculations
    ):
        return {
            "total_discrepancies": 0,
            "total_amount_eur": 0.0,
            "direction": "keine",
            "summary": (
                "Eine Berechnungsprüfung war wegen fehlender oder ungeklärter "
                "Eingaben nicht möglich. Eine Aussage zur Richtigkeit der "
                "Berechnungen ist deshalb nicht möglich."
            ),
            "recommended_action": referral_hint
            or "Lassen Sie die fehlenden Angaben und rechtlichen Voraussetzungen prüfen.",
        }
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

    if any(calc.get("status") in ("missing_input", "unavailable") for calc in calculations):
        # Mixed modules may yield a result for one check and refuse another.
        # A language-model explanation cannot promote that into overall success.
        summary = (
            "Nicht alle Berechnungsprüfungen waren möglich. Fehlende oder "
            "ungeklärte Eingaben und rechtliche Voraussetzungen bleiben zu prüfen."
        )
        recommended_action = referral_hint or "Lassen Sie die offenen Angaben prüfen."

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
        recommended_action = referral_hint

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
