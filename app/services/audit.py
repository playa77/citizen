"""Audit-logging helpers for pipeline execution — writes ``CaseRun``,
``PipelineStageLog``, ``Claim`` and ``EvidenceBinding`` rows to the
permanent store.

This module is invoked as a ``BackgroundTask`` after the SSE stream for an
analysis run has been fully sent to the client.  It persists the full audit
trail so that WP-015 acceptance criteria can be verified:

- ``pipeline_stage_log`` contains 7 rows (stages) + 1 row (disclaimer_ack)
- ``claim`` and ``evidence_binding`` tables are populated
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    CaseRun,
    Claim,
    EvidenceBinding,
    LegalChunk,
    PipelineStageLog,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data transfer object
# ---------------------------------------------------------------------------


@dataclass
class AuditRecord:
    """Container for data collected during one pipeline run."""

    session_id: str
    input_text: str
    status: str
    latency_ms: int
    stage_logs: list[dict[str, Any]] = field(default_factory=list)
    claims: list[dict[str, Any]] = field(default_factory=list)
    evidence_bindings: list[dict[str, Any]] = field(default_factory=list)
    disclaimer_ack: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def persist_audit_record(
    session: AsyncSession,
    record: AuditRecord,
) -> UUID:
    """Persist the full pipeline audit trail using *session*.

    Parameters
    ----------
    session :
        An active ``AsyncSession``.
    record :
        Populated ``AuditRecord`` collected during the run.

    Returns
    -------
    UUID
        The ``case_run.id`` primary key of the inserted row.
    """
    # -- CaseRun ------------------------------------------------------------
    case_run = CaseRun(
        session_id=record.session_id,
        input_text=record.input_text[:100_000],
        status=record.status,
        latency_ms=record.latency_ms,
    )
    session.add(case_run)
    await session.flush()  # ensures case_run.id is available

    # -- PipelineStageLog (7 stages) ---------------------------------------
    for entry in record.stage_logs:
        log = PipelineStageLog(
            case_run_id=case_run.id,
            stage_name=entry["stage_name"],
            input_snapshot=entry.get("input_snapshot"),
            output_snapshot=entry.get("output_snapshot"),
            duration_ms=entry["duration_ms"],
            error_trace=entry.get("error_trace"),
        )
        session.add(log)

    # -- disclaimer_ack (8th row) ------------------------------------------
    ack_data = record.disclaimer_ack
    if ack_data:
        disclaimer_log = PipelineStageLog(
            case_run_id=case_run.id,
            stage_name="disclaimer_ack",
            input_snapshot=ack_data.get("input_snapshot"),
            output_snapshot=ack_data.get("output_snapshot"),
            duration_ms=ack_data.get("duration_ms", 0),
            error_trace=None,
        )
        session.add(disclaimer_log)

    # -- Resolve chunk IDs by hierarchy_path for evidence bindings ---------
    chunk_id_map: dict[str, UUID | None] = {}
    for binding in record.evidence_bindings:
        hierarchy = binding.get("chunk_hierarchy", "")
        if hierarchy and hierarchy not in chunk_id_map:
            chunk_id_map[hierarchy] = await _resolve_chunk_id(session, hierarchy)

    # -- Claims -----------------------------------------------------------
    claims: list[Claim] = []
    for claim_data in record.claims:
        claim = Claim(
            case_run_id=case_run.id,
            claim_text=str(claim_data.get("claim_text", "")).strip(),
            confidence_score=float(claim_data.get("confidence_score", 0.0)),
            claim_type=str(claim_data.get("claim_type", "fact")),
        )
        session.add(claim)
        claims.append(claim)

    await session.flush()  # populates claim.id for server-default PKs

    # -- Evidence bindings --------------------------------------------------
    claim_ids = [c.id for c in claims]
    for binding in record.evidence_bindings:
        claim_idx = binding.get("claim_index", 0)
        if claim_idx >= len(claim_ids):
            continue  # safety bound

        hierarchy = binding.get("chunk_hierarchy", "")
        db_chunk_id = chunk_id_map.get(hierarchy)
        if db_chunk_id is None:
            continue  # skip unresolvable bindings

        eb = EvidenceBinding(
            claim_id=claim_ids[claim_idx],
            chunk_id=db_chunk_id,
            binding_strength=float(binding.get("binding_strength", 0.0)),
            quote_excerpt=str(binding.get("quote_excerpt", "")).strip(),
        )
        session.add(eb)

    await session.commit()
    logger.info(
        "Audit trail persisted: session_id=%s, stages=%d, " "claims=%d, bindings=%d",
        record.session_id,
        len(record.stage_logs) + (1 if record.disclaimer_ack else 0),
        len(record.claims),
        len(record.evidence_bindings),
    )
    return case_run.id


async def _resolve_chunk_id(session: AsyncSession, hierarchy: str) -> UUID | None:
    """Look up the ``legal_chunk.id`` for a given *hierarchy_path*.

    Parameters
    ----------
    session :
        Active ``AsyncSession``.
    hierarchy :
        The hierarchy path string (e.g. ``"SGB II > § 31 > Abs. 1"``).

    Returns
    -------
    UUID | None
        The UUID or ``None`` if no match.
    """
    result = await session.execute(
        select(LegalChunk.id)
        .where(
            LegalChunk.hierarchy_path == hierarchy,
        )
        .limit(1)
    )
    row = result.scalar_one_or_none()
    return row
