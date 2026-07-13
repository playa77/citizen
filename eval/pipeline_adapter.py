# Version: 1.0.0 | 2026-07-12
"""Adapter that runs the Citizen pipeline on a goldset case and extracts normalized output.

Usage:
    from eval.pipeline_adapter import run_pipeline_for_case, PipelineOutput

    output = await run_pipeline_for_case(case)
    print(output.issues, output.latency_ms)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from app.core.pipeline import PipelineState, PipelineTimeoutError, StageExecutionError, run_pipeline
from eval.goldset_loader import GoldsetCase

logger = logging.getLogger(__name__)


@dataclass
class PipelineOutput:
    """Normalized extraction from PipelineState after run_pipeline completes."""

    issues: list[str] = field(default_factory=list)
    questions: list[str] = field(default_factory=list)
    claims: list[dict[str, Any]] = field(default_factory=list)
    verified_claims: list[dict[str, Any]] = field(default_factory=list)
    final_output: dict[str, str] = field(default_factory=dict)
    calculation_result: dict[str, Any] = field(default_factory=dict)
    retrieved_chunks: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    latency_ms: int = 0


async def run_pipeline_for_case(case: GoldsetCase) -> PipelineOutput:
    """Run the pipeline on a goldset case and extract normalized output.

    Constructs ``PipelineState`` from ``case.input_document.text``, runs
    ``run_pipeline`` on it, drains the SSE generator, and returns a structured
    ``PipelineOutput`` with the mutated state fields.

    ``legal_areas`` is set to ``["sozialrecht"]`` per D-1 (the only supported
    legal area at this time).

    ``PipelineTimeoutError`` and ``StageExecutionError`` are caught gracefully
    — they populate ``state.errors`` and the partial output is returned so
    partial results can still be evaluated for debugging purposes.

    Parameters
    ----------
    case :
        A goldset case whose ``input_document.text`` will be used as pipeline
        input. The ``input_document.type`` field is not consumed by the
        pipeline adapter (the pipeline normalises internally).

    Returns
    -------
    PipelineOutput
        Extracted fields from the mutated pipeline state, with ``latency_ms``
        set to wall-clock elapsed time.
    """
    state = PipelineState(
        input_text=case.input_document.text,
        legal_areas=["sozialrecht"],
    )

    start = time.monotonic()
    try:
        async for _sse_event in run_pipeline(state):
            # Drain the SSE generator — we don't need individual events
            # in the adapter; the mutated state is what matters.
            pass
    except (PipelineTimeoutError, StageExecutionError) as exc:
        elapsed = int((time.monotonic() - start) * 1000)
        logger.warning(
            "Pipeline for case %s exited early after %dms: %s",
            case.id,
            elapsed,
            exc,
        )
        state.errors.append(str(exc))
    except Exception as exc:
        elapsed = int((time.monotonic() - start) * 1000)
        logger.exception(
            "Pipeline for case %s raised unexpected exception after %dms: %s",
            case.id,
            elapsed,
            exc,
        )
        state.errors.append(f"Unexpected error: {exc}")
    else:
        elapsed = int((time.monotonic() - start) * 1000)

    return PipelineOutput(
        issues=state.issues,
        questions=state.questions,
        claims=state.claims,
        verified_claims=state.verified_claims,
        final_output=state.final_output,
        calculation_result=state.calculation_result,
        retrieved_chunks=state.retrieved_chunks,
        errors=state.errors,
        latency_ms=elapsed,
    )
