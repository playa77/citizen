"""Appointment dossier endpoints (roadmap P10, WP-101/WP-103).

Endpoints:
    POST /api/v1/cases/{case_id}/dossier?format=json|pdf  Build the next revision
    GET  /api/v1/cases/{case_id}/dossier?format=json|pdf  Last built revision
    GET  /api/v1/cases/{case_id}/dossier/chronology       Proposals + decisions
    PUT  /api/v1/cases/{case_id}/dossier/chronology       Confirm/correct (full state)

The JSON form is ``citizen-dossier-v1.0`` (``app/dossier/``); the PDF is
rendered locally from the same stored JSON and embeds it. Both carry the
Art. 50 provenance marker. Contract: ``API_DOCUMENTATION.md`` § 8.11.
"""

# Semantic Version: 1.0.0 | 2026-11-16 — P10 initial.

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Body, HTTPException, Query, status
from fastapi.responses import JSONResponse, Response

from app.db.models import CaseDossier
from app.db.session import async_session_factory
from app.dossier.pdf import render_pdf
from app.services import dossier_service
from app.services.dossier_service import CaseNotFoundError

logger = logging.getLogger(__name__)

router = APIRouter()

_FORMAT = Query("json", pattern="^(json|pdf)$")


def _case_not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")


def _respond(row: CaseDossier, fmt: str, status_code: int) -> Response:
    headers = {
        "X-Dossier-Revision": str(row.revision),
        "X-Dossier-Sha256": row.content_sha256,
        "X-Dossier-Schema": row.schema_version,
    }
    if fmt == "pdf":
        content = render_pdf(row.dossier_json)
        headers["Content-Disposition"] = (
            f'attachment; filename="dossier_{row.case_run_id}_r{row.revision}.pdf"'
        )
        return Response(
            content=content,
            media_type="application/pdf",
            status_code=status_code,
            headers=headers,
        )
    return JSONResponse(
        status_code=status_code,
        headers=headers,
        content={
            "case_id": str(row.case_run_id),
            "revision": row.revision,
            "schema_version": row.schema_version,
            "content_sha256": row.content_sha256,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "dossier": row.dossier_json,
        },
    )


@router.post("/cases/{case_id}/dossier")
async def build_dossier_endpoint(case_id: UUID, format: str = _FORMAT) -> Response:
    """Build and store the next dossier revision; return it as JSON or PDF."""
    async with async_session_factory() as db:
        try:
            row = await dossier_service.build_and_store(db, case_id)
        except CaseNotFoundError:
            raise _case_not_found() from None
    logger.info("dossier built: case=%s revision=%d", case_id, row.revision)
    return _respond(row, format, status.HTTP_201_CREATED)


@router.get("/cases/{case_id}/dossier")
async def get_dossier_endpoint(case_id: UUID, format: str = _FORMAT) -> Response:
    """Return the last built revision (JSON, or PDF rendered from it)."""
    async with async_session_factory() as db:
        if not await dossier_service.case_exists(db, case_id):
            raise _case_not_found()
        row = await dossier_service.latest_dossier(db, case_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "dossier_not_built",
                "message": "Für diesen Fall wurde noch kein Dossier erstellt.",
                "action": f"POST /api/v1/cases/{case_id}/dossier",
            },
        )
    return _respond(row, format, status.HTTP_200_OK)


@router.get("/cases/{case_id}/dossier/chronology")
async def get_chronology_endpoint(case_id: UUID) -> dict[str, Any]:
    """Chronology proposals with the person's decisions and confirmed facts."""
    async with async_session_factory() as db:
        try:
            return await dossier_service.chronology_view(db, case_id)
        except CaseNotFoundError:
            raise _case_not_found() from None


@router.put("/cases/{case_id}/dossier/chronology")
async def put_chronology_endpoint(
    case_id: UUID,
    payload: dict[str, Any] = Body(...),  # noqa: B008
) -> dict[str, Any]:
    """Replace the confirmation state (decisions, added events, facts)."""
    async with async_session_factory() as db:
        try:
            return await dossier_service.update_chronology(db, case_id, payload)
        except CaseNotFoundError:
            raise _case_not_found() from None
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": "invalid_chronology_update", "message": str(exc)},
            ) from None
