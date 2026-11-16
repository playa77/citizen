"""Intake interview endpoints.

Endpoints:
    POST /api/v1/intake/start         Begin a new intake interview
    POST /api/v1/intake/{id}/message  Send a user reply
    GET  /api/v1/intake/{id}          Get current state
    POST /api/v1/intake/{id}/restart  Abandon & reset
    POST /api/v1/intake/{id}/confirm  Force-finalise

Every session response carries ``resolved_modules`` (WP-95): one entry per
determined area key (primary first, then secondary) naming the owning
module, its version, whether the key is a legacy alias and whether the
module is enabled — ``[]`` while no area is determined yet.
"""

# Semantic Version: 0.4.0 | 2026-11-16 — WP-95: resolved_modules on every session
# response (additive key).
# 0.3.0

from __future__ import annotations

import logging
import uuid
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Body, HTTPException, status

from app.db.session import async_session_factory
from app.modules.runtime import resolved_modules
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


def _with_modules(session: dict[str, Any]) -> dict[str, Any]:
    """Add ``resolved_modules`` for the session's determined area keys."""
    keys = [session["primary_area"]] if session.get("primary_area") else []
    keys += [k for k in session.get("secondary_areas") or [] if k not in keys]
    return {**session, "resolved_modules": resolved_modules(keys)}


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
            return _with_modules(
                await start_intake(
                    db,
                    session_id=session_id,
                    initial_text=initial_text,
                    max_turns=max_turns,
                )
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
            return _with_modules(
                await continue_intake(
                    db,
                    intake_id=intake_id,
                    user_message=message,
                )
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
        return _with_modules(result)


@router.post("/intake/{intake_id}/restart")
async def post_restart_intake(intake_id: UUID) -> dict[str, Any]:
    """Abandon the current intake and reset it."""
    async with async_session_factory() as db:
        try:
            return _with_modules(await restart_intake(db, intake_id=intake_id))
        except IntakeError as exc:
            raise _err(f"Intake restart failed: {exc}") from exc


@router.post("/intake/{intake_id}/confirm")
async def post_confirm_intake(intake_id: UUID) -> dict[str, Any]:
    """Force-finalise the intake, returning the IntakeResult."""
    async with async_session_factory() as db:
        try:
            return _with_modules(await finalize_intake(db, intake_id=intake_id))
        except IntakeError as exc:
            raise _err(f"Intake confirm failed: {exc}") from exc
