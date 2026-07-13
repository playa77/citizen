"""Document generation endpoints — WP-40.

Endpoints:
    POST   /api/v1/documents/generate          Generate an action document
    GET    /api/v1/documents/generator-options/{case_run_id}  List available generators

All endpoints require the ``X-Disclaimer-Ack`` header (enforced by middleware).
"""

# Semantic Version: 0.1.0

from __future__ import annotations

import logging
from datetime import date
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Body, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.routes.cases import get_case_endpoint
from app.db.models import CaseRun, Claim
from app.db.session import async_session_factory
from app.services.document_generators import (
    generate_document,
    select_generator,
)
from app.services.fristen import (
    FristResult,
)
from app.services.pseudonymization import (
    PiiMapping,
    depseudonymize_tolerant,
)
from app.services.rules_engine import (
    ReconciliationLineItem,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# POST /documents/generate
# ---------------------------------------------------------------------------


class DocumentGenerationError(Exception):
    """Raised when document generation fails."""


def _extract_frist_data(case: CaseRun, case_dict: dict[str, Any]) -> FristResult | None:
    """Try to reconstruct a FristResult from case pipeline output."""
    final_output = case_dict.get("final_output", {}) or {}

    # Try pipeline output first, then stage logs
    frist_raw: dict[str, Any] | None = final_output.get("frist_berechnung", None)
    if frist_raw is None:
        for sl in case.stage_logs or []:
            if sl.stage_name in ("generation", "construction") and sl.output_snapshot:
                candidate = sl.output_snapshot.get("frist_berechnung")
                if isinstance(candidate, dict):
                    frist_raw = candidate
                    break

    if not isinstance(frist_raw, dict):
        return None

    def _parse_date(value: Any) -> date | None:
        if isinstance(value, date):
            return value
        if isinstance(value, str):
            try:
                return date.fromisoformat(value)
            except ValueError:
                pass
            try:
                from datetime import datetime as _dt

                return _dt.strptime(value, "%d.%m.%Y").date()
            except (ValueError, TypeError):
                pass
        return None

    bekanntgabe = _parse_date(frist_raw.get("bekanntgabe"))
    frist_ende = _parse_date(frist_raw.get("frist_ende"))
    oq1_alt = _parse_date(frist_raw.get("oq1_alternate_ende"))

    if bekanntgabe is None or frist_ende is None:
        logger.warning("FristResult reconstruction missing required dates")
        return None

    try:
        return FristResult(
            bekanntgabe=bekanntgabe,
            frist_ende=frist_ende,
            frist_typ=str(frist_raw.get("frist_typ", "monat")),
            rollover_applied=bool(frist_raw.get("rollover_applied", False)),
            oq1_flag=bool(frist_raw.get("oq1_flag", False)),
            oq1_alternate_ende=oq1_alt,
            explanation_de=str(frist_raw.get("explanation_de", "")),
        )
    except (TypeError, ValueError) as exc:
        logger.warning("Could not reconstruct FristResult from data: %s", exc)
        return None


def _extract_claims_dicts(case: CaseRun) -> list[dict[str, Any]]:
    """Extract claims as dicts from a CaseRun, including user adjudication."""
    results: list[dict[str, Any]] = []
    for claim in case.claims or []:
        # Determine verification_status from evidence bindings
        verification = "unverifiziert"
        for eb in claim.evidence_bindings or []:
            # If any binding exists, use best available
            if eb.binding_strength >= 0.8:
                verification = "exakt"
                break
            verification = "normalisiert"

        claim_dict: dict[str, Any] = {
            "claim_text": claim.claim_text,
            "confidence_score": claim.confidence_score,
            "claim_type": claim.claim_type,
            "verification_status": verification,
            "user_adjudication": claim.user_adjudication or {},
        }
        results.append(claim_dict)
    return results


def _extract_reconciliation(
    case_dict: dict[str, Any],
) -> list[ReconciliationLineItem]:
    """Try to extract reconciliation data from case final_output."""
    final_output = case_dict.get("final_output", {}) or {}
    calc_raw = final_output.get("calculation_check", None)
    if isinstance(calc_raw, list):
        items: list[ReconciliationLineItem] = []
        for entry in calc_raw:
            if isinstance(entry, dict):
                items.append(
                    ReconciliationLineItem(
                        label=str(entry.get("label", "")),
                        jobcenter_ergebnis=entry.get("jobcenter_ergebnis"),
                        korrekt=entry.get("korrekt"),
                        differenz=entry.get("differenz"),
                        relevant_rule=str(entry.get("relevant_rule", "")),
                        detail=str(entry.get("detail", "")),
                    )
                )
        return items
    return []


def _extract_case_metadata(
    case_dict: dict[str, Any],
) -> tuple[date | None, str | None, str | None]:
    """Extract Bescheid date, Aktenzeichen, and Behörde from case data."""
    final_output = case_dict.get("final_output", {}) or {}

    # Try to find date from various sources
    bescheid_datum = None
    for key in ("bescheid_datum", "date", "bescheid_date"):
        val = final_output.get(key)
        if isinstance(val, str):
            try:
                bescheid_datum = date.fromisoformat(val)
                break
            except ValueError:
                try:
                    from datetime import datetime as dt

                    bescheid_datum = dt.strptime(val, "%d.%m.%Y").date()
                    break
                except (ValueError, TypeError):
                    pass

    aktenzeichen = final_output.get("aktenzeichen", None)
    behoerde = final_output.get("behoerde", None)

    return bescheid_datum, aktenzeichen, behoerde


@router.post("/documents/generate")
async def generate_document_endpoint(
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    """Generate an action document from a completed case run.

    Request body::

        {
            "case_run_id": "<uuid>",
            "doc_type": "widerspruch" | "ueberpruefungsantrag_44" |
                        "akteneinsichtsantrag_25",
            "user_data": {                // optional
                "name": "...",
                "adresse": "..."
            },
            "doc_type_override": null     // optional: force a specific type
        }

    Returns a ``GeneratedDocument`` as JSON.
    """
    case_run_id_str = body.get("case_run_id")
    doc_type = body.get("doc_type")
    user_data = body.get("user_data", {}) or {}

    if not case_run_id_str:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Feld 'case_run_id' ist erforderlich.",
        )

    try:
        case_run_id = UUID(case_run_id_str)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ungültige case_run_id: {case_run_id_str!r}",
        )

    if doc_type and doc_type not in (
        "widerspruch",
        "widerspruch_jahresfrist",
        "ueberpruefungsantrag_44",
        "akteneinsichtsantrag_25",
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unbekannter doc_type: {doc_type!r}. "
            f"Erlaubt: widerspruch, widerspruch_jahresfrist, "
            f"ueberpruefungsantrag_44, akteneinsichtsantrag_25.",
        )

    # ── Fetch case from DB ────────────────────────────────────────────
    async with async_session_factory() as db:
        stmt = (
            select(CaseRun)
            .where(CaseRun.id == case_run_id)
            .options(
                selectinload(CaseRun.stage_logs),
                selectinload(CaseRun.claims).selectinload(Claim.evidence_bindings),
            )
        )
        result = await db.execute(stmt)
        case = result.scalar_one_or_none()

    if case is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"CaseRun {case_run_id} nicht gefunden.",
        )

    # ── Build case dict (reuse endpoint logic) ────────────────────────
    try:
        case_dict = await get_case_endpoint(case_run_id)
    except Exception as exc:
        logger.warning("Could not build case dict: %s", exc)
        case_dict = {"id": str(case_run_id), "final_output": {}}

    # ── Extract data ──────────────────────────────────────────────────
    frist_result = _extract_frist_data(case, case_dict)
    claims_list = _extract_claims_dicts(case)
    reconciliation = _extract_reconciliation(case_dict)
    bescheid_datum, aktenzeichen, behoerde = _extract_case_metadata(case_dict)

    # ── Auto-select generator if not specified ────────────────────────
    if not doc_type:
        doc_type = select_generator(frist_result, claims_list)

    # ── Handle PII ────────────────────────────────────────────────────
    pii_mapping = None
    if case.pii_mapping:
        try:
            pii_mapping = PiiMapping.from_dict(case.pii_mapping)
        except Exception as exc:
            logger.warning("Could not deserialize PiiMapping: %s", exc)

    # ── Generate document ─────────────────────────────────────────────
    doc = generate_document(
        doc_type=doc_type,
        frist_result=frist_result,
        reconciliation=reconciliation,
        claims=claims_list,
        user_data=user_data or None,
        bescheid_datum=bescheid_datum,
        aktenzeichen=aktenzeichen,
        behoerde=behoerde,
    )

    # ── Depseudonymize ────────────────────────────────────────────────
    if pii_mapping is not None:
        depseu_text, dep_warnings = depseudonymize_tolerant(
            doc.rendered_text,
            pii_mapping,
        )
        doc.rendered_text = depseu_text
        doc.warnings.extend(f"Depseudonymisierung: {w}" for w in dep_warnings)

    # ── Serialize response ────────────────────────────────────────────
    response: dict[str, Any] = {
        "document_type": doc.document_type,
        "title": doc.title,
        "rendered_text": doc.rendered_text,
        "slots": [
            {
                "key": s.key,
                "label": s.label,
                "source": s.source,
                "value": s.value,
                "verified": s.verified,
                "needs_review": s.needs_review,
                "review_topic": s.review_topic,
            }
            for s in doc.slots
        ],
        "warnings": doc.warnings,
        "generation_metadata": doc.generation_metadata,
    }

    return response


# ---------------------------------------------------------------------------
# GET /documents/generator-options/{case_run_id}
# ---------------------------------------------------------------------------


@router.get("/documents/generator-options/{case_run_id}")
async def get_generator_options_endpoint(
    case_run_id: UUID,
) -> dict[str, Any]:
    """Return which document generators are available for a given case.

    Analyses the Frist status and claim verification state to determine
    which document types are feasible.
    """
    async with async_session_factory() as db:
        stmt = (
            select(CaseRun)
            .where(CaseRun.id == case_run_id)
            .options(
                selectinload(CaseRun.stage_logs),
                selectinload(CaseRun.claims).selectinload(Claim.evidence_bindings),
            )
        )
        result = await db.execute(stmt)
        case = result.scalar_one_or_none()

    if case is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"CaseRun {case_run_id} nicht gefunden.",
        )

    try:
        case_dict = await get_case_endpoint(case_run_id)
    except Exception:
        case_dict = {"id": str(case_run_id), "final_output": {}}

    frist_result = _extract_frist_data(case, case_dict)
    claims_list = _extract_claims_dicts(case)

    # Determine available generators
    available: dict[str, Any] = {}
    recommended: str | None = None

    # Count verified+confirmed claims
    verified_count = sum(
        1
        for c in claims_list
        if c.get("verification_status") in ("exakt", "normalisiert")
        and isinstance(c.get("user_adjudication"), dict)
        and c["user_adjudication"].get("status") == "confirmed"
    )

    # Count unverified claims
    unverified_count = sum(
        1 for c in claims_list if c.get("verification_status") == "unverifiziert"
    )

    if frist_result:
        recommended = select_generator(frist_result)
        available["widerspruch"] = {
            "available": frist_result.frist_ende >= date.today()
            or frist_result.frist_typ == "jahr",
            "frist_ende": frist_result.frist_ende.isoformat(),
            "frist_typ": frist_result.frist_typ,
        }
        available["ueberpruefungsantrag_44"] = {
            "available": frist_result.frist_ende < date.today()
            and frist_result.frist_typ != "kein_va",
            "frist_ende": frist_result.frist_ende.isoformat(),
        }
    else:
        available["widerspruch"] = {"available": False, "reason": "Keine Fristdaten"}
        available["ueberpruefungsantrag_44"] = {"available": False, "reason": "Keine Fristdaten"}

    # Akteneinsicht is always available
    available["akteneinsichtsantrag_25"] = {"available": True}

    return {
        "case_run_id": str(case_run_id),
        "recommended": recommended,
        "available": available,
        "claims": {
            "total": len(claims_list),
            "verified_confirmed": verified_count,
            "unverified": unverified_count,
        },
    }
