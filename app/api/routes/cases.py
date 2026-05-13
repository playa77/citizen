"""Case session endpoints — CRUD + chat + re-evaluation + export.

Endpoints:
    GET    /api/v1/cases                     List case sessions
    GET    /api/v1/cases/{case_id}           Get full case session detail
    DELETE /api/v1/cases/{case_id}           Delete a case session
    POST   /api/v1/cases/{case_id}/chat      SSE case chat
    POST   /api/v1/cases/{case_id}/reevaluate  SSE targeted re-analysis
    PATCH  /api/v1/cases/{case_id}/claims/{claim_id}  Edit a claim
    POST   /api/v1/cases/{case_id}/claims    Add a new claim
    POST   /api/v1/cases/{case_id}/adjudicate  Flag/confirm a claim or section
    GET    /api/v1/cases/{case_id}/export    Export case data
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import AsyncGenerator
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Body, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.models import CaseRun, Claim
from app.db.session import async_session_factory

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# SSE helper (mirrors conversations.py)
# ---------------------------------------------------------------------------


def _sse_format(data: dict[str, Any]) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


# ---------------------------------------------------------------------------
# GET /cases — list case sessions
# ---------------------------------------------------------------------------


@router.get("/cases")
async def list_cases_endpoint() -> list[dict[str, Any]]:
    """List completed case sessions, ordered by most recently updated."""
    async with async_session_factory() as db:
        stmt = (
            select(CaseRun)
            .where(CaseRun.status == "completed")
            .order_by(CaseRun.updated_at.desc())
            .limit(100)
        )
        result = await db.execute(stmt)
        cases = list(result.scalars().all())

    return [
        {
            "id": str(c.id),
            "session_id": c.session_id,
            "title": c.title,
            "status": c.status,
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "updated_at": c.updated_at.isoformat() if c.updated_at else None,
            "input_preview": (
                (c.input_text[:100] + "...")
                if c.input_text and len(c.input_text) > 100
                else c.input_text
            ),
        }
        for c in cases
    ]


# ---------------------------------------------------------------------------
# GET /cases/{case_id} — get full case session detail
# ---------------------------------------------------------------------------


@router.get("/cases/{case_id}")
async def get_case_endpoint(case_id: UUID) -> dict[str, Any]:
    """Return full case session including stages, claims, and evidence."""
    async with async_session_factory() as db:
        stmt = (
            select(CaseRun)
            .where(CaseRun.id == case_id)
            .options(
                selectinload(CaseRun.stage_logs),
                selectinload(CaseRun.claims).selectinload(Claim.evidence_bindings),
            )
        )
        result = await db.execute(stmt)
        case = result.scalar_one_or_none()

    if case is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")

    # Reconstruct final_output from stage logs.
    final_output: dict[str, str] = {}
    if case.stage_logs:
        # Collect output from generation, adversarial_review, and calculation_check.
        for sl in case.stage_logs:
            if sl.stage_name == "generation" and isinstance(sl.output_snapshot, dict):
                final_output.update(sl.output_snapshot)
            elif sl.stage_name == "adversarial_review" and isinstance(sl.output_snapshot, dict):
                for k, v in sl.output_snapshot.items():
                    final_output[f"adversarial_{k}"] = v
            elif sl.stage_name == "calculation_check" and isinstance(sl.output_snapshot, dict):
                for k, v in sl.output_snapshot.items():
                    final_output[f"calculation_{k}"] = v

    # Serialize stages.
    stages = [
        {
            "id": str(sl.id),
            "stage_name": sl.stage_name,
            "input_snapshot": sl.input_snapshot,
            "output_snapshot": sl.output_snapshot,
            "duration_ms": sl.duration_ms,
            "error_trace": sl.error_trace,
            "created_at": sl.created_at.isoformat() if sl.created_at else None,
        }
        for sl in (case.stage_logs or [])
    ]

    # Serialize claims with evidence bindings.
    claims = []
    for cl in case.claims or []:
        cl_data = {
            "id": str(cl.id),
            "case_run_id": str(cl.case_run_id),
            "claim_text": cl.claim_text,
            "confidence_score": cl.confidence_score,
            "claim_type": cl.claim_type,
            "user_adjudication": cl.user_adjudication,
            "created_at": cl.created_at.isoformat() if cl.created_at else None,
            "evidence_bindings": [],
        }
        for eb in cl.evidence_bindings or []:
            cl_data["evidence_bindings"].append(
                {
                    "id": str(eb.id),
                    "claim_id": str(eb.claim_id),
                    "chunk_id": str(eb.chunk_id),
                    "binding_strength": eb.binding_strength,
                    "quote_excerpt": eb.quote_excerpt,
                    "created_at": eb.created_at.isoformat() if eb.created_at else None,
                }
            )
        claims.append(cl_data)

    return {
        "id": str(case.id),
        "session_id": case.session_id,
        "title": case.title,
        "status": case.status,
        "input_text": case.input_text,
        "created_at": case.created_at.isoformat() if case.created_at else None,
        "updated_at": case.updated_at.isoformat() if case.updated_at else None,
        "chat_history": case.chat_history,
        "user_edits": case.user_edits,
        "final_output": final_output,
        "stages": stages,
        "claims": claims,
    }


# ---------------------------------------------------------------------------
# DELETE /cases/{case_id} — delete case session (cascade deletes)
# ---------------------------------------------------------------------------


@router.delete("/cases/{case_id}")
async def delete_case_endpoint(case_id: UUID) -> dict[str, str]:
    """Delete a case session and all related data (cascade)."""
    async with async_session_factory() as db:
        stmt = select(CaseRun).where(CaseRun.id == case_id)
        result = await db.execute(stmt)
        case = result.scalar_one_or_none()
        if case is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
        await db.delete(case)
        await db.commit()

    return {"status": "deleted", "id": str(case_id)}


# ---------------------------------------------------------------------------
# POST /cases/{case_id}/chat — SSE case chat
# ---------------------------------------------------------------------------


@router.post("/cases/{case_id}/chat")
async def case_chat_endpoint(
    case_id: UUID,
    payload: dict[str, str] = Body(...),  # noqa: B008
) -> StreamingResponse:
    """Chat with a case session via SSE streaming response.

    Request body: ``{"content": "user message"}``
    """
    content = payload.get("content", "")
    if not content or not content.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Message content must be non-empty.",
        )

    async with async_session_factory() as db:
        stmt = (
            select(CaseRun)
            .where(CaseRun.id == case_id)
            .options(
                selectinload(CaseRun.stage_logs),
                selectinload(CaseRun.claims),
            )
        )
        result = await db.execute(stmt)
        case = result.scalar_one_or_none()
        if case is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")

        # Reconstruct pipeline_output from stage logs.
        pipeline_output: dict[str, str] = {}
        for sl in case.stage_logs or []:
            if sl.stage_name == "generation" and isinstance(sl.output_snapshot, dict):
                pipeline_output.update(sl.output_snapshot)
            elif sl.stage_name == "adversarial_review" and isinstance(sl.output_snapshot, dict):
                for k, v in sl.output_snapshot.items():
                    pipeline_output[f"adversarial_{k}"] = v
            elif sl.stage_name == "calculation_check" and isinstance(sl.output_snapshot, dict):
                for k, v in sl.output_snapshot.items():
                    pipeline_output[f"calculation_{k}"] = v

        # Load chat_history and user_edits.
        chat_history = case.chat_history or {"messages": []}
        user_edits = case.user_edits or {}

        # Load claims with adjudications.
        claims_data = [
            {
                "id": str(cl.id),
                "claim_text": cl.claim_text,
                "confidence_score": cl.confidence_score,
                "claim_type": cl.claim_type,
                "user_adjudication": cl.user_adjudication,
            }
            for cl in (case.claims or [])
        ]

        # Build messages history from chat_history for the LLM context.
        messages_history: list[dict[str, str]] = []
        for msg in chat_history.get("messages", []):
            messages_history.append({"role": msg["role"], "content": msg.get("content", "")})

        # Build adjudications dict from claims and section adjudications.
        adjudications: dict[str, Any] = {}
        for cl in (case.claims or []):
            if cl.user_adjudication:
                adjudications[str(cl.id)] = cl.user_adjudication
        section_adjs = user_edits.get("section_adjudications", {})
        for section_key, adj in section_adjs.items():
            adjudications[f"section:{section_key}"] = adj

        # Save the user message to chat_history.
        user_msg = {"role": "user", "content": content.strip(), "timestamp": time.time()}
        if "messages" not in chat_history:
            chat_history["messages"] = []
        chat_history["messages"].append(user_msg)
        case.chat_history = chat_history
        await db.commit()

    # ── Define SSE generator ──────────────────────────────────────────
    async def event_generator() -> AsyncGenerator[str, None]:
        accumulated_response = ""

        try:
            from app.services.case_chat import generate_case_chat_response

            async for event in generate_case_chat_response(
                messages=messages_history,
                pipeline_output=pipeline_output,
                user_edits=user_edits,
                adjudications=adjudications,
                claims=claims_data,
                case_id=str(case_id),
            ):
                yield event
                if event.startswith("data: "):
                    try:
                        parsed = json.loads(event[6:].strip())
                        if parsed.get("type") == "done":
                            accumulated_response = parsed.get("full_response", "")
                    except (json.JSONDecodeError, KeyError):
                        pass

            # Save assistant response to chat_history and update updated_at.
            if accumulated_response:
                async with async_session_factory() as inner_db:
                    inner_stmt = select(CaseRun).where(CaseRun.id == case_id)
                    inner_result = await inner_db.execute(inner_stmt)
                    inner_case = inner_result.scalar_one_or_none()
                    if inner_case:
                        inner_chat = inner_case.chat_history or {"messages": []}
                        if "messages" not in inner_chat:
                            inner_chat["messages"] = []
                        inner_chat["messages"].append(
                            {
                                "role": "assistant",
                                "content": accumulated_response,
                                "timestamp": time.time(),
                            }
                        )
                        inner_case.chat_history = inner_chat
                        await inner_db.commit()

        except ImportError:
            logger.exception("app.services.case_chat not available")
            yield _sse_format(
                {
                    "error": "service_unavailable",
                    "detail": "Case chat service is not yet implemented.",
                }
            )
        except Exception as exc:
            logger.exception("Case chat failed for case %s", case_id)
            error_payload = {
                "error": "case_chat_failed",
                "detail": str(exc),
                "case_id": str(case_id),
            }
            yield _sse_format(error_payload)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# POST /cases/{case_id}/reevaluate — SSE targeted re-analysis
# ---------------------------------------------------------------------------


@router.post("/cases/{case_id}/reevaluate")
async def reevaluate_case_endpoint(
    case_id: UUID,
    payload: dict[str, str] = Body(...),  # noqa: B008
) -> StreamingResponse:
    """Run a targeted re-analysis on a specific pipeline stage via SSE.

    Request body: ``{"stage": "calculation_check", "context": "...hint..."}``
    """
    stage = payload.get("stage", "")
    context = payload.get("context", "")

    if not stage:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="'stage' is required.",
        )

    async with async_session_factory() as db:
        stmt = (
            select(CaseRun).where(CaseRun.id == case_id).options(selectinload(CaseRun.stage_logs))
        )
        result = await db.execute(stmt)
        case = result.scalar_one_or_none()
        if case is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")

        # Reconstruct pipeline_state from stage logs.
        pipeline_state: dict[str, Any] = {
            "stages": {},
            "user_edits": case.user_edits or {},
        }
        for sl in case.stage_logs or []:
            pipeline_state["stages"][sl.stage_name] = {
                "id": str(sl.id),
                "input_snapshot": sl.input_snapshot,
                "output_snapshot": sl.output_snapshot,
                "duration_ms": sl.duration_ms,
                "error_trace": sl.error_trace,
            }

    # ── Define SSE generator ──────────────────────────────────────────
    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            from app.services.case_chat import run_targeted_reevaluate

            async for event in run_targeted_reevaluate(
                stage_name=stage,
                context=context,
                pipeline_state=pipeline_state,
                case_id=str(case_id),
            ):
                yield event

            # On done, update PipelineStageLog entries and user_edits.
            async with async_session_factory() as inner_db:
                inner_stmt = (
                    select(CaseRun)
                    .where(CaseRun.id == case_id)
                    .options(selectinload(CaseRun.stage_logs))
                )
                inner_result = await inner_db.execute(inner_stmt)
                inner_case = inner_result.scalar_one_or_none()
                if inner_case:
                    # Update user_edits to record that this re-evaluation occurred.
                    edits = inner_case.user_edits or {}
                    if "reevaluations" not in edits:
                        edits["reevaluations"] = []
                    edits["reevaluations"].append(
                        {
                            "stage": stage,
                            "context": context,
                            "timestamp": time.time(),
                        }
                    )
                    inner_case.user_edits = edits
                    await inner_db.commit()

        except ImportError:
            logger.exception("app.services.case_chat not available")
            yield _sse_format(
                {
                    "error": "service_unavailable",
                    "detail": "Case chat service is not yet implemented.",
                }
            )
        except Exception as exc:
            logger.exception("Re-evaluation failed for case %s stage %s", case_id, stage)
            error_payload = {
                "error": "reevaluation_failed",
                "detail": str(exc),
                "case_id": str(case_id),
                "stage": stage,
            }
            yield _sse_format(error_payload)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# PATCH /cases/{case_id}/claims/{claim_id} — edit a claim
# ---------------------------------------------------------------------------


@router.patch("/cases/{case_id}/claims/{claim_id}")
async def edit_claim_endpoint(
    case_id: UUID,
    claim_id: UUID,
    payload: dict[str, Any] = Body(...),  # noqa: B008
) -> dict[str, Any]:
    """Update a claim's text, confidence score, or both.

    Request body: ``{"claim_text": "...", "confidence_score": 0.85}``
    """
    async with async_session_factory() as db:
        stmt = select(Claim).where(Claim.id == claim_id, Claim.case_run_id == case_id)
        result = await db.execute(stmt)
        claim = result.scalar_one_or_none()
        if claim is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Claim not found")

        changed = False
        if "claim_text" in payload:
            claim.claim_text = payload["claim_text"]
            changed = True
        if "confidence_score" in payload:
            claim.confidence_score = payload["confidence_score"]
            changed = True

        if changed:
            # Mark in user_edits that this claim was edited.
            case_stmt = select(CaseRun).where(CaseRun.id == case_id)
            case_result = await db.execute(case_stmt)
            case = case_result.scalar_one_or_none()
            if case:
                edits = case.user_edits or {}
                if "edited_claims" not in edits:
                    edits["edited_claims"] = []
                edits["edited_claims"].append(
                    {
                        "claim_id": str(claim_id),
                        "timestamp": time.time(),
                        "changes": {
                            k: payload[k]
                            for k in ("claim_text", "confidence_score")
                            if k in payload
                        },
                    }
                )
                case.user_edits = edits

            await db.commit()
            await db.refresh(claim)

    return {
        "id": str(claim.id),
        "case_run_id": str(claim.case_run_id),
        "claim_text": claim.claim_text,
        "confidence_score": claim.confidence_score,
        "claim_type": claim.claim_type,
        "user_adjudication": claim.user_adjudication,
        "created_at": claim.created_at.isoformat() if claim.created_at else None,
    }


# ---------------------------------------------------------------------------
# POST /cases/{case_id}/claims — add a new claim
# ---------------------------------------------------------------------------


@router.post("/cases/{case_id}/claims")
async def add_claim_endpoint(
    case_id: UUID,
    payload: dict[str, Any] = Body(...),  # noqa: B008
) -> dict[str, Any]:
    """Add a new claim to a case session.

    Request body: ``{"claim_text": "...", "confidence_score": 0.8, "claim_type": "fact"}``
    """
    claim_text = payload.get("claim_text", "").strip()
    if not claim_text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="claim_text must be non-empty.",
        )
    confidence_score = payload.get("confidence_score", 0.0)
    claim_type = payload.get("claim_type", "fact")

    async with async_session_factory() as db:
        # Verify case exists.
        case_stmt = select(CaseRun).where(CaseRun.id == case_id)
        case_result = await db.execute(case_stmt)
        case = case_result.scalar_one_or_none()
        if case is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")

        claim = Claim(
            case_run_id=case_id,
            claim_text=claim_text,
            confidence_score=confidence_score,
            claim_type=claim_type,
        )
        db.add(claim)
        await db.flush()

        # Mark in user_edits.
        edits = case.user_edits or {}
        if "added_claims" not in edits:
            edits["added_claims"] = []
        edits["added_claims"].append(
            {
                "claim_id": str(claim.id),
                "timestamp": time.time(),
            }
        )
        case.user_edits = edits

        await db.commit()
        await db.refresh(claim)

    return {
        "id": str(claim.id),
        "case_run_id": str(claim.case_run_id),
        "claim_text": claim.claim_text,
        "confidence_score": claim.confidence_score,
        "claim_type": claim.claim_type,
        "user_adjudication": claim.user_adjudication,
        "created_at": claim.created_at.isoformat() if claim.created_at else None,
    }


# ---------------------------------------------------------------------------
# POST /cases/{case_id}/adjudicate — flag/confirm a claim or section
# ---------------------------------------------------------------------------


@router.post("/cases/{case_id}/adjudicate")
async def adjudicate_endpoint(
    case_id: UUID,
    payload: dict[str, Any] = Body(...),  # noqa: B008
) -> dict[str, Any]:
    """Flag a claim or analysis section as agreed/disputed.

    Request body:
    ``{"target_type": "claim"|"section", "target_id": "claim_uuid|section_key",
       "status": "agreed"|"disputed", "note": "optional note"}``
    """
    target_type = payload.get("target_type", "")
    target_id = payload.get("target_id", "")
    status_val = payload.get("status", "")
    note = payload.get("note")

    if target_type not in ("claim", "section"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="target_type must be 'claim' or 'section'.",
        )
    if status_val not in ("agreed", "disputed"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="status must be 'agreed' or 'disputed'.",
        )

    async with async_session_factory() as db:
        if target_type == "claim":
            stmt = select(Claim).where(Claim.id == UUID(target_id), Claim.case_run_id == case_id)
            result = await db.execute(stmt)
            claim = result.scalar_one_or_none()
            if claim is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Claim not found")

            adjudication = {"status": status_val}
            if note:
                adjudication["note"] = note
            claim.user_adjudication = adjudication
            await db.commit()
            await db.refresh(claim)

            return {
                "id": str(claim.id),
                "claim_text": claim.claim_text,
                "user_adjudication": claim.user_adjudication,
            }

        elif target_type == "section":
            # Store adjudication in user_edits.
            stmt = select(CaseRun).where(CaseRun.id == case_id)
            result = await db.execute(stmt)
            case = result.scalar_one_or_none()
            if case is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")

            edits = case.user_edits or {}
            if "section_adjudications" not in edits:
                edits["section_adjudications"] = {}
            edits["section_adjudications"][target_id] = {
                "status": status_val,
                "note": note,
                "timestamp": time.time(),
            }
            case.user_edits = edits
            await db.commit()

            return {
                "section_key": target_id,
                "adjudication": edits["section_adjudications"][target_id],
            }


# ---------------------------------------------------------------------------
# GET /cases/{case_id}/export — export case data
# ---------------------------------------------------------------------------


@router.get("/cases/{case_id}/export")
async def export_case_endpoint(
    case_id: UUID,
    format: str = Query("json", pattern="^(json|markdown)$"),
) -> StreamingResponse:
    """Export a case session as JSON or Markdown.

    Query params: ``?format=json`` (default) or ``?format=markdown``
    """
    async with async_session_factory() as db:
        stmt = (
            select(CaseRun)
            .where(CaseRun.id == case_id)
            .options(
                selectinload(CaseRun.stage_logs),
                selectinload(CaseRun.claims).selectinload(Claim.evidence_bindings),
            )
        )
        result = await db.execute(stmt)
        case = result.scalar_one_or_none()

    if case is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")

    # Reconstruct final_output.
    final_output: dict[str, str] = {}
    if case.stage_logs:
        for sl in case.stage_logs:
            if sl.stage_name == "generation" and isinstance(sl.output_snapshot, dict):
                final_output.update(sl.output_snapshot)
            elif sl.stage_name == "adversarial_review" and isinstance(sl.output_snapshot, dict):
                for k, v in sl.output_snapshot.items():
                    final_output[f"adversarial_{k}"] = v
            elif sl.stage_name == "calculation_check" and isinstance(sl.output_snapshot, dict):
                for k, v in sl.output_snapshot.items():
                    final_output[f"calculation_{k}"] = v

    # Serialize stages.
    stages = [
        {
            "id": str(sl.id),
            "stage_name": sl.stage_name,
            "input_snapshot": sl.input_snapshot,
            "output_snapshot": sl.output_snapshot,
            "duration_ms": sl.duration_ms,
            "error_trace": sl.error_trace,
            "created_at": sl.created_at.isoformat() if sl.created_at else None,
        }
        for sl in (case.stage_logs or [])
    ]

    # Serialize claims with evidence bindings.
    claims = []
    for cl in case.claims or []:
        cl_data = {
            "id": str(cl.id),
            "claim_text": cl.claim_text,
            "confidence_score": cl.confidence_score,
            "claim_type": cl.claim_type,
            "user_adjudication": cl.user_adjudication,
            "created_at": cl.created_at.isoformat() if cl.created_at else None,
            "evidence_bindings": [],
        }
        for eb in cl.evidence_bindings or []:
            cl_data["evidence_bindings"].append(
                {
                    "id": str(eb.id),
                    "chunk_id": str(eb.chunk_id),
                    "binding_strength": eb.binding_strength,
                    "quote_excerpt": eb.quote_excerpt,
                }
            )
        claims.append(cl_data)

    case_data = {
        "id": str(case.id),
        "session_id": case.session_id,
        "title": case.title,
        "status": case.status,
        "input_text": case.input_text,
        "created_at": case.created_at.isoformat() if case.created_at else None,
        "updated_at": case.updated_at.isoformat() if case.updated_at else None,
        "chat_history": case.chat_history,
        "user_edits": case.user_edits,
        "final_output": final_output,
        "stages": stages,
        "claims": claims,
    }

    if format == "markdown":
        md_lines = [
            f"# Fallanalyse: {case.title or 'Unbenannt'}",
            "",
            f"**Status:** {case.status}  ",
            f"**Erstellt:** {case_data['created_at']}  ",
            f"**Aktualisiert:** {case_data['updated_at']}  ",
            "",
            "---",
            "",
            "## Eingabetext",
            "",
            case.input_text or "*Keine Eingabe*",
            "",
            "---",
            "",
            "## Ergebnisse",
            "",
        ]
        for section_key, section_text in final_output.items():
            if section_text:
                section_title = section_key.replace("_", " ").title()
                md_lines.append(f"### {section_title}")
                md_lines.append("")
                md_lines.append(section_text)
                md_lines.append("")

        if claims:
            md_lines.append("---")
            md_lines.append("")
            md_lines.append("## Ansprüche / Claims")
            md_lines.append("")
            for cl in claims:
                adj = cl.get("user_adjudication") or {}
                adj_str = f" *(Adjudikation: {adj.get('status', 'unbewertet')})*" if adj else ""
                md_lines.append(
                    f"- **{cl['claim_type']}** (Konfidenz: {cl['confidence_score']:.2f}){adj_str}"
                )
                md_lines.append(f"  - {cl['claim_text']}")
                for eb in cl.get("evidence_bindings", []):
                    md_lines.append(
                        f"    - Beleg: „{eb['quote_excerpt']}” "
                        f"(Stärke: {eb['binding_strength']:.2f})"
                    )
                md_lines.append("")

        content = "\n".join(md_lines).encode("utf-8")
        media_type = "text/markdown; charset=utf-8"
        filename = f"case_{case_id}_{case.session_id}.md"
    else:
        content = json.dumps(case_data, ensure_ascii=False, indent=2, default=str).encode("utf-8")
        media_type = "application/json; charset=utf-8"
        filename = f"case_{case_id}_{case.session_id}.json"

    return StreamingResponse(
        iter([content]),
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(content)),
        },
    )
