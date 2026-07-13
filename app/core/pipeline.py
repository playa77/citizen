"""8-Stage reasoning pipeline orchestrator with SSE streaming and timeout enforcement.

Pipeline stages:
    1. Input Normalization
    2. Issue Classification   ─┐  concurrent (WP-003)
    3. Question Decomposition  ─┘
    4. Evidence Retrieval
    5. Claim Construction
    6. Verification Pass
    7. Adversarial Legal Review
    8. Output Generation

Each stage yields an SSE-formatted event:
    ``data: {"stage": "...", "status": "complete", "payload": {...}}\\n\\n``

"""

# Semantic Version: 0.1.0

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncGenerator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, select

from app.core import config as cfg
from app.db.models import LegalChunk
from app.db.session import get_async_session
from app.utils.text import normalize_text

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------


class PipelineTimeoutError(Exception):
    """Raised when the full pipeline execution exceeds the configured timeout."""


class StageExecutionError(Exception):
    """Raised when a single pipeline stage fails irrecoverably."""


class OcrQualityError(Exception):
    """Raised when OCR quality is below the minimum threshold (WP-42)."""


# ---------------------------------------------------------------------------
# Pipeline state
# ---------------------------------------------------------------------------


@dataclass
class PipelineState:
    """Mutable state carried through all 8 pipeline stages.

    Attributes
    ----------
    input_text :
        Raw text uploaded by the user (pre-normalization).
    normalized_text :
        Cleaned / standardised text (stage 1 output).
    issues :
        Legal topics identified by the classifier (stage 2).
    questions :
        Explicit legal questions extracted from the text (stage 3).
    retrieved_chunks :
        Evidence chunks retrieved from pgvector (stage 4).
    claims :
        Claims with confidence scores and types (stage 5).
    verified_claims :
        Claims cross-referenced against source text (stage 6).
    adversarial_review :
        Adversarial legal review results (stage 7).
    final_output :
        7-part formatted result dictionary (stage 8).
    errors :
        Collected stage errors, if any.
    """

    input_text: str
    normalized_text: str = ""
    issues: list[str] = field(default_factory=list)
    questions: list[str] = field(default_factory=list)
    retrieved_chunks: list[dict[str, Any]] = field(default_factory=list)
    claims: list[dict[str, Any]] = field(default_factory=list)
    verified_claims: list[dict[str, Any]] = field(default_factory=list)
    adversarial_review: dict[str, Any] = field(default_factory=dict)
    calculation_result: dict[str, Any] = field(default_factory=dict)
    final_output: dict[str, str] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    stream_output_lines: list[str] = field(default_factory=list)
    # legal_areas: list of legal_area keys (e.g. ["sozialrecht"] or
    # ["erbrecht", "familienrecht"]) selected for this case. When empty
    # the pipeline behaves exactly as before — fully backward compatible.
    legal_areas: list[str] = field(default_factory=list)
    # intake_session_id: optional reference to the IntakeSession that
    # produced the legal_areas + enriched input_text. Persisted on
    # case_run_area rows after the pipeline finishes.
    intake_session_id: str | None = None
    # per_area_chunks: per-area retrieved chunks keyed by legal_area
    # (only populated when legal_areas is non-empty). The merged
    # retrieved_chunks field is the union, capped at MAX_CHUNKS_FOR_FINAL.
    per_area_chunks: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    # WP-30: pseudonymization mapping for this case run
    pii_mapping: dict[str, Any] | None = None
    pseudonymization_warnings: list[str] = field(default_factory=list)
    # legal_regime_banner: regime-awareness banner injected into LLM prompts
    # for construction and generation stages (WP-24). Populated during
    # classification/decomposition using the current date.
    legal_regime_banner: str = ""
    # WP-42: OCR quality report from pre-processing quality gate
    ocr_quality_report: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Stage ordering
# ---------------------------------------------------------------------------

_STAGES: list[str] = [
    "normalization",
    "classification",
    "decomposition",
    "retrieval",
    "construction",
    "verification",
    "generation",
    "adversarial_review",
    "calculation_check",
]

# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _populate_regime_banner(state: PipelineState) -> None:
    """Set ``state.legal_regime_banner`` based on the current date.

    This function is called once after classification/triage completes so
    that all subsequent pipeline stages can inject the regime-awareness
    banner into their LLM prompts.

    Currently uses ``date.today()`` as the reference date.  Future
    enhancements may extract the Bescheid date from the normalized text
    for historical cases.
    """
    from datetime import date as _dt

    from app.services.regime import legal_regime, regime_banner

    regime = legal_regime(_dt.today())
    state.legal_regime_banner = regime_banner(regime)
    logger.info(
        "Regime banner set: regime=%s banner_len=%d",
        regime,
        len(state.legal_regime_banner),
    )


def _sse_event(stage: str, status: str, payload: dict[str, Any]) -> str:
    """Format a dictionary as an SSE data line.

    Returns a string of the form::

        data: {"stage": "...", "status": "...", "payload": {...}}\n\n
    """
    data = {
        "stage": stage,
        "status": status,
        "payload": payload,
    }
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def _sse_stream_event(lines: list[str]) -> str:
    """Format a stream output progress event as an SSE data line."""
    data = {
        "stage": "stream_output",
        "status": "streaming",
        "payload": {"lines": lines},
    }
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def _stage_payload(
    state: PipelineState,
    *,
    stage_name: str,
    duration_ms: int,
) -> dict[str, Any]:
    """Return a snapshot payload appropriate for the given stage."""
    payload: dict[str, Any] = {"duration_ms": duration_ms}

    if stage_name == "normalization":
        payload["text_length"] = len(state.normalized_text)
    elif stage_name == "classification":
        payload["issues"] = state.issues
        payload["issue_count"] = len(state.issues)
    elif stage_name == "decomposition":
        payload["questions"] = state.questions
        payload["question_count"] = len(state.questions)
    elif stage_name == "retrieval":
        payload["chunk_count"] = len(state.retrieved_chunks)
    elif stage_name == "construction":
        payload["claim_count"] = len(state.claims)
        payload["claims"] = state.claims
    elif stage_name == "verification":
        payload["verified_claim_count"] = len(state.verified_claims)
        payload["verified_claims"] = state.verified_claims
    elif stage_name == "adversarial_review":
        payload["review_count"] = len(state.adversarial_review.get("reviews", []))
        payload["key_risks"] = state.adversarial_review.get("overall_assessment", {}).get(
            "key_risks", []
        )
    elif stage_name == "calculation_check":
        payload["calculations_found"] = len(state.calculation_result.get("calculations_found", []))
        payload["discrepancies"] = state.calculation_result.get("overall_assessment", {}).get(
            "total_discrepancies", 0
        )
        payload["total_amount_eur"] = state.calculation_result.get("overall_assessment", {}).get(
            "total_amount_eur", 0.0
        )
    elif stage_name == "generation":
        payload["sections"] = list(state.final_output.keys())

    return payload


# ---------------------------------------------------------------------------
# Stage implementations
# ---------------------------------------------------------------------------


async def _stage_normalization(state: PipelineState) -> None:
    """Stage 1 — strip whitespace, normalize encoding, clean OCR artefacts."""
    state.normalized_text = normalize_text(state.input_text)
    logger.info("Normalization complete (%d chars)", len(state.normalized_text))


async def _stage_classification(state: PipelineState) -> None:
    """Stage 2 — LLM identifies legal topics at stake."""
    from app.services.prompts import get_prompts
    from app.services.reasoning import classify_issues

    system_prompt = get_prompts(state.legal_areas)["classification"]
    state.issues = await classify_issues(
        state.normalized_text,
        system_prompt=system_prompt,
    )
    logger.info("Classification complete (%d issues)", len(state.issues))


async def _stage_decomposition(state: PipelineState) -> None:
    """Stage 3 — extract 3-5 explicit legal questions."""
    from app.services.prompts import get_prompts
    from app.services.reasoning import decompose_questions

    system_prompt = get_prompts(state.legal_areas)["decomposition"]
    state.questions = await decompose_questions(
        state.normalized_text,
        system_prompt=system_prompt,
    )
    logger.info("Decomposition complete (%d questions)", len(state.questions))


async def _run_classification_and_decomposition_stages(
    state: PipelineState,
) -> AsyncGenerator[str, None]:
    """Run classification and decomposition after normalization.

    When ``COMBINE_TRIAGE_STAGES`` is ``True`` (WP-006), both tasks are
    resolved by a single ``triage_document()`` LLM call. Otherwise they
    run concurrently via ``asyncio.gather()`` (WP-003).

    SSE events are emitted in the canonical order: classification first, then
    decomposition.
    """
    from app.services.prompts import get_prompts
    from app.services.reasoning import (
        classify_issues,
        decompose_questions,
        triage_document,
    )

    t0 = time.monotonic()

    # ── WP-006: combined triage path ───────────────────────────────────
    if cfg._get_settings().COMBINE_TRIAGE_STAGES:
        logger.info("  → launching combined triage (classification + decomposition)")
        system_prompt = get_prompts(state.legal_areas)["triage"]
        try:
            triage_result = await triage_document(
                state.normalized_text,
                system_prompt=system_prompt,
            )
        except Exception as exc:
            logger.exception("Combined triage failed")
            state.errors.append(f"triage (classification+decomposition): {exc}")
            raise StageExecutionError(f"Combined triage failed: {exc}") from exc

        state.issues = triage_result["issues"]
        state.questions = triage_result["questions"]

        # WP-24: populate regime banner for subsequent LLM calls.
        _populate_regime_banner(state)

        dur = int((time.monotonic() - t0) * 1000)

        logger.info(
            "Triage complete (%d issues, %d questions, %dms)",
            len(state.issues),
            len(state.questions),
            dur,
        )

        yield _sse_event(
            stage="classification",
            status="complete",
            payload=_stage_payload(
                state,
                stage_name="classification",
                duration_ms=dur,
            ),
        )

        yield _sse_event(
            stage="decomposition",
            status="complete",
            payload=_stage_payload(
                state,
                stage_name="decomposition",
                duration_ms=dur,
            ),
        )
        return

    # ── WP-003: parallel path (legacy, COMBINE_TRIAGE_STAGES=False) ───
    logger.info("  → launching classification + decomposition in parallel")

    cls_task = asyncio.create_task(classify_issues(state.normalized_text), name="classification")
    dec_task = asyncio.create_task(decompose_questions(state.normalized_text), name="decomposition")

    # Wait for both concurrently.  ``return_exceptions=True`` lets us inspect
    # each result individually and produce clear failure messages.
    cls_result, dec_result = await asyncio.gather(cls_task, dec_task, return_exceptions=True)

    cls_dur = int((time.monotonic() - t0) * 1000)

    # -- Classification (always emitted first) ---------------------------------
    if isinstance(cls_result, BaseException):
        logger.exception("Stage classification failed in parallel batch")
        state.errors.append(f"classification: {cls_result}")
        raise StageExecutionError(f"Stage 'classification' failed: {cls_result}") from cls_result

    state.issues = cls_result
    logger.info("Classification complete (%d issues)", len(state.issues))

    # WP-24: populate regime banner for subsequent LLM calls.
    _populate_regime_banner(state)

    yield _sse_event(
        stage="classification",
        status="complete",
        payload=_stage_payload(
            state,
            stage_name="classification",
            duration_ms=cls_dur,
        ),
    )

    # -- Decomposition (emitted second) ----------------------------------------
    if isinstance(dec_result, BaseException):
        logger.exception("Stage decomposition failed in parallel batch")
        state.errors.append(f"decomposition: {dec_result}")
        raise StageExecutionError(f"Stage 'decomposition' failed: {dec_result}") from dec_result

    state.questions = dec_result
    logger.info("Decomposition complete (%d questions)", len(state.questions))

    dec_dur = int((time.monotonic() - t0) * 1000)

    yield _sse_event(
        stage="decomposition",
        status="complete",
        payload=_stage_payload(
            state,
            stage_name="decomposition",
            duration_ms=dec_dur,
        ),
    )


async def _run_final_stages(
    state: PipelineState,
    stream_progress: bool = False,
) -> AsyncGenerator[str, None]:
    """Run construction, verification, and generation in a single LLM call.

    When ``COMBINE_FINAL_STAGES`` is ``True`` (WP-007), all three tasks are
    resolved by a single ``generate_grounded_answer()`` call followed by
    deterministic local verification. The adversarial review stage is NOT
    included here — it runs as a separate pipeline stage afterwards.

    Otherwise each stage runs as a separate LLM call (legacy path).

    SSE events are emitted in the canonical order: construction first, then
    verification, then generation.
    """
    from app.services.prompts import get_prompts
    from app.services.verification import verify_claims_against_chunks

    t0 = time.monotonic()

    # ── WP-007: combined final stages path ────────────────────────────
    if cfg._get_settings().COMBINE_FINAL_STAGES:
        logger.info(
            "  → launching combined grounded answer " "(construction + verification + generation)"
        )
        grounded_prompt = get_prompts(state.legal_areas)["grounded_answer"]

        # WP-24: inject regime awareness banner.
        if state.legal_regime_banner:
            grounded_prompt = f"{state.legal_regime_banner}\n\n{grounded_prompt}"

        if stream_progress and cfg._get_settings().ENABLE_PROGRESS_STREAM:
            from app.services.reasoning import generate_grounded_answer_stream

            accumulated_text: list[str] = []
            last_emit_time = time.monotonic()
            llm_claims: list[dict[str, Any]] | None = None
            sections: dict[str, str] | None = None

            try:
                async for item in generate_grounded_answer_stream(
                    state.normalized_text,
                    state.issues,
                    state.questions,
                    state.retrieved_chunks,
                    system_prompt=grounded_prompt,
                ):
                    if item["type"] == "token":
                        accumulated_text.append(item["content"])
                        # Emit SSE progress every ~200ms or on line breaks
                        now = time.monotonic()
                        full_text = "".join(accumulated_text)
                        if (now - last_emit_time) >= 0.2 or "\n" in item["content"]:
                            lines = full_text.split("\n")
                            last_4 = lines[-4:]
                            state.stream_output_lines = last_4
                            yield _sse_stream_event(last_4)
                            last_emit_time = now
                    elif item["type"] == "done":
                        result = item["result"]
                        llm_claims = result["claims"]
                        sections = result["sections"]
            except Exception as exc:
                logger.exception("Combined grounded answer stream failed")
                state.errors.append(
                    f"grounded answer (construction+verification+generation): {exc}"
                )
                raise StageExecutionError(f"Combined grounded answer failed: {exc}") from exc

            if llm_claims is None or sections is None:
                raise StageExecutionError(
                    "Combined grounded answer stream completed without a result"
                )
        else:
            from app.services.reasoning import generate_grounded_answer

            try:
                grounded = await generate_grounded_answer(
                    state.normalized_text,
                    state.issues,
                    state.questions,
                    [],  # claims — unused by grounded answer, regenerated from LLM
                    state.retrieved_chunks,
                    system_prompt=grounded_prompt,
                )
            except Exception as exc:
                logger.exception("Combined grounded answer failed")
                state.errors.append(
                    f"grounded answer (construction+verification+generation): {exc}"
                )
                raise StageExecutionError(f"Combined grounded answer failed: {exc}") from exc

            llm_claims = grounded["claims"]
            sections = grounded["sections"]

        # -- Stage 5: Construction (populated from LLM claims) ---------------
        state.claims = llm_claims or []
        construct_dur = int((time.monotonic() - t0) * 1000)

        logger.info(
            "Construction complete (%d claims, %dms — from grounded answer)",
            len(state.claims),
            construct_dur,
        )

        yield _sse_event(
            stage="construction",
            status="complete",
            payload=_stage_payload(
                state,
                stage_name="construction",
                duration_ms=construct_dur,
            ),
        )

        # -- Stage 6: Verification (deterministic local) ---------------------
        ver_start = time.monotonic()
        state.verified_claims = verify_claims_against_chunks(
            state.claims,
            state.retrieved_chunks,
        )
        verify_dur = int((time.monotonic() - ver_start) * 1000)

        logger.info(
            "Verification complete (%d verified claims, %dms — deterministic local)",
            len(state.verified_claims),
            verify_dur,
        )

        yield _sse_event(
            stage="verification",
            status="complete",
            payload=_stage_payload(
                state,
                stage_name="verification",
                duration_ms=verify_dur,
            ),
        )

        # -- Stage 7: Generation (populated from LLM sections) ---------------
        state.final_output = sections or {}
        gen_dur = int((time.monotonic() - ver_start) * 1000)

        logger.info(
            "Generation complete (sections: %s, %dms — from grounded answer)",
            list(state.final_output.keys()),
            gen_dur,
        )

        yield _sse_event(
            stage="generation",
            status="complete",
            payload=_stage_payload(
                state,
                stage_name="generation",
                duration_ms=gen_dur,
            ),
        )
        return

    # ── Legacy: separate LLM calls path (COMBINE_FINAL_STAGES=False) ───
    # Stage 5 — Construction
    logger.info("  → launching construction (separate LLM call)")
    c_start = time.monotonic()
    await _stage_construction(state)
    c_dur = int((time.monotonic() - c_start) * 1000)
    yield _sse_event(
        stage="construction",
        status="complete",
        payload=_stage_payload(
            state,
            stage_name="construction",
            duration_ms=c_dur,
        ),
    )

    # Stage 6 — Verification
    logger.info("  → launching verification (separate LLM call)")
    v_start = time.monotonic()
    await _stage_verification(state)
    v_dur = int((time.monotonic() - v_start) * 1000)
    yield _sse_event(
        stage="verification",
        status="complete",
        payload=_stage_payload(
            state,
            stage_name="verification",
            duration_ms=v_dur,
        ),
    )

    # Stage 7 — Generation
    logger.info("  → launching generation (separate LLM call)")
    g_start = time.monotonic()
    await _stage_generation(state)
    g_dur = int((time.monotonic() - g_start) * 1000)
    yield _sse_event(
        stage="generation",
        status="complete",
        payload=_stage_payload(
            state,
            stage_name="generation",
            duration_ms=g_dur,
        ),
    )
    logger.info(
        "Final stages complete (legacy): construction=%dms, verification=%dms, " "generation=%dms",
        c_dur,
        v_dur,
        g_dur,
    )


async def _stage_retrieval(state: PipelineState) -> None:
    """Stage 4 — pgvector similarity search with diversity filter.

    Uses combined mode (one embedding for issues+questions+text) when
    ``settings.RETRIEVAL_MODE == "combined"``, falling back to
    per-question embeddings otherwise.

    Multi-area: when ``state.legal_areas`` is non-empty, retrieval is
    run once per area and the results merged + de-duplicated. The
    per-area splits are also kept in ``state.per_area_chunks`` for
    logging/debugging.
    """
    from app.services.retrieval import (
        retrieve_chunks,
        retrieve_chunks_combined,
        retrieve_chunks_for_areas,
    )

    if state.legal_areas:
        state.per_area_chunks, state.retrieved_chunks = await retrieve_chunks_for_areas(
            state.legal_areas,
            state.issues,
            state.questions,
            state.normalized_text,
        )
        logger.info(
            "Per-area retrieval complete (areas=%s, %d unique chunks)",
            state.legal_areas,
            len(state.retrieved_chunks),
        )
        return

    if cfg._get_settings().RETRIEVAL_MODE == "combined":
        state.retrieved_chunks = await retrieve_chunks_combined(
            state.issues,
            state.questions,
            state.normalized_text,
        )
    else:
        state.retrieved_chunks = await retrieve_chunks(state.questions)

    logger.info("Retrieval complete (%d chunks)", len(state.retrieved_chunks))


async def _stage_construction(state: PipelineState) -> None:
    """Stage 5 — build claims with confidence scores and types."""
    from app.services.prompts import get_prompts
    from app.services.reasoning import construct_claims

    system_prompt = get_prompts(state.legal_areas)["claim_construction"]

    # WP-24: inject regime awareness banner.
    if state.legal_regime_banner:
        system_prompt = f"{state.legal_regime_banner}\n\n{system_prompt}"

    state.claims = await construct_claims(
        state.retrieved_chunks,
        state.questions,
        system_prompt=system_prompt,
    )
    logger.info("Construction complete (%d claims)", len(state.claims))


async def _stage_verification(state: PipelineState) -> None:
    """Stage 6 — cross-reference claims against source text."""
    from app.services.prompts import get_prompts
    from app.services.reasoning import verify_claims

    system_prompt = get_prompts(state.legal_areas)["verification"]
    state.verified_claims = await verify_claims(
        state.claims,
        state.retrieved_chunks,
        system_prompt=system_prompt,
    )
    logger.info("Verification complete (%d verified claims)", len(state.verified_claims))


async def _stage_adversarial_review(state: PipelineState) -> None:
    """Stage 7 — adversarial legal review from multiple perspectives.

    Runs the "Rechtsprüfungsrat" (legal review council) that evaluates
    every claim from defense, authority, and judicial perspectives.
    Also performs procedural review and risk assessment.

    Gracefully skips if the LLM call fails so the pipeline can continue.
    """
    from app.services.prompts import get_prompts
    from app.services.reasoning import adversarial_review

    # Use verified claims if available, otherwise raw claims.
    claims_to_review = state.verified_claims if state.verified_claims else state.claims
    if not claims_to_review:
        logger.warning("adversarial_review: no claims to review, skipping")
        state.adversarial_review = {
            "reviews": [],
            "overall_assessment": {
                "summary": "Keine Claims zur Prüfung vorhanden.",
                "key_risks": [],
                "recommended_next_steps": [],
                "confidence_in_defense": 0.0,
                "procedural_errors_found": [],
            },
        }
        return

    system_prompt = get_prompts(state.legal_areas)["adversarial_review"]
    try:
        result = await adversarial_review(
            normalized_text=state.normalized_text,
            issues=state.issues,
            questions=state.questions,
            claims=claims_to_review,
            chunks=state.retrieved_chunks,
            system_prompt=system_prompt,
        )
        state.adversarial_review = result

        # Inject adversarial findings into final_output for the UI.
        state.final_output["adversarial_pruefung"] = json.dumps(
            result, ensure_ascii=False, indent=2
        )

        logger.info(
            "Adversarial review complete (%d reviews)",
            len(result.get("reviews", [])),
        )
    except Exception as exc:
        logger.exception("Adversarial review failed — skipping gracefully: %s", exc)
        state.errors.append(f"adversarial_review: {exc}")
        state.adversarial_review = {
            "reviews": [],
            "overall_assessment": {
                "summary": "Adversariale Prüfung fehlgeschlagen.",
                "key_risks": [],
                "recommended_next_steps": [
                    "Bitte besprechen Sie die rechtlichen Risiken direkt mit Ihrem Anwalt."
                ],
                "confidence_in_defense": 0.5,
                "procedural_errors_found": [],
            },
        }
        state.final_output["adversarial_pruefung"] = (
            "Adversariale Prüfung nicht verfügbar (LLM-Fehler). "
            "Bitte konsultieren Sie einen Rechtsanwalt."
        )


async def _stage_generation(state: PipelineState) -> None:
    """Stage 8 — format into mandatory 7-part structure."""
    from app.services.prompts import get_prompts
    from app.services.reasoning import generate_output

    system_prompt = get_prompts(state.legal_areas)["output"]

    # WP-24: inject regime awareness banner.
    if state.legal_regime_banner:
        system_prompt = f"{state.legal_regime_banner}\n\n{system_prompt}"

    state.final_output = await generate_output(
        state.verified_claims,
        system_prompt=system_prompt,
    )
    logger.info("Generation complete (sections: %s)", list(state.final_output.keys()))


async def _stage_calculation_check(state: PipelineState) -> None:
    """Stage 9 — verify all monetary calculations in the document against SGB II rules.

    Uses a specialised calculation-checking model to extract and verify every
    monetary computation (freibeträge, aufrechnungen, etc.) in the document.
    The result is injected into ``state.final_output`` under the
    ``berechnungspruefung`` key so the frontend can display it alongside the
    other output sections.

    Gracefully skips if the LLM call fails so the pipeline can continue.
    """
    from app.services.calculation import check_calculations

    # Build claims and sections for context.
    claims_for_check = state.verified_claims or state.claims or None
    sections_for_check = state.final_output if state.final_output else None

    try:
        result = await check_calculations(
            state.normalized_text,
            claims=claims_for_check,
            sections=sections_for_check,
        )
        state.calculation_result = result

        # Inject calculation findings into final_output for the UI.
        state.final_output["berechnungspruefung"] = json.dumps(result, ensure_ascii=False, indent=2)

        discrepancies = result.get("overall_assessment", {}).get("total_discrepancies", 0)
        logger.info(
            "Calculation check complete (%d calculations, %d discrepancies)",
            len(result.get("calculations_found", [])),
            discrepancies,
        )
    except Exception as exc:
        logger.warning("Calculation check failed — skipping gracefully: %s", exc)
        state.errors.append(f"calculation_check: {exc}")
        state.calculation_result = {
            "calculations_found": [],
            "overall_assessment": {
                "total_discrepancies": 0,
                "total_amount_eur": 0.0,
                "direction": "keine",
                "summary": "Berechnungsprüfung nicht verfügbar (LLM-Fehler).",
                "recommended_action": "",
            },
        }
        state.final_output["berechnungspruefung"] = (
            "Berechnungsprüfung nicht verfügbar (LLM-Fehler). "
            "Bitte überprüfen Sie die Berechnungen eigenständig."
        )


# Map stage name → stage async function.
_STAGE_MAP: dict[str, Callable[[PipelineState], Awaitable[None]]] = {
    "normalization": _stage_normalization,
    "classification": _stage_classification,
    "decomposition": _stage_decomposition,
    "retrieval": _stage_retrieval,
    "construction": _stage_construction,
    "verification": _stage_verification,
    "adversarial_review": _stage_adversarial_review,
    "calculation_check": _stage_calculation_check,
    "generation": _stage_generation,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def execute_stage(
    stage_name: str,
    state: PipelineState,
) -> AsyncGenerator[str, None]:
    """Execute a single pipeline stage and yield the SSE event result."""
    if stage_name not in _STAGE_MAP:
        raise StageExecutionError(f"Unknown stage: {stage_name!r}")

    logger.info("  → entering stage: %s", stage_name)
    start = time.monotonic()
    try:
        await _STAGE_MAP[stage_name](state)
    except ImportError as exc:
        logger.warning(
            "Stage %s skipped — dependency not yet available: %s",
            stage_name,
            exc,
        )
        state.errors.append(f"{stage_name}: {exc}")
        raise StageExecutionError(
            f"Stage {stage_name!r} failed — dependency not available: {exc}"
        ) from exc
    except StageExecutionError:
        raise
    except Exception as exc:
        logger.exception("Stage %s failed: %s", stage_name, exc)
        state.errors.append(f"{stage_name}: {exc}")
        raise StageExecutionError(f"Stage {stage_name!r} failed: {exc}") from exc

    duration_ms = int((time.monotonic() - start) * 1000)
    logger.info("  ← stage %s finished in %dms", stage_name, duration_ms)
    yield _sse_event(
        stage=stage_name,
        status="complete",
        payload=_stage_payload(
            state,
            stage_name=stage_name,
            duration_ms=duration_ms,
        ),
    )


async def _pipeline_all(state: PipelineState) -> AsyncGenerator[str, None]:
    """Internal helper that iterates over all stages and collects SSE events."""
    for stage_name in _STAGES:
        async for event in execute_stage(stage_name, state):
            yield event


async def _collect_single_stage(
    stage_name: str,
    state: PipelineState,
) -> list[str]:
    """Execute a single stage and collect its SSE events into a list."""
    events: list[str] = []
    async for event in execute_stage(stage_name, state):
        events.append(event)
    return events


async def _collect_async_gen(
    gen: AsyncGenerator[str, None],
) -> list[str]:
    """Collect all items from an async generator into a list."""
    items: list[str] = []
    async for item in gen:
        items.append(item)
    return items


async def run_pipeline(state: PipelineState) -> AsyncGenerator[str, None]:
    """Execute the full 8-stage reasoning pipeline with timeout enforcement.

    Yields SSE-formatted progress events after each stage.
    If the retrieval stage returns no chunks, the pipeline stops early
    with a safe output instead of producing hallucinated legal advice.

    Parameters
    ----------
    state :
        Initialised ``PipelineState`` with ``input_text`` populated.

    Yields
    ------
    str
        SSE data lines in the format::

            data: {"stage": "...", "status": "complete", "payload": {...}}\n\n

    Raises
    ------
    PipelineTimeoutError :
        If execution exceeds ``settings.PIPELINE_TIMEOUT_SEC``.
    StageExecutionError :
        If any stage fails irrecoverably.
    """
    timeout_sec = cfg._get_settings().PIPELINE_TIMEOUT_SEC
    logger.info("Starting pipeline (timeout=%ds)", timeout_sec)

    # -----------------------------------------------------------------------
    # WP-42: OCR quality gate — assess before any LLM call
    # -----------------------------------------------------------------------
    if cfg._get_settings().OCR_QUALITY_ENABLED:
        from app.services.ocr_quality import assess_ocr_quality

        ocr_report = assess_ocr_quality(state.input_text)
        # Store report as dict for frontend consumption
        state.ocr_quality_report = {
            "score": ocr_report.score,
            "level": ocr_report.level,
            "issues": ocr_report.issues,
            "warnings": ocr_report.warnings,
            "ocr_artifacts_detected": ocr_report.ocr_artifacts_detected,
            "readable_words_pct": ocr_report.readable_words_pct,
            "language_detected": ocr_report.language_detected,
            "recommendations": ocr_report.recommendations,
        }

        min_score = cfg._get_settings().OCR_QUALITY_MIN_SCORE
        warn_score = cfg._get_settings().OCR_QUALITY_WARN_SCORE

        if ocr_report.score < min_score:
            logger.warning(
                "OCR quality gate: score=%.4f < min_score=%.2f — blocking pipeline",
                ocr_report.score,
                min_score,
            )
            raise OcrQualityError(
                f"OCR-Qualität unzureichend (Score: {ocr_report.score:.1%}, "
                f"erforderlich: >{min_score:.0%}). "
                f"{' '.join(ocr_report.recommendations)}"
            )

        if ocr_report.score < warn_score:
            logger.warning(
                "OCR quality gate: score=%.4f < warn_score=%.2f — emitting warning",
                ocr_report.score,
                warn_score,
            )
            yield _sse_event(
                stage="ocr_quality",
                status="warning",
                payload={
                    "score": ocr_report.score,
                    "level": ocr_report.level,
                    "issues": ocr_report.issues,
                    "warnings": ocr_report.warnings,
                    "ocr_artifacts_detected": ocr_report.ocr_artifacts_detected,
                    "readable_words_pct": ocr_report.readable_words_pct,
                    "language_detected": ocr_report.language_detected,
                    "recommendations": ocr_report.recommendations,
                },
            )
        elif ocr_report.level == "acceptable":
            yield _sse_event(
                stage="ocr_quality",
                status="info",
                payload={
                    "score": ocr_report.score,
                    "level": ocr_report.level,
                    "issues": ocr_report.issues,
                    "warnings": ocr_report.warnings,
                },
            )
        else:
            # "good" — silent pass-through
            logger.info(
                "OCR quality gate: score=%.4f level=%s — proceeding silently",
                ocr_report.score,
                ocr_report.level,
            )

    # -----------------------------------------------------------------------
    # WP-30: Pseudonymization gate — replace PII before any LLM call
    # -----------------------------------------------------------------------
    if cfg._get_settings().PSEUDONYMIZATION_ENABLED:
        from app.services.pseudonymization import pseudonymize

        pseudonymized_text, mapping = pseudonymize(state.input_text, None)
        state.input_text = pseudonymized_text
        state.pii_mapping = mapping.to_dict()
        logger.info(
            "Pseudonymization gate applied: %d persons, %d addresses, " "%d companies, %d IDs",
            mapping.person_counter,
            mapping.address_counter,
            mapping.company_counter,
            mapping.id_counter,
        )

    # -----------------------------------------------------------------------
    # Corpus health check (before pipeline begins)
    # -----------------------------------------------------------------------
    total_chunks = 0
    try:
        async for session in get_async_session():
            total_chunks = await session.scalar(select(func.count(LegalChunk.id))) or 0
            await session.close()
            break
    except Exception as exc:
        logger.warning("Corpus health check fehlgeschlagen: %s", exc)

    if total_chunks == 0:
        warn_msg = (
            "Der Corpus enthält keine Rechtsquellen. "
            "Bitte führen Sie eine Corpus-Aktualisierung durch: POST /api/v1/corpus/update"
        )
        logger.warning(warn_msg)
        yield _sse_event(
            stage="corpus_health",
            status="warning",
            payload={
                "total_chunks": 0,
                "total_sources": 0,
                "message": warn_msg,
                "warnings": [warn_msg],
            },
        )
    elif total_chunks < 100:
        warn_msg = (
            f"Der Corpus enthält nur {total_chunks} Textblöcke – "
            "für eine zuverlässige Analyse werden mehr Rechtsquellen empfohlen."
        )
        logger.warning(warn_msg)
        yield _sse_event(
            stage="corpus_health",
            status="warning",
            payload={
                "total_chunks": total_chunks,
                "message": warn_msg,
                "warnings": [warn_msg],
            },
        )
    else:
        yield _sse_event(
            stage="corpus_health",
            status="ok",
            payload={
                "total_chunks": total_chunks,
                "message": f"Corpus enthält {total_chunks} Textblöcke.",
                "warnings": [],
            },
        )

    started = time.monotonic()
    stage_timings: dict[str, float] = {}  # collect per-stage elapsed seconds for summary

    # WP-003: classification + decomposition run concurrently.
    # WP-007: construction + verification + generation run as one combined call.
    # When the loop hits "classification" or "construction", execute the
    # combined handler and skip the child stages.
    _skip_stages: set[str] = set()

    for stage_name in _STAGES:
        if stage_name in _skip_stages:
            continue

        # Check remaining time budget
        elapsed = time.monotonic() - started
        remaining = timeout_sec - elapsed
        logger.info(
            "▶ Stage %-14s | elapsed=%5.1fs | remaining=%5.1fs | budget=%ds",
            stage_name,
            elapsed,
            remaining,
            timeout_sec,
        )
        if remaining <= 0:
            raise PipelineTimeoutError(f"Pipeline execution exceeded {timeout_sec}s timeout")

        # --- WP-003: parallelise classification + decomposition -----------------
        if stage_name == "classification":
            stage_start = time.monotonic()
            try:
                events = await asyncio.wait_for(
                    _collect_async_gen(_run_classification_and_decomposition_stages(state)),
                    timeout=max(remaining, 10.0),
                )
            except TimeoutError:
                logger.error(
                    "✗ Stage classification+decomposition TIMED OUT after %.1fs "
                    "(budget %.1fs remaining)",
                    time.monotonic() - stage_start,
                    remaining,
                )
                raise PipelineTimeoutError(
                    f"Pipeline execution exceeded {timeout_sec}s timeout"
                ) from None

            stage_dur = time.monotonic() - stage_start
            stage_timings["classification+decomposition"] = stage_dur
            logger.info(
                "✓ classification+decomposition completed in %.2fs (parallel)",
                stage_dur,
            )

            for event in events:
                yield event

            _skip_stages.add("decomposition")
            continue
        # ------------------------------------------------------------------------

        # --- WP-007: combined final stages (construction + verification + generation) ---
        if stage_name == "construction":
            stage_start = time.monotonic()
            try:
                events = await asyncio.wait_for(
                    _collect_async_gen(_run_final_stages(state)),
                    timeout=max(remaining, 10.0),
                )
            except TimeoutError:
                logger.error(
                    "✗ Stage construction+verification+generation TIMED OUT after %.1fs "
                    "(budget %.1fs remaining)",
                    time.monotonic() - stage_start,
                    remaining,
                )
                raise PipelineTimeoutError(
                    f"Pipeline execution exceeded {timeout_sec}s timeout"
                ) from None

            stage_dur = time.monotonic() - stage_start
            stage_timings["construction+verification+generation"] = stage_dur
            logger.info(
                "✓ construction+verification+generation completed in %.2fs",
                stage_dur,
            )

            for event in events:
                yield event

            _skip_stages.add("verification")
            _skip_stages.add("generation")
            continue
        # ------------------------------------------------------------------------

        stage_start = time.monotonic()
        try:
            events = await asyncio.wait_for(
                _collect_single_stage(stage_name, state),
                timeout=max(remaining, 5.0),
            )
        except TimeoutError:
            logger.error(
                "✗ Stage %-14s TIMED OUT after %.1fs (budget %.1fs remaining)",
                stage_name,
                time.monotonic() - stage_start,
                remaining,
            )
            raise PipelineTimeoutError(
                f"Pipeline execution exceeded {timeout_sec}s timeout"
            ) from None

        stage_dur = time.monotonic() - stage_start
        stage_timings[stage_name] = stage_dur
        logger.info(
            "✓ Stage %-14s completed in %.2fs",
            stage_name,
            stage_dur,
        )

        for event in events:
            yield event

        # No-evidence guard: if retrieval returned nothing, stop safely
        if stage_name == "retrieval" and not state.retrieved_chunks:
            settings = cfg._get_settings()
            threshold = settings.MAX_COSINE_DISTANCE
            keyword_fallback = settings.RETRIEVAL_KEYWORD_FALLBACK
            fallback_note = (
                "Stichwort-Fallback wurde versucht, aber es wurden keine "
                "relevanten Ergebnisse gefunden."
                if keyword_fallback
                else "Stichwort-Fallback war deaktiviert."
            )
            logger.warning("No legal chunks retrieved — stopping pipeline with safe output")
            state.final_output = {
                "sachverhalt": state.normalized_text if state.normalized_text else "",
                "rechtliche_wuerdigung": (
                    "Keine belastbare rechtliche Würdigung möglich, "
                    "da keine passenden Rechtsquellen im lokalen Corpus gefunden wurden."
                ),
                "ergebnis": "Keine evidenzbasierte Einschätzung möglich.",
                "handlungsempfehlung": (
                    "Bitte stellen Sie sicher, dass der Corpus aktualisiert wurde "
                    "und relevante Rechtsquellen enthält."
                ),
                "entwurf": "",
                "unsicherheiten": (
                    f"Keine passenden Rechtsquellen im lokalen Corpus gefunden.\n"
                    f"  • Corpus-Umfang: {total_chunks} Textblöcke\n"
                    f"  • Schwellenwert (Cosine Distance): {threshold:.2f}\n"
                    f"  • {fallback_note}\n"
                    f"  • Eine Corpus-Aktualisierung über /api/v1/corpus/update wird empfohlen.\n"
                    f"  • Konfigurierte Quellen: {settings.CORPUS_SOURCES}"
                ),
            }
            break

    total_elapsed = time.monotonic() - started

    # Print a clear per-stage timing summary.
    logger.info("=" * 55)
    logger.info("PIPELINE TIMING SUMMARY")
    logger.info("=" * 55)
    # Print the parallel/combined entries if present.
    comb_dur = stage_timings.get("classification+decomposition")
    if comb_dur is not None:
        logger.info("  %-18s %8.2fs  (parallel)", "classification", comb_dur)
        logger.info("  %-18s %8s", "decomposition", "↑")

    final_comb_dur = stage_timings.get("construction+verification+generation")
    if final_comb_dur is not None:
        logger.info("  %-18s %8.2fs  (combined)", "construction", final_comb_dur)
        logger.info("  %-18s %8s", "verification", "↑")
        logger.info("  %-18s %8s", "generation", "↑")

    for stage_name in _STAGES:
        if stage_name in (
            "classification",
            "decomposition",
            "construction",
            "verification",
            "generation",
        ):
            continue  # already printed above
        dur = stage_timings.get(stage_name)
        if dur is not None:
            logger.info("  %-18s %8.2fs", stage_name, dur)
        else:
            logger.info("  %-18s %8s", stage_name, "(skipped)")
    logger.info("-" * 55)
    logger.info("  %-18s %8.2fs", "total", total_elapsed)
    total_staged = sum(stage_timings.values())
    if total_staged and total_staged > 0:
        logger.info(
            "  %-18s %8.2fs (%.1f%% of total)",
            "staged (sum)",
            total_staged,
            (total_staged / total_elapsed) * 100,
        )
    logger.info("=" * 55)

    # -------------------------------------------------------------------
    # WP-30: Depseudonymize final output — restore original PII for user
    # -------------------------------------------------------------------
    if state.pii_mapping is not None:
        from app.services.pseudonymization import (
            PiiMapping,
            depseudonymize_output,
        )

        mapping = PiiMapping.from_dict(state.pii_mapping)
        if mapping.placeholder_to_value:
            for section_key in list(state.final_output.keys()):
                value = state.final_output[section_key]
                if isinstance(value, str):
                    restored, warnings = depseudonymize_output(value, mapping)
                    state.final_output[section_key] = restored
                    state.pseudonymization_warnings.extend(f"{section_key}: {w}" for w in warnings)
            logger.info(
                "Depseudonymization complete with %d warning(s)",
                len(state.pseudonymization_warnings),
            )

    logger.info("Pipeline completed successfully.")
