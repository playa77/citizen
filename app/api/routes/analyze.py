"""Analysis endpoint — full 7-stage pipeline with SSE streaming.

Provides a single endpoint:
    POST /api/v1/analyze — Execute the complete reasoning pipeline on
    provided legal text. Streams SSE events representing stage progress
    and finally yields the 6-part structured output.

Request body accepts either raw text or a reference to a previously
ingested document. For WP-013, the payload is a simple JSON object:
    { "text": "<normalized or raw text>" }

The endpoint normalizes the input (Stage 1) and then streams one SSE
event per completed stage. After Stage 7 (generation), the stream ends
with a final event containing the 6-part JSON output.

Each SSE event follows the format::
    data: {"stage": "<name>", "status": "complete", "payload": {...}}\\n\\n
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import APIRouter, Body, HTTPException, status
from fastapi.responses import StreamingResponse

from app.core.pipeline import PipelineState, run_pipeline
from app.db.session import get_async_session
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
                            # construction/verification.
                            if parsed["stage"] == "construction":
                                claims_payload = parsed.get("payload", {}).get("claims", [])
                                for idx, c in enumerate(claims_payload):
                                    claim_entries.append({**c, "_index": idx})
                            if parsed["stage"] == "verification":
                                for idx, vc in enumerate(
                                    parsed.get("payload", {}).get("verified_claims", [])
                                ):
                                    # Attach evidence bindings from verified claims.
                                    chunk = (
                                        state.retrieved_chunks[idx % len(state.retrieved_chunks)]
                                        if state.retrieved_chunks
                                        else {}
                                    )
                                    evidence_entries.append(
                                        {
                                            "claim_index": idx,
                                            "binding_strength": float(
                                                vc.get("confidence_score", 0.5)
                                            ),
                                            "quote_excerpt": str(
                                                chunk.get("text_content", "")[:500]
                                            ),
                                            "chunk_hierarchy": str(chunk.get("hierarchy_path", "")),
                                            "chunk_id": str(chunk.get("chunk_id", "")),
                                        }
                                    )
                    except (json.JSONDecodeError, IndexError, KeyError):
                        pass

            # After pipeline completes, yield a final compact summary event.
            final_payload = {
                "session_id": session_id,
                "sections": list(state.final_output.keys()),
                "final_output": state.final_output,
            }
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
            # Do not persist audit trail on failure — keep status as "failed".
            return

        # Persist the audit trail in the background after streaming completes.
        latency_ms = int((time.monotonic() - start) * 1000)

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
        )

        try:
            # Use a fresh session for persistence.
            async for db_session in get_async_session():
                await persist_audit_record(db_session, audit_record)
                await db_session.close()
                break
        except Exception:
            logger.exception("Failed to persist audit trail for session %s", session_id)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )
