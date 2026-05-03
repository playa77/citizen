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

import logging
import uuid
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import APIRouter, Body, HTTPException, status
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask

from app.core.pipeline import PipelineState, run_pipeline
from app.utils.text import normalize_text

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# SSE utilities
# ---------------------------------------------------------------------------


def _sse_format(data: dict[str, Any]) -> str:
    """Serialize *data* as an SSE data line."""
    import json

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

    # Create a background task to log the case_run row after streaming completes.
    # This is a placeholder — actual DB logging would occur in main.py middleware
    # or in the pipeline's own stage logging. For WP-013 we only need the route.
    async def _log_case_run() -> None:
        # Placeholder for audit-logging — kept intentionally minimal for WP-013.
        logger.info("Pipeline session completed: session_id=%s", session_id)

    # Define the async generator that SSE will stream.
    async def event_generator() -> AsyncGenerator[str, None]:
        """Yield SSE events from run_pipeline, then a final summary event."""
        try:
            # Stream all stage events from the pipeline.
            async for sse_event in run_pipeline(state):
                yield sse_event

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
            # End stream cleanly without re-raising to avoid ASGI TaskGroup errors.
            return

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
        background=BackgroundTask(_log_case_run),
    )
