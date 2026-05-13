"""Analysis endpoint — full 8-stage pipeline with SSE streaming.

Provides a single endpoint:
    POST /api/v1/analyze — Execute the complete reasoning pipeline on
    provided legal text. Streams SSE events representing stage progress
    and finally yields the 7-part structured output.

Request body accepts either raw text or a reference to a previously
ingested document. For WP-013, the payload is a simple JSON object:
    { "text": "<normalized or raw text>" }

The endpoint normalizes the input (Stage 1) and then streams one SSE
event per completed stage. After Stage 8 (generation), the stream ends
with a final event containing the 7-part JSON output.

Each SSE event follows the format::
    data: {"stage": "<name>", "status": "complete", "payload": {...}}\\n\\n
"""

# Semantic Version: 0.1.0

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import APIRouter, Body, HTTPException, status
from fastapi.responses import StreamingResponse

from app.core.pipeline import PipelineState, run_pipeline
from app.db.models import CaseRun, Claim, EvidenceBinding, PipelineStageLog
from app.db.session import async_session_factory
from app.services.audit import AuditRecord, persist_audit_record
from app.utils.text import normalize_text

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# SSE utilities
# ---------------------------------------------------------------------------


def _sse_format(data: dict[str, Any]) -> str:
    """Serialize *data* as an SSE data line."""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


# ---------------------------------------------------------------------------
# Background audit persistence
# ---------------------------------------------------------------------------


async def _persist_audit_safely(audit_record: AuditRecord) -> None:
    """Persist *audit_record* in a fresh DB session, swallowing all errors.

    This helper is designed to be scheduled with ``asyncio.create_task()``
    so that audit persistence never blocks the SSE response stream
    (WP-005).
    """
    try:
        async with async_session_factory() as db_session:
            await persist_audit_record(db_session, audit_record)
    except Exception:
        logger.exception(
            "Background audit persistence failed for session %s",
            audit_record.session_id,
        )


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post("/analyze")
async def analyze(payload: dict[str, str] = Body(...)) -> StreamingResponse:  # noqa: B008
    """Execute the full 7-stage pipeline on *payload['text']*.

    Parameters
    ----------
    payload : dict[str, str]
        JSON body: ``{ "text": "<document text>" }``

    Returns
    -------
    StreamingResponse
        An SSE stream yielding one event per pipeline stage. Each event
        is a ``data: {...}\n\n`` line. The final event's ``payload``
        contains the key ``sections`` pointing to the 6-part output keys
        and a separate ``final_output`` field with the full result.

    Raises
    ------
    HTTPException(400)
        If the request body is missing the ``text`` field or it is empty.
    HTTPException(500)
        If the pipeline fails with an unrecoverable error.
    """
    # Validate payload
    raw_text = payload.get("text")
    if not raw_text or not isinstance(raw_text, str) or not raw_text.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Request body must contain a non-empty 'text' field.",
        )

    # Mild pre-normalization to clean obvious artefacts before state init.
    input_text = normalize_text(raw_text)
    session_id = str(uuid.uuid4())

    # Initialize pipeline state.
    state = PipelineState(input_text=input_text)

    # Record start time for latency calculation.
    start = time.monotonic()

    # Define the async generator that SSE will stream.
    async def event_generator() -> AsyncGenerator[str, None]:
        """Yield SSE events from run_pipeline, then a final summary event."""
        stage_log_entries: list[dict[str, Any]] = []
        claim_entries: list[dict[str, Any]] = []
        evidence_entries: list[dict[str, Any]] = []

        try:
            # Stream all stage events from the pipeline.
            async for sse_event in run_pipeline(state):
                yield sse_event

                # Parse the SSE to collect stage log data for audit trail.
                if sse_event.startswith("data: "):
                    try:
                        payload_str = sse_event[6:].strip()
                        parsed = json.loads(payload_str)
                        if parsed.get("stage") and parsed.get("status") == "complete":
                            stage_log_entries.append(
                                {
                                    "stage_name": parsed["stage"],
                                    "input_snapshot": None,
                                    "output_snapshot": parsed.get("payload"),
                                    "duration_ms": parsed.get("payload", {}).get("duration_ms", 0),
                                    "error_trace": None,
                                }
                            )
                            # Collect claims and evidence from
                            # construction/verification/adversarial_review.
                            if parsed["stage"] == "construction":
                                claims_payload = parsed.get("payload", {}).get("claims", [])
                                for idx, c in enumerate(claims_payload):
                                    claim_entries.append({**c, "_index": idx})
                            if parsed["stage"] == "verification":
                                for idx, vc in enumerate(
                                    parsed.get("payload", {}).get("verified_claims", [])
                                ):
                                    # Only create evidence bindings when the claim
                                    # explicitly references a chunk_id.
                                    ref_chunk_id = vc.get("evidence_chunk_id")
                                    evidence_entries.append(
                                        {
                                            "claim_index": idx,
                                            "binding_strength": float(
                                                vc.get("confidence_score", 0.5)
                                            ),
                                            "quote_excerpt": str(
                                                vc.get("evidence_quote", "")[:500]
                                            ),
                                            "chunk_hierarchy": str(
                                                vc.get("evidence_hierarchy", "")
                                            ),
                                            "chunk_id": str(ref_chunk_id) if ref_chunk_id else "",
                                        }
                                    )
                            if parsed["stage"] == "adversarial_review":
                                review_payload = parsed.get("payload", {})
                                evidence_entries.append(
                                    {
                                        "claim_index": -1,
                                        "binding_strength": review_payload.get(
                                            "overall_assessment", {}
                                        ).get("confidence_in_defense", 0.5),
                                        "quote_excerpt": str(
                                            review_payload.get("overall_assessment", {}).get(
                                                "summary", ""
                                            )[:500]
                                        ),
                                        "chunk_hierarchy": "adversarial_review",
                                        "chunk_id": "adversarial_review",
                                    }
                                )
                    except (json.JSONDecodeError, IndexError, KeyError):
                        pass

            # Capture legal_snapshot from calculation result for audit persistence.
            calc_result = state.calculation_result
            legal_snapshot = calc_result.get("legal_snapshot") if calc_result else None

            # Compute latency and persist CaseRun with pipeline results.
            latency_ms = int((time.monotonic() - start) * 1000)
            case_run_id: str | None = None
            try:
                async with async_session_factory() as db:
                    title = (input_text[:77] + "...") if len(input_text) > 80 else input_text[:80]
                    case_run = CaseRun(
                        session_id=session_id,
                        input_text=input_text,
                        status="completed",
                        latency_ms=latency_ms,
                        title=title,
                        legal_snapshot=legal_snapshot,
                        chat_history={},
                        user_edits={},
                    )
                    db.add(case_run)
                    await db.flush()

                    # Persist PipelineStageLog records.
                    for entry in stage_log_entries:
                        stage_log = PipelineStageLog(
                            case_run_id=case_run.id,
                            stage_name=entry["stage_name"],
                            input_snapshot=entry.get("input_snapshot"),
                            output_snapshot=entry.get("output_snapshot"),
                            duration_ms=entry.get("duration_ms", 0),
                            error_trace=entry.get("error_trace"),
                        )
                        db.add(stage_log)

                    # Persist Claim records and build index → id map.
                    claim_id_map: dict[int, Any] = {}
                    for entry in claim_entries:
                        claim = Claim(
                            case_run_id=case_run.id,
                            claim_text=entry.get("claim_text", ""),
                            confidence_score=entry.get("confidence_score", 0.0),
                            claim_type=entry.get("claim_type", "interpretation"),
                        )
                        db.add(claim)
                        await db.flush()
                        claim_id_map[entry["_index"]] = claim.id

                    # Persist EvidenceBinding records (skip entries with invalid chunk_id).
                    for entry in evidence_entries:
                        claim_index: int = entry.get("claim_index", -1)
                        claim_id = claim_id_map.get(claim_index)
                        if claim_id is None:
                            continue
                        chunk_id_str = entry.get("chunk_id", "")
                        try:
                            chunk_uuid = uuid.UUID(chunk_id_str) if chunk_id_str else None
                        except (ValueError, AttributeError):
                            chunk_uuid = None
                        if chunk_uuid is None:
                            continue
                        evidence_binding = EvidenceBinding(
                            claim_id=claim_id,
                            chunk_id=chunk_uuid,
                            binding_strength=entry.get("binding_strength", 0.5),
                            quote_excerpt=entry.get("quote_excerpt", ""),
                        )
                        db.add(evidence_binding)

                    await db.commit()
                    await db.refresh(case_run)
                    case_run_id = str(case_run.id)
            except Exception:
                logger.exception("Failed to persist CaseRun for session %s", session_id)

            # After pipeline completes, yield a final compact summary event.
            final_payload = {
                "session_id": session_id,
                "sections": list(state.final_output.keys()),
                "final_output": state.final_output,
            }
            if case_run_id:
                final_payload["case_run_id"] = case_run_id
            yield _sse_format(final_payload)

        except Exception as exc:
            logger.exception("Pipeline execution failed")
            # Emit a terminal error event so the client is not left hanging.
            error_payload = {
                "error": "pipeline_failed",
                "detail": str(exc),
                "session_id": session_id,
            }
            yield _sse_format(error_payload)

            # Schedule a failed-audit persistence in the background.
            latency_ms = int((time.monotonic() - start) * 1000)

            # Also persist a failed CaseRun so the session is recorded.
            try:
                async with async_session_factory() as db:
                    title = (input_text[:77] + "...") if len(input_text) > 80 else input_text[:80]
                    failed_case_run = CaseRun(
                        session_id=session_id,
                        input_text=input_text,
                        status="failed",
                        latency_ms=latency_ms,
                        title=title,
                        legal_snapshot=None,
                        chat_history={},
                        user_edits={},
                    )
                    db.add(failed_case_run)
                    await db.commit()
            except Exception:
                logger.exception("Failed to persist failed CaseRun for session %s", session_id)

            failed_audit = AuditRecord(
                session_id=session_id,
                input_text=input_text,
                status="failed",
                latency_ms=latency_ms,
                stage_logs=stage_log_entries,
                claims=[],
                evidence_bindings=[],
                disclaimer_ack={
                    "input_snapshot": {"session_id": session_id},
                    "output_snapshot": {"acknowledged": False},
                    "duration_ms": 0,
                },
                legal_snapshot=None,
            )
            asyncio.create_task(_persist_audit_safely(failed_audit))
            return

        # Schedule audit persistence in the background after streaming completes.
        disclaimer_ack_entry = {
            "input_snapshot": {"session_id": session_id},
            "output_snapshot": {"acknowledged": True},
            "duration_ms": 0,
        }
        audit_record = AuditRecord(
            session_id=session_id,
            input_text=input_text,
            status="completed",
            latency_ms=latency_ms,
            stage_logs=stage_log_entries,
            claims=claim_entries,
            evidence_bindings=evidence_entries,
            disclaimer_ack=disclaimer_ack_entry,
            legal_snapshot=legal_snapshot,
        )
        asyncio.create_task(_persist_audit_safely(audit_record))

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )
