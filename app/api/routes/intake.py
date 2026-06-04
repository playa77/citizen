"""Intake interview endpoints.

Endpoints:
    POST /api/v1/intake/start         Begin a new intake interview
    POST /api/v1/intake/{id}/message  Send a user reply
    GET  /api/v1/intake/{id}          Get current state
    POST /api/v1/intake/{id}/restart  Abandon & reset
    POST /api/v1/intake/{id}/confirm  Force-finalise
"""

# Semantic Version: 0.3.0

from __future__ import annotations

import logging
import uuid
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Body, HTTPException, status

from app.db.session import async_session_factory
from app.services.intake import (
    IntakeError,
    IntakeTurnLimitReached,
    continue_intake,
    finalize_intake,
    get_intake,
    restart_intake,
    start_intake,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _err(msg: str, code: int = status.HTTP_400_BAD_REQUEST) -> HTTPException:
    return HTTPException(status_code=code, detail=msg)


@router.post("/intake/start")
async def post_start_intake(
    payload: dict[str, Any] = Body(...),  # noqa: B008
) -> dict[str, Any]:
    """Start a new intake interview.

    Body: ``{"session_id": "...", "initial_text": "..."}``
    """
    session_id = str(payload.get("session_id") or uuid.uuid4())
    initial_text = str(payload.get("initial_text") or "").strip()
    max_turns = int(payload.get("max_turns") or 8)
    if not initial_text:
        raise _err("'initial_text' must be non-empty.")
    if max_turns < 2 or max_turns > 12:
        raise _err("'max_turns' must be between 2 and 12.")

    async with async_session_factory() as db:
        try:
            return await start_intake(
                db,
                session_id=session_id,
                initial_text=initial_text,
                max_turns=max_turns,
            )
        except IntakeError as exc:
            raise _err(f"Intake failed: {exc}") from exc


@router.post("/intake/{intake_id}/message")
async def post_continue_intake(
    intake_id: UUID,
    payload: dict[str, Any] = Body(...),  # noqa: B008
) -> dict[str, Any]:
    """Send a user reply during an active interview.

    Body: ``{"message": "..."}``
    """
    message = str(payload.get("message") or "").strip()
    if not message:
        raise _err("'message' must be non-empty.")

    async with async_session_factory() as db:
        try:
            return await continue_intake(
                db, intake_id=intake_id, user_message=message,
            )
        except IntakeTurnLimitReached as exc:
            raise _err(str(exc), code=status.HTTP_409_CONFLICT) from exc
        except IntakeError as exc:
            raise _err(f"Intake failed: {exc}") from exc


@router.get("/intake/{intake_id}")
async def get_intake_endpoint(intake_id: UUID) -> dict[str, Any]:
    """Get the current state of an intake session."""
    async with async_session_factory() as db:
        result = await get_intake(db, intake_id)
        if result is None:
            raise _err("Intake not found", code=status.HTTP_404_NOT_FOUND)
        return result


@router.post("/intake/{intake_id}/restart")
async def post_restart_intake(intake_id: UUID) -> dict[str, Any]:
    """Abandon the current intake and reset it."""
    async with async_session_factory() as db:
        try:
            return await restart_intake(db, intake_id=intake_id)
        except IntakeError as exc:
            raise _err(f"Intake restart failed: {exc}") from exc


@router.post("/intake/{intake_id}/confirm")
async def post_confirm_intake(intake_id: UUID) -> dict[str, Any]:
    """Force-finalise the intake, returning the IntakeResult."""
    async with async_session_factory() as db:
        try:
            return await finalize_intake(db, intake_id=intake_id)
        except IntakeError as exc:
            raise _err(f"Intake confirm failed: {exc}") from exc
