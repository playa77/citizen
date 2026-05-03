"""7-Stage reasoning pipeline orchestrator with SSE streaming and timeout enforcement.

Pipeline stages (sequential, non-parallel):
    1. Input Normalization
    2. Issue Classification
    3. Question Decomposition
    4. Evidence Retrieval
    5. Claim Construction
    6. Verification Pass
    7. Output Generation

Each stage yields an SSE-formatted event:
    ``data: {"stage": "...", "status": "complete", "payload": {...}}\\n\\n``

"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncGenerator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from app.core import config as cfg
from app.utils.text import normalize_text

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------


class PipelineTimeoutError(Exception):
    """Raised when the full pipeline execution exceeds the configured timeout."""


class StageExecutionError(Exception):
    """Raised when a single pipeline stage fails irrecoverably."""


# ---------------------------------------------------------------------------
# Pipeline state
# ---------------------------------------------------------------------------


@dataclass
class PipelineState:
    """Mutable state carried through all 7 pipeline stages.

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
    final_output :
        6-part formatted result dictionary (stage 7).
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
    final_output: dict[str, str] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


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
]

# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _sse_event(stage: str, status: str, payload: dict[str, Any]) -> str:
    """Format a dictionary as an SSE data line.

    Returns a string of the form::

        data: {"stage": "...", "status": "...", "payload": {...}}\\n\\n
    """
    data = {
        "stage": stage,
        "status": status,
        "payload": payload,
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
    from app.services.reasoning import classify_issues

    state.issues = await classify_issues(state.normalized_text)
    logger.info("Classification complete (%d issues)", len(state.issues))


async def _stage_decomposition(state: PipelineState) -> None:
    """Stage 3 — extract 3-5 explicit legal questions."""
    from app.services.reasoning import decompose_questions

    state.questions = await decompose_questions(state.normalized_text)
    logger.info("Decomposition complete (%d questions)", len(state.questions))


async def _stage_retrieval(state: PipelineState) -> None:
    """Stage 4 — pgvector similarity search with diversity filter."""
    from app.services.retrieval import retrieve_chunks

    state.retrieved_chunks = await retrieve_chunks(state.questions)
    logger.info("Retrieval complete (%d chunks)", len(state.retrieved_chunks))


async def _stage_construction(state: PipelineState) -> None:
    """Stage 5 — build claims with confidence scores and types."""
    from app.services.reasoning import construct_claims

    state.claims = await construct_claims(state.retrieved_chunks, state.questions)
    logger.info("Construction complete (%d claims)", len(state.claims))


async def _stage_verification(state: PipelineState) -> None:
    """Stage 6 — cross-reference claims against source text."""
    from app.services.reasoning import verify_claims

    state.verified_claims = await verify_claims(state.claims, state.retrieved_chunks)
    logger.info("Verification complete (%d verified claims)", len(state.verified_claims))


async def _stage_generation(state: PipelineState) -> None:
    """Stage 7 — format into mandatory 6-part structure."""
    from app.services.reasoning import generate_output

    state.final_output = await generate_output(state.verified_claims)
    logger.info("Generation complete (sections: %s)", list(state.final_output.keys()))


# Map stage name → stage async function.
_STAGE_MAP: dict[str, Callable[[PipelineState], Awaitable[None]]] = {
    "normalization": _stage_normalization,
    "classification": _stage_classification,
    "decomposition": _stage_decomposition,
    "retrieval": _stage_retrieval,
    "construction": _stage_construction,
    "verification": _stage_verification,
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


async def _collect_events(state: PipelineState) -> list[str]:
    """Materialise the full pipeline into a list of SSE event strings."""
    events: list[str] = []
    async for event in _pipeline_all(state):
        events.append(event)
    return events


async def run_pipeline(state: PipelineState) -> AsyncGenerator[str, None]:
    """Execute the full 7-stage reasoning pipeline with timeout enforcement.

    Yields SSE-formatted progress events after each stage.

    Parameters
    ----------
    state :
        Initialised ``PipelineState`` with ``input_text`` populated.

    Yields
    ------
    str
        SSE data lines in the format::

            data: {"stage": "...", "status": "complete", "payload": {...}}\\n\\n

    Raises
    ------
    PipelineTimeoutError :
        If execution exceeds ``settings.PIPELINE_TIMEOUT_SEC``.
    StageExecutionError :
        If any stage fails irrecoverably.
    """
    timeout_sec = cfg._get_settings().PIPELINE_TIMEOUT_SEC
    logger.info("Starting pipeline (timeout=%ds)", timeout_sec)

    try:
        events: list[str] = await asyncio.wait_for(
            _collect_events(state),
            timeout=timeout_sec,
        )
    except TimeoutError:
        logger.error("Pipeline timed out after %ds", timeout_sec)
        raise PipelineTimeoutError(f"Pipeline execution exceeded {timeout_sec}s timeout") from None

    for event in events:
        yield event

    logger.info("Pipeline completed successfully.")
