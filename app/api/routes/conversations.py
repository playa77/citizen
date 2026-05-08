"""Conversation endpoints — CRUD + message streaming.

Endpoints:
    POST   /api/v1/conversations                    Create a conversation
    GET    /api/v1/conversations                    List conversations
    GET    /api/v1/conversations/{id}               Get conversation detail
    DELETE /api/v1/conversations/{id}               Delete conversation
    POST   /api/v1/conversations/{id}/messages      Send message (SSE response)
    POST   /api/v1/conversations/{id}/documents     Attach document
    DELETE /api/v1/conversations/{id}/documents/{did} Remove document
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections.abc import AsyncGenerator
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Body, File, Form, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse

from app.core import config as cfg
from app.db.session import async_session_factory
from app.services.chat_reasoning import generate_chat_response, run_first_message_pipeline
from app.services.conversation import (
    add_document,
    add_message,
    conversation_detail_to_dict,
    conversation_to_dict,
    create_conversation,
    delete_conversation,
    document_to_dict,
    get_conversation,
    get_documents,
    get_messages,
    list_conversations,
    message_to_dict,
    remove_document,
)
from app.services.ocr import process_document
from app.services.audit import AuditRecord, persist_audit_record
from app.utils.text import normalize_text

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# SSE helper
# ---------------------------------------------------------------------------


def _sse_format(data: dict[str, Any]) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


# ---------------------------------------------------------------------------
# Background audit persistence (copied from analyze.py)
# ---------------------------------------------------------------------------


async def _persist_audit_safely(audit_record: AuditRecord) -> None:
    try:
        async with async_session_factory() as db_session:
            await persist_audit_record(db_session, audit_record)
    except Exception:
        logger.exception("Background audit persistence failed")


# ---------------------------------------------------------------------------
# Conversation CRUD
# ---------------------------------------------------------------------------


@router.post("/conversations")
async def create_conversation_endpoint(
    title: str | None = Form(None),
    file: UploadFile | None = File(None),
) -> dict[str, Any]:
    """Create a new conversation, optionally with an initial document."""
    async with async_session_factory() as db:
        conv = await create_conversation(db, title=title)

        if file is not None and file.filename:
            try:
                ocr_text = await process_document(file)
                normalized = normalize_text(ocr_text)
                await add_document(
                    db,
                    conversation_id=conv.id,
                    original_filename=file.filename,
                    normalized_text=normalized,
                )
            except Exception as exc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Document processing failed: {exc}",
                ) from exc

        await db.commit()
        return conversation_detail_to_dict(conv)


@router.get("/conversations")
async def list_conversations_endpoint() -> list[dict[str, Any]]:
    """List recent conversations."""
    async with async_session_factory() as db:
        convs = await list_conversations(db)
        return [conversation_to_dict(c) for c in convs]


@router.get("/conversations/{conversation_id}")
async def get_conversation_endpoint(conversation_id: UUID) -> dict[str, Any]:
    """Get conversation with messages and documents."""
    async with async_session_factory() as db:
        conv = await get_conversation(
            db,
            conversation_id,
            include_messages=True,
            include_documents=True,
        )
        if conv is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
        return conversation_detail_to_dict(conv)


@router.delete("/conversations/{conversation_id}")
async def delete_conversation_endpoint(conversation_id: UUID) -> dict[str, str]:
    """Delete a conversation and all its data."""
    async with async_session_factory() as db:
        deleted = await delete_conversation(db, conversation_id)
        if not deleted:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
        await db.commit()
        return {"status": "deleted", "id": str(conversation_id)}


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------


@router.post("/conversations/{conversation_id}/messages")
async def send_message_endpoint(
    conversation_id: UUID,
    payload: dict[str, str] = Body(...),  # noqa: B008
) -> StreamingResponse:
    """Send a message in a conversation and stream the assistant's response via SSE.

    Request body: ``{"content": "..."}``

    If this is the **first user message** in the conversation *and*
    documents are attached, the full 7-stage pipeline is executed and the
    structured analysis is stored as the assistant response.

    Subsequent messages use a focused chat + RAG mode.
    """
    content = payload.get("content", "")
    if not content or not content.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Message content must be non-empty.",
        )

    async with async_session_factory() as db:
        conv = await get_conversation(
            db,
            conversation_id,
            include_messages=True,
            include_documents=True,
        )
        if conv is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

        # Count prior user messages (conv.messages was loaded before add_message).
        prior_user_message_count = sum(1 for m in conv.messages if m.role == "user")

        # Extract document texts before the session closes.
        documents = conv.documents or []
        doc_texts = [d.normalized_text for d in documents]
        has_documents = len(documents) > 0

        # Determine mode: first user message + has documents → full pipeline.
        is_first_pipeline_run = prior_user_message_count == 0 and has_documents

        # Store the user message.
        await add_message(db, conversation_id=conversation_id, role="user", content=content.strip())
        await db.commit()

        session_id = str(uuid.uuid4())
        start = time.monotonic()

    # ── Define the SSE generator ───────────────────────────────────────
    async def event_generator() -> AsyncGenerator[str, None]:
        accumulated_response = ""

        try:
            if is_first_pipeline_run:
                # ── Full 7-stage pipeline ──────────────────────────────
                async for event in run_first_message_pipeline(doc_texts):
                    yield event
                    # Collect the final output from the last event.
                    if event.startswith("data: "):
                        try:
                            parsed = json.loads(event[6:].strip())
                            if "final_output" in parsed:
                                # Extract a readable summary from each section.
                                fo = parsed["final_output"]
                                sections = [
                                    fo.get("sachverhalt", ""),
                                    fo.get("rechtliche_wuerdigung", ""),
                                    fo.get("ergebnis", ""),
                                    fo.get("handlungsempfehlung", ""),
                                    fo.get("entwurf", ""),
                                    fo.get("unsicherheiten", ""),
                                ]
                                accumulated_response = "\n\n".join(
                                    s for s in sections if s
                                )
                        except (json.JSONDecodeError, KeyError):
                            pass
            else:
                # ── Chat + RAG mode ─────────────────────────────────────
                messages_history: list[dict[str, str]] = []
                async with async_session_factory() as inner_db:
                    all_msgs = await get_messages(inner_db, conversation_id)
                    for m in all_msgs:
                        messages_history.append({"role": m.role, "content": m.content})

                async for event in generate_chat_response(
                    messages=messages_history,
                    document_texts=doc_texts,
                    conversation_id=str(conversation_id),
                ):
                    yield event
                    if event.startswith("data: "):
                        try:
                            parsed = json.loads(event[6:].strip())
                            if parsed.get("type") == "done":
                                accumulated_response = parsed.get("full_response", "")
                        except (json.JSONDecodeError, KeyError):
                            pass

            # Store the assistant response.
            if accumulated_response:
                async with async_session_factory() as inner_db:
                    await add_message(
                        inner_db,
                        conversation_id=conversation_id,
                        role="assistant",
                        content=accumulated_response,
                    )
                    await inner_db.commit()

        except Exception as exc:
            logger.exception("Message generation failed for conversation %s", conversation_id)
            error_payload = {
                "error": "message_generation_failed",
                "detail": str(exc),
                "conversation_id": str(conversation_id),
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
# Documents
# ---------------------------------------------------------------------------


@router.post("/conversations/{conversation_id}/documents")
async def add_document_endpoint(
    conversation_id: UUID,
    file: UploadFile = File(...),
) -> dict[str, Any]:
    """Upload and attach a document to a conversation."""
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No file provided")

    async with async_session_factory() as db:
        conv = await get_conversation(db, conversation_id)
        if conv is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

        try:
            ocr_text = await process_document(file)
            normalized = normalize_text(ocr_text)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Document processing failed: {exc}",
            ) from exc

        doc = await add_document(
            db,
            conversation_id=conversation_id,
            original_filename=file.filename,
            normalized_text=normalized,
        )
        await db.commit()
        return document_to_dict(doc)


@router.get("/conversations/{conversation_id}/documents")
async def list_documents_endpoint(conversation_id: UUID) -> list[dict[str, Any]]:
    """List documents attached to a conversation."""
    async with async_session_factory() as db:
        docs = await get_documents(db, conversation_id)
        return [document_to_dict(d) for d in docs]


@router.delete("/conversations/{conversation_id}/documents/{document_id}")
async def remove_document_endpoint(
    conversation_id: UUID,
    document_id: UUID,
) -> dict[str, str]:
    """Remove a document from a conversation."""
    async with async_session_factory() as db:
        removed = await remove_document(db, document_id)
        if not removed:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
        await db.commit()
        return {"status": "deleted", "id": str(document_id)}
