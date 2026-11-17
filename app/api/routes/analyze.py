"""Analysis endpoint — full 8-stage pipeline with SSE streaming.

Provides a single endpoint:
    POST /api/v1/analyze — Execute the complete reasoning pipeline on
    provided legal text. Streams SSE events representing stage progress
    and finally yields the 7-part structured output.

Request body accepts either raw text or a reference to a previously
ingested document. The payload is a simple JSON object:
    {
        "text": "<normalized or raw text>",
        "legal_areas": ["<module id>"]  // optional, defaults to [] (DEFAULT_MODULE)
    }

When ``legal_areas`` is non-empty, the pipeline runs per-area
retrieval and uses area-specific prompts. The endpoint also accepts an
optional ``intake_session_id`` to link the resulting CaseRun back to
the IntakeSession that produced the legal_areas.

Each requested area key is validated against the module registry first
(WP-95, D-039): a key no installed module serves → HTTP 422
``MODULE_UNKNOWN``; a key whose module is installed but not enabled → HTTP
422 ``MODULE_NOT_ENABLED``. When ``legal_areas`` is non-empty the terminal
summary event carries ``resolved_modules`` (one entry per requested key).

A pre-flight check verifies that all selected legal_areas have a
populated corpus; if any are missing, the endpoint returns HTTP 409
with the list of missing source_types so the UI can show a targeted
"Quellen jetzt laden" modal.

The endpoint normalizes the input (Stage 1) and then streams one SSE
event per completed stage. After Stage 8 (generation), the stream ends
with a final event containing the 7-part JSON output and the
``case_run_id``.

Each SSE event follows the format::
    data: {"stage": "<name>", "status": "complete", "payload": {...}}\\n\\n
"""

# Semantic Version: 0.9.0 | 2026-11-17 — P12/WP-122: optional request key
# `plain_languages` → terminal event `plain` (absent: event unchanged).
# 0.8.0 | 2026-11-16 — P10: the stored calculation_check stage
# log also keeps the full calculation result (`result`) for the dossier; the
# SSE stream is unchanged.
# 0.7.0 | 2026-11-16 — WP-96: terminal-event provenance names
# the request's modules (citizen-provenance-v1.1).
# 0.6.0 | 2026-11-16 — WP-95: legal_areas validated against the
# registry (422 MODULE_UNKNOWN / MODULE_NOT_ENABLED); terminal event carries
# resolved_modules when legal_areas is non-empty; body accepts a JSON list for
# legal_areas (the documented shape — previously rejected by a dict[str, str]
# body annotation).
# 0.5.0 | 2026-11-16 — WP-94: case_run_area rows record module_id +
# module_version; unknown area keys are rejected by the writer (no DB CHECK).
# Previous: 0.4.1 | 2026-11-16 — WP-93: module-neutral docstring examples.
# 0.4.0 | 2026-08-25 — Art. 50(1)/(2) EU AI Act (D-032):
# the terminal summary event now embeds `disclosure` and `provenance`.

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
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.core.pipeline import PipelineState, run_pipeline
from app.db.models import (
    CaseRun,
    CaseRunArea,
    Claim,
    EvidenceBinding,
    IntakeSession,
    PipelineStageLog,
)
from app.db.session import async_session_factory
from app.modules.runtime import (
    MODULE_UNKNOWN,
    ModuleRequestError,
    area_module_binding,
    resolve_request_areas,
)
from app.plain.service import PlainLanguageRequestError, analysis_plain, parse_languages
from app.services.audit import AuditRecord, persist_audit_record
from app.services.corpus_readiness import check_preflight
from app.services.disclosure import build_disclosure_and_provenance
from app.utils.text import normalize_text


def module_request_http_error(exc: ModuleRequestError) -> HTTPException:
    """HTTP 422 for ``MODULE_UNKNOWN`` / ``MODULE_NOT_ENABLED`` (WP-95).

    Shared with the conversation messages endpoint (prompt set 3.0.0), so
    both report an invalid ``legal_areas`` value identically.
    """
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={
            "error": exc.code,
            "message": (
                "Mindestens ein ausgewähltes Rechtsgebiet ist nicht installiert."
                if exc.code == MODULE_UNKNOWN
                else "Mindestens ein ausgewähltes Rechtsgebiet ist in dieser "
                "Instanz nicht freigeschaltet."
            ),
            "legal_areas": exc.legal_areas,
            "action": "GET /api/v1/modules lists the installed and enabled modules",
        },
    )


# Strong references to scheduled audit-persist tasks (RUF006): the event
# loop may garbage-collect a task with no reference before it completes,
# silently losing the audit record.
_audit_tasks: set[asyncio.Task[None]] = set()


def _schedule_audit_persist(audit_record: AuditRecord) -> None:
    task = asyncio.create_task(_persist_audit_safely(audit_record))
    _audit_tasks.add(task)
    task.add_done_callback(_audit_tasks.discard)


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
async def analyze(payload: dict[str, Any] = Body(...)) -> StreamingResponse:  # noqa: B008
    """Execute the full 7-stage pipeline on *payload['text']*.

    Parameters
    ----------
    payload : dict[str, Any]
        JSON body::

            {
                "text": "<document text>",
                "legal_areas": ["<module id>", "<module id>"],
                "intake_session_id": "<uuid>",
            }

        ``legal_areas`` is optional (defaults to ``[]``) and triggers
        per-area retrieval and area-specific prompts. A comma-separated
        string is accepted as well.

    Returns
    -------
    StreamingResponse
        An SSE stream yielding one event per pipeline stage. Each event
        is a ``data: {...}\n\n`` line. The final event's ``payload``
        contains the key ``sections`` pointing to the 7-part output
        keys, a separate ``final_output`` field with the full result,
        and ``case_run_id`` for re-entry into Case Chat.

    Raises
    ------
    HTTPException(400)
        If the request body is missing the ``text`` field or it is empty.
    HTTPException(404)
        If the ``intake_session_id`` doesn't exist.
    HTTPException(422)
        ``MODULE_UNKNOWN`` / ``MODULE_NOT_ENABLED`` for a requested area
        key (structured ``detail`` lists the offending keys).
    HTTPException(409)
        Pre-flight check failed: one or more selected ``legal_areas``
        have no corpus chunks. The response body lists per-area missing
        sources so the UI can show a targeted "Quellen jetzt laden"
        modal.
    HTTPException(500)
        If the pipeline fails with an unrecoverable error.
    """
    raw_text = payload.get("text")
    if not raw_text or not isinstance(raw_text, str) or not raw_text.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Request body must contain a non-empty 'text' field.",
        )

    # Mild pre-normalization to clean obvious artefacts before state init.
    input_text = normalize_text(raw_text)
    session_id = str(uuid.uuid4())

    # Optional: legal_areas list + intake_session_id.
    legal_areas_raw: Any = payload.get("legal_areas") or []
    if isinstance(legal_areas_raw, str):
        legal_areas = [a.strip() for a in legal_areas_raw.split(",") if a.strip()]
    elif isinstance(legal_areas_raw, list):
        legal_areas = [str(a).strip() for a in legal_areas_raw if str(a).strip()]
    else:
        legal_areas = []
    # P12 (WP-122): opt-in plain-language finding in the terminal event. Absent
    # → the terminal event stays byte-identical (golden SSE transcript).
    plain_languages: list[str] | None = None
    if payload.get("plain_languages") not in (None, "", []):
        try:
            plain_languages = parse_languages(payload.get("plain_languages"))
        except PlainLanguageRequestError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "error": "PLAIN_LANGUAGE_INVALID",
                    "message": str(exc),
                    "values": exc.values,
                },
            ) from None
    intake_session_id_str = payload.get("intake_session_id")
    intake_session_uuid: uuid.UUID | None = None
    if intake_session_id_str:
        try:
            intake_session_uuid = uuid.UUID(str(intake_session_id_str))
        except (ValueError, TypeError):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="'intake_session_id' must be a valid UUID.",
            ) from None

    # Module gate (D-039): every requested key must resolve to an enabled
    # module (or the core procedural library) before anything else runs.
    resolved_modules: list[dict[str, Any]] = []
    if legal_areas:
        try:
            resolved_modules = [entry.as_dict() for entry in resolve_request_areas(legal_areas)]
        except ModuleRequestError as exc:
            raise module_request_http_error(exc) from None

    # Pre-flight corpus check.
    if legal_areas:
        async with async_session_factory() as pre_db:
            try:
                preflight = await check_preflight(pre_db, legal_areas)
            except SQLAlchemyError as exc:
                logger.warning("pre-flight DB error: %s", exc)
                preflight = {
                    "is_ready": True,
                    "areas": {},
                    "missing_source_types": [],
                    "ready_source_types": [],
                }
        if not preflight["is_ready"]:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error": "corpus_not_ready",
                    "message": (
                        "Mindestens ein ausgewähltes Rechtsgebiet hat keine "
                        "Rechtsquellen im Corpus. Bitte die fehlenden Quellen laden."
                    ),
                    "legal_areas": legal_areas,
                    "areas": preflight["areas"],
                    "missing_source_types": preflight["missing_source_types"],
                    "action": "POST /api/v1/corpus/update with the missing source_types",
                },
            )

    # Verify intake_session_id if provided.
    if intake_session_uuid is not None:
        async with async_session_factory() as db:
            stmt = select(IntakeSession).where(IntakeSession.id == intake_session_uuid)
            res = await db.execute(stmt)
            if res.scalar_one_or_none() is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"IntakeSession {intake_session_uuid} not found.",
                )

    # Initialize pipeline state.
    state = PipelineState(
        input_text=input_text,
        legal_areas=legal_areas,
        intake_session_id=str(intake_session_uuid) if intake_session_uuid else None,
    )

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

                    # Persist case_run_area rows for every selected legal area,
                    # with the module (and version) the case ran with (WP-94).
                    # An unknown area key raises here, as the former DB CHECK
                    # did at flush: the case is not persisted (D-057).
                    if state.legal_areas:
                        primary = state.legal_areas[0] if state.legal_areas else None
                        for area in state.legal_areas:
                            module_id, module_version = area_module_binding(area)
                            db.add(
                                CaseRunArea(
                                    case_run_id=case_run.id,
                                    legal_area=area,
                                    module_id=module_id,
                                    module_version=module_version,
                                    is_primary=(area == primary),
                                    intake_session_id=(
                                        uuid.UUID(state.intake_session_id)
                                        if state.intake_session_id
                                        else None
                                    ),
                                )
                            )

                    # Persist PipelineStageLog records.
                    for entry in stage_log_entries:
                        output_snapshot = entry.get("output_snapshot")
                        # P10: the SSE payload carries only counts; the dossier
                        # needs the calculators' line items, so the stored log
                        # (not the stream) keeps the result. legal_snapshot is
                        # already on case_run.
                        if (
                            entry["stage_name"] == "calculation_check"
                            and isinstance(output_snapshot, dict)
                            and state.calculation_result
                        ):
                            output_snapshot = {
                                **output_snapshot,
                                "result": {
                                    k: v
                                    for k, v in state.calculation_result.items()
                                    if k != "legal_snapshot"
                                },
                            }
                        stage_log = PipelineStageLog(
                            case_run_id=case_run.id,
                            stage_name=entry["stage_name"],
                            input_snapshot=entry.get("input_snapshot"),
                            output_snapshot=output_snapshot,
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
            final_payload: dict[str, Any] = {
                "session_id": session_id,
                "sections": list(state.final_output.keys()),
                "final_output": state.final_output,
            }
            if case_run_id:
                final_payload["case_run_id"] = case_run_id
            # WP-95: only when the request named areas, so requests without
            # legal_areas keep a byte-identical terminal event (WP-97 gate).
            if resolved_modules:
                final_payload["resolved_modules"] = resolved_modules
            # Art. 50(1)/(2) EU AI Act (D-032): the terminal event carries the
            # disclosure the consuming client must display to the person plus
            # the machine-readable provenance marker. Both are derived from
            # in-memory state; deliberately absent from error events (those
            # carry no AI-generated text).
            # Provenance v1.1 (WP-96) names the modules this request ran with.
            disclosure_info, provenance_marker = build_disclosure_and_provenance(
                settings, legal_areas
            )
            if plain_languages is not None:
                try:
                    final_payload["plain"] = analysis_plain(
                        state.final_output, legal_areas, plain_languages
                    )
                except Exception:
                    # Copy is static module data; a defect must not cost the
                    # person their analysis result.
                    logger.exception("plain-language rendering failed")
                    final_payload["plain"] = None
            final_payload["disclosure"] = disclosure_info.model_dump(mode="json")
            final_payload["provenance"] = provenance_marker.model_dump(mode="json")
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
            _schedule_audit_persist(failed_audit)
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
        _schedule_audit_persist(audit_record)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
        },
    )
