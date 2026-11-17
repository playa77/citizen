"""Dossier persistence and case loading (WP-101/WP-103).

Bridges the database and the pure generator in ``app/dossier/``:

* loads a case (input text, attached documents, claims with evidence,
  calculation result, area keys, the person's chronology decisions/facts);
* builds a dossier, stores it as the next ``case_dossier`` revision and
  returns it;
* serves and updates the chronology confirmation state, kept in
  ``case_run.user_edits["dossier"]`` (``{"decisions": {...}, "added": [...],
  "facts": {...}}``) so it survives every rebuild.

Claim texts and quotes are depseudonymized with the case's PII mapping
before they enter the dossier: the dossier is the person's own document.
"""

# Semantic Version: 1.0.0 | 2026-11-16 — P10 initial.

from __future__ import annotations

import copy
import hashlib
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.db.models import (
    CaseDossier,
    CaseRun,
    CaseRunArea,
    Claim,
    ConversationDocument,
    LegalChunk,
)
from app.dossier.builder import (
    DOSSIER_SCHEMA_VERSION,
    DossierInputs,
    build_dossier,
    chronology_entries,
)
from app.dossier.chronology import ChronologyDecisions, SourceText, validate_update
from app.dossier.deadlines import validate_facts
from app.dossier.drafts import make_draft_factory
from app.modules.runtime import request_modules
from app.services.disclosure import build_disclosure_and_provenance
from app.services.pseudonymization import PiiMapping, depseudonymize_tolerant

logger = logging.getLogger(__name__)

#: Key in ``case_run.user_edits`` holding the dossier confirmation state.
USER_EDITS_KEY = "dossier"


class CaseNotFoundError(LookupError):
    """The case id does not exist."""


@dataclass
class LoadedCase:
    case: CaseRun
    legal_areas: list[str]
    documents: list[ConversationDocument]
    chunk_paths: dict[uuid.UUID, str]


def canonical_sha256(dossier: dict[str, Any]) -> str:
    payload = json.dumps(dossier, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def load_case(db: AsyncSession, case_id: uuid.UUID) -> LoadedCase:
    stmt = (
        select(CaseRun)
        .where(CaseRun.id == case_id)
        .options(
            selectinload(CaseRun.stage_logs),
            selectinload(CaseRun.claims).selectinload(Claim.evidence_bindings),
        )
    )
    case = (await db.execute(stmt)).scalar_one_or_none()
    if case is None:
        raise CaseNotFoundError(str(case_id))
    areas = (
        (
            await db.execute(
                select(CaseRunArea)
                .where(CaseRunArea.case_run_id == case_id)
                .order_by(CaseRunArea.is_primary.desc(), CaseRunArea.created_at)
            )
        )
        .scalars()
        .all()
    )
    documents = (
        (
            await db.execute(
                select(ConversationDocument)
                .where(ConversationDocument.case_run_id == case_id)
                .order_by(ConversationDocument.created_at)
            )
        )
        .scalars()
        .all()
    )
    chunk_ids = {eb.chunk_id for cl in case.claims or [] for eb in cl.evidence_bindings or []}
    chunk_paths: dict[uuid.UUID, str] = {}
    if chunk_ids:
        rows = await db.execute(
            select(LegalChunk.id, LegalChunk.hierarchy_path).where(LegalChunk.id.in_(chunk_ids))
        )
        chunk_paths = {row[0]: row[1] for row in rows.all()}
    return LoadedCase(case, [a.legal_area for a in areas], list(documents), chunk_paths)


def dossier_state(case: CaseRun) -> tuple[ChronologyDecisions, dict[str, Any]]:
    state = (case.user_edits or {}).get(USER_EDITS_KEY) or {}
    return (
        ChronologyDecisions(
            decisions=dict(state.get("decisions") or {}),
            added=list(state.get("added") or []),
        ),
        dict(state.get("facts") or {}),
    )


def _sources(loaded: LoadedCase) -> list[SourceText]:
    sources = [SourceText("case_input", "Analysierter Text", loaded.case.input_text or "")]
    seen = {loaded.case.input_text or ""}
    for doc in loaded.documents:
        if doc.normalized_text in seen:
            continue  # the analysed text itself, attached as a document
        seen.add(doc.normalized_text)
        sources.append(
            SourceText(
                f"conversation_document:{doc.id}", doc.original_filename, doc.normalized_text
            )
        )
    return sources


def _calculation(case: CaseRun) -> dict[str, Any] | None:
    for log in case.stage_logs or []:
        if log.stage_name != "calculation_check" or not isinstance(log.output_snapshot, dict):
            continue
        result = log.output_snapshot.get("result")
        if isinstance(result, dict):
            return {"result": result}
        return {"summary": log.output_snapshot}
    return None


def _claims(loaded: LoadedCase) -> list[dict[str, Any]]:
    mapping: PiiMapping | None = None
    if loaded.case.pii_mapping:
        try:
            mapping = PiiMapping.from_dict(loaded.case.pii_mapping)
        except Exception as exc:  # a broken mapping must not break the dossier
            logger.warning("dossier: could not deserialize PiiMapping: %s", exc)

    def clear(text: str) -> str:
        if mapping is None:
            return text
        restored, _warnings = depseudonymize_tolerant(text, mapping)
        return restored

    claims = []
    for claim in loaded.case.claims or []:
        claims.append(
            {
                "claim_id": str(claim.id),
                "claim_text": clear(claim.claim_text),
                "claim_type": claim.claim_type,
                "confidence_score": claim.confidence_score,
                "user_adjudication": claim.user_adjudication,
                "bindings": [
                    {
                        "quote_excerpt": clear(eb.quote_excerpt),
                        "binding_strength": eb.binding_strength,
                        "source": loaded.chunk_paths.get(eb.chunk_id),
                    }
                    for eb in claim.evidence_bindings or []
                ],
            }
        )
    return claims


def case_inputs(loaded: LoadedCase, revision: int) -> DossierInputs:
    decisions, facts = dossier_state(loaded.case)
    module_ids = request_modules(loaded.legal_areas or None)
    disclosure, provenance = build_disclosure_and_provenance(settings, loaded.legal_areas or None)
    case = loaded.case
    return DossierInputs(
        case_id=str(case.id),
        title=case.title,
        created_at=case.created_at.isoformat() if case.created_at else None,
        legal_areas=list(loaded.legal_areas),
        module_ids=module_ids,
        sources=_sources(loaded),
        decisions=decisions,
        facts=facts,
        claims=_claims(loaded),
        calculation=_calculation(case),
        revision=revision,
        generated_at=datetime.now(UTC).isoformat(),
        disclosure=disclosure.model_dump(mode="json"),
        provenance=provenance.model_dump(mode="json"),
        disclaimer_version=str(settings.DISCLAIMER_VERSION),
    )


async def build_and_store(db: AsyncSession, case_id: uuid.UUID) -> CaseDossier:
    """Build the next dossier revision for *case_id* and persist it."""
    loaded = await load_case(db, case_id)
    current = (
        await db.execute(
            select(func.max(CaseDossier.revision)).where(CaseDossier.case_run_id == case_id)
        )
    ).scalar_one_or_none()
    revision = int(current or 0) + 1
    inputs = case_inputs(loaded, revision)
    hint = inputs.module_ids[0] if inputs.module_ids else None
    dossier = build_dossier(inputs, make_draft_factory(hint))
    row = CaseDossier(
        case_run_id=case_id,
        revision=revision,
        schema_version=DOSSIER_SCHEMA_VERSION,
        dossier_json=dossier,
        content_sha256=canonical_sha256(dossier),
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def latest_dossier(db: AsyncSession, case_id: uuid.UUID) -> CaseDossier | None:
    return (
        await db.execute(
            select(CaseDossier)
            .where(CaseDossier.case_run_id == case_id)
            .order_by(CaseDossier.revision.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def case_exists(db: AsyncSession, case_id: uuid.UUID) -> bool:
    return (await db.execute(select(CaseRun.id).where(CaseRun.id == case_id))).first() is not None


def _chronology_view(loaded: LoadedCase) -> dict[str, Any]:
    inputs = case_inputs(loaded, revision=0)
    entries = chronology_entries(inputs)
    return {
        "case_id": str(loaded.case.id),
        "entries": [e.as_dict() for e in entries],
        "facts": inputs.facts,
    }


async def chronology_view(db: AsyncSession, case_id: uuid.UUID) -> dict[str, Any]:
    """Every proposal with its current decision (rejected ones included)."""
    return _chronology_view(await load_case(db, case_id))


async def update_chronology(
    db: AsyncSession, case_id: uuid.UUID, payload: dict[str, Any]
) -> dict[str, Any]:
    """Replace the case's chronology decisions and facts (PUT semantics).

    Raises ``ValueError`` for an invalid body (unknown entry id, bad date,
    unknown fact). Absent keys reset to empty: the body is the full state.
    """
    loaded = await load_case(db, case_id)
    known = {e.entry_id for e in chronology_entries(case_inputs(loaded, revision=0))}
    # Decisions apply to proposals only; user-added ids are re-issued on PUT.
    known = {i for i in known if i.startswith("chr-")}
    decisions, added = validate_update(payload, known)
    facts = validate_facts(payload.get("facts"))

    # Copy, never mutate in place: the column is plain JSON (no mutation
    # tracking), so only a new object marks it dirty.
    edits = copy.deepcopy(loaded.case.user_edits or {})
    edits[USER_EDITS_KEY] = {
        "decisions": decisions,
        "added": added,
        "facts": facts,
        "updated_at": datetime.now(UTC).isoformat(),
    }
    loaded.case.user_edits = edits
    # Build the response before committing: the commit expires the loaded
    # relationships, and lazy loads are not available on an async session.
    view = _chronology_view(loaded)
    await db.commit()
    return view
