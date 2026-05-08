"""Conversation service — CRUD operations for conversations, messages, and documents.

All functions accept a SQLAlchemy AsyncSession as their first argument and
return ORM model instances or plain dicts.  No side effects outside the
database.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Conversation, ConversationDocument, ConversationMessage

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Conversations
# ---------------------------------------------------------------------------


async def create_conversation(
    db: AsyncSession,
    *,
    title: str | None = None,
) -> Conversation:
    """Create a new conversation and return the ORM instance."""
    conv = Conversation(title=title)
    db.add(conv)
    await db.flush()
    await db.refresh(conv)
    logger.info("Created conversation %s", conv.id)
    return conv


async def get_conversation(
    db: AsyncSession,
    conversation_id: UUID,
    *,
    include_messages: bool = False,
    include_documents: bool = False,
) -> Conversation | None:
    """Fetch a conversation by ID.

    Use *include_messages* / *include_documents* to eagerly load related rows.
    """
    stmt = select(Conversation).where(Conversation.id == conversation_id)
    if include_messages:
        stmt = stmt.options(selectinload(Conversation.messages))
    if include_documents:
        stmt = stmt.options(selectinload(Conversation.documents))
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def list_conversations(
    db: AsyncSession,
    *,
    limit: int = 50,
) -> list[Conversation]:
    """Return recent conversations ordered by *updated_at* descending."""
    stmt = (
        select(Conversation)
        .order_by(Conversation.updated_at.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def delete_conversation(
    db: AsyncSession,
    conversation_id: UUID,
) -> bool:
    """Delete a conversation and all its messages/documents (CASCADE).

    Returns ``True`` if the conversation existed, ``False`` otherwise.
    """
    conv = await get_conversation(db, conversation_id)
    if conv is None:
        return False
    await db.delete(conv)
    await db.flush()
    logger.info("Deleted conversation %s", conversation_id)
    return True


async def touch_conversation(db: AsyncSession, conversation_id: UUID) -> None:
    """Update the *updated_at* timestamp of a conversation."""
    await db.execute(
        update(Conversation)
        .where(Conversation.id == conversation_id)
        .values(updated_at=datetime.now(timezone.utc)),
    )


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------


async def add_message(
    db: AsyncSession,
    *,
    conversation_id: UUID,
    role: str,
    content: str,
) -> ConversationMessage:
    """Append a message to a conversation and return the ORM instance."""
    msg = ConversationMessage(
        conversation_id=conversation_id,
        role=role,
        content=content,
    )
    db.add(msg)
    await db.flush()
    await db.refresh(msg)
    await touch_conversation(db, conversation_id)
    logger.info("Added %s message to conversation %s", role, conversation_id)
    return msg


async def get_messages(
    db: AsyncSession,
    conversation_id: UUID,
    *,
    limit: int | None = None,
) -> list[ConversationMessage]:
    """Return messages for a conversation, oldest first."""
    stmt = (
        select(ConversationMessage)
        .where(ConversationMessage.conversation_id == conversation_id)
        .order_by(ConversationMessage.created_at.asc())
    )
    if limit is not None:
        stmt = stmt.limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------


async def add_document(
    db: AsyncSession,
    *,
    conversation_id: UUID,
    original_filename: str,
    normalized_text: str,
    case_run_id: UUID | None = None,
) -> ConversationDocument:
    """Attach a document to a conversation."""
    doc = ConversationDocument(
        conversation_id=conversation_id,
        original_filename=original_filename,
        normalized_text=normalized_text,
        case_run_id=case_run_id,
    )
    db.add(doc)
    await db.flush()
    await db.refresh(doc)
    await touch_conversation(db, conversation_id)
    logger.info("Added document %s to conversation %s", original_filename, conversation_id)
    return doc


async def get_documents(
    db: AsyncSession,
    conversation_id: UUID,
) -> list[ConversationDocument]:
    """List documents attached to a conversation, oldest first."""
    stmt = (
        select(ConversationDocument)
        .where(ConversationDocument.conversation_id == conversation_id)
        .order_by(ConversationDocument.created_at.asc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def remove_document(
    db: AsyncSession,
    document_id: UUID,
) -> bool:
    """Remove a single document from its conversation."""
    stmt = select(ConversationDocument).where(ConversationDocument.id == document_id)
    result = await db.execute(stmt)
    doc = result.scalar_one_or_none()
    if doc is None:
        return False
    await db.delete(doc)
    await db.flush()
    logger.info("Removed document %s", document_id)
    return True


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------


def conversation_to_dict(conv: Conversation) -> dict[str, Any]:
    """Convert a Conversation ORM instance to a JSON-safe dict."""
    return {
        "id": str(conv.id),
        "title": conv.title,
        "created_at": conv.created_at.isoformat() if conv.created_at else None,
        "updated_at": conv.updated_at.isoformat() if conv.updated_at else None,
    }


def message_to_dict(msg: ConversationMessage) -> dict[str, Any]:
    """Convert a ConversationMessage ORM instance to a JSON-safe dict."""
    return {
        "id": str(msg.id),
        "conversation_id": str(msg.conversation_id),
        "role": msg.role,
        "content": msg.content,
        "created_at": msg.created_at.isoformat() if msg.created_at else None,
    }


def document_to_dict(doc: ConversationDocument) -> dict[str, Any]:
    """Convert a ConversationDocument ORM instance to a JSON-safe dict."""
    return {
        "id": str(doc.id),
        "conversation_id": str(doc.conversation_id),
        "original_filename": doc.original_filename,
        "text_length": len(doc.normalized_text),
        "case_run_id": str(doc.case_run_id) if doc.case_run_id else None,
        "created_at": doc.created_at.isoformat() if doc.created_at else None,
    }


def conversation_detail_to_dict(conv: Conversation) -> dict[str, Any]:
    """Full conversation detail including messages and documents."""
    data = conversation_to_dict(conv)
    data["messages"] = [message_to_dict(m) for m in (conv.messages or [])]
    data["documents"] = [document_to_dict(d) for d in (conv.documents or [])]
    return data
