"""Module catalog endpoints (WP-95; ARCHITECTURE.md § 5, D-039).

Provides:
    GET /api/v1/modules                      — installed modules (summary)
    GET /api/v1/modules/{module_id}          — public manifest parts, deadline
                                               catalog, document types
    GET /api/v1/modules/{module_id}/goldset  — the module's declared goldset
                                               (manifest + case summaries)
    GET /api/v1/modules/{module_id}/errata/{erratum_id}/cases
                                             — stored cases whose recorded
                                               module version an erratum
                                               affects (WP-110)

Read-only views over the running module registry. Every field is module
data or registry state; the routes contain no area-specific logic. Only
*public* manifest parts are served: file paths and code references
(``corpus``, ``calculators``, ``regimes.provider``, …) are reduced to
capability flags.

Database-backed fields degrade instead of failing: when the database is
unreachable, ``corpus`` and ``installed_at`` are ``null`` — the catalog
itself comes from the filesystem and stays available.
"""

# Semantic Version: 1.2.0 | 2026-11-17 — WP-110: `errata` on the module detail,
# affected-cases route; WP-111: `updates`, `parameter_set`; WP-112: `origin`/
# `declared_tier` in the summary; WP-116: catalog helpers moved to app/modules/catalog.py.
# 1.1.0 | 2026-11-16 — P10: dossier_checklist served from the
# module's dossier.yaml.
# 1.0.0 | 2026-11-16 — WP-95: initial version.

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.api.routes.goldset import goldset_listing, load_goldset_file
from app.db.models import CaseRun, CaseRunArea, LegalModule, ModuleUpdate
from app.db.session import async_session_factory
from app.dossier.module_content import public_dossier_checklist
from app.modules.areas import area_tables
from app.modules.catalog import document_types, module_deadlines, public_compliance, public_scope
from app.modules.content import module_path
from app.modules.errata import Erratum, module_errata
from app.modules.registry import ModuleManifest
from app.modules.runtime import (
    MODULE_UNKNOWN,
    module_provenance,
    module_registry,
)
from app.modules.sync import manifest_sha256
from app.services.corpus_readiness import chunk_counts_by_source_type, source_type_status

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _manifest_or_404(module_id: str) -> ModuleManifest:
    manifest = module_registry().get(module_id)
    if manifest is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": MODULE_UNKNOWN,
                "message": f"Modul '{module_id}' ist nicht installiert.",
                "module_id": module_id,
            },
        )
    return manifest


def _ordered_module_ids() -> list[str]:
    """Installed module ids: owners in area-key order, key-less modules last."""
    tables = area_tables()
    ordered: list[str] = []
    for key in tables.keys:
        owner = tables.owner[key]
        if owner in module_registry().modules and owner not in ordered:
            ordered.append(owner)
    ordered.extend(sorted(set(module_registry().modules) - set(ordered)))
    return ordered


def _area_keys(module_id: str) -> list[str]:
    tables = area_tables()
    return [key for key in tables.keys if tables.owner[key] == module_id]


def _module_source_types(module_id: str) -> tuple[str, ...]:
    """Union of the owned area keys' source types, first-seen order."""
    tables = area_tables()
    seen: list[str] = []
    for key in _area_keys(module_id):
        for source_type in tables.source_types.get(key, ()):
            if source_type not in seen:
                seen.append(source_type)
    return tuple(seen)


async def _db_state() -> tuple[dict[str, int] | None, dict[str, LegalModule] | None]:
    """Chunk counts per source type and ``legal_module`` rows, or ``None``s."""
    try:
        async with async_session_factory() as session:
            by_source = await chunk_counts_by_source_type(session)
            rows = (await session.execute(select(LegalModule))).scalars().all()
            return by_source, {row.id: row for row in rows}
    except (SQLAlchemyError, OSError) as exc:
        logger.warning("module catalog: database unavailable (%s); corpus/installed_at null", exc)
        return None, None


async def _applied_updates(module_id: str) -> list[dict[str, Any]] | None:
    """Applied signed update feeds of a module (WP-111), newest first; ``None``
    when the database is unreachable."""
    try:
        async with async_session_factory() as session:
            rows = (
                (
                    await session.execute(
                        select(ModuleUpdate)
                        .where(ModuleUpdate.module_id == module_id)
                        .order_by(ModuleUpdate.serial.desc())
                    )
                )
                .scalars()
                .all()
            )
    except (SQLAlchemyError, OSError) as exc:
        logger.warning("module catalog: update ledger unavailable (%s); updates null", exc)
        return None
    return [
        {
            "serial": row.serial,
            "issued_at": row.issued_at.isoformat(),
            "applied_at": row.applied_at.isoformat(),
            "key_id": row.key_id,
            "module_version": row.module_version,
            "parameters": [
                {k: p.get(k) for k in ("key", "valid_from", "erratum", "action")}
                for p in row.parameters
            ],
            "corpus_notices": list(row.corpus_notices),
        }
        for row in rows
    ]


def _installed_at(manifest: ModuleManifest, rows: dict[str, LegalModule] | None) -> str | None:
    """``legal_module.installed_at`` if the row describes the running manifest.

    A row from an older manifest (startup sync failed or has not run) does
    not date the installed one, so it is reported as ``null``.
    """
    row = (rows or {}).get(manifest.id)
    if row is None or row.manifest_sha256 != manifest_sha256(manifest):
        return None
    installed_at: datetime = row.installed_at
    return installed_at.isoformat()


def _summary(
    manifest: ModuleManifest,
    by_source: dict[str, int] | None,
    rows: dict[str, LegalModule] | None,
) -> dict[str, Any]:
    registry = module_registry()
    return {
        "id": manifest.id,
        "version": manifest.version,
        "tier": manifest.tier,
        "enabled": registry.is_enabled(manifest.id),
        "is_default": manifest.id == registry.default_module,
        # WP-112: "in_tree" (reviewed, ships with the core) or "entry_point"
        # (installed package, tier clamped to community).
        "origin": manifest.origin,
        "declared_tier": manifest.declared_tier or manifest.tier,
        "title": dict(manifest.title),
        "area_keys": _area_keys(manifest.id),
        "corpus": (
            source_type_status(_module_source_types(manifest.id), by_source)
            if by_source is not None
            else None
        ),
        "installed_at": _installed_at(manifest, rows),
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/modules")
async def list_modules() -> dict[str, Any]:
    """List every installed module with enablement and corpus readiness."""
    registry = module_registry()
    by_source, rows = await _db_state()
    return {
        "default_module": registry.default_module,
        "modules": [
            _summary(registry.modules[module_id], by_source, rows)
            for module_id in _ordered_module_ids()
        ],
    }


@router.get("/modules/{module_id}")
async def get_module(module_id: str) -> dict[str, Any]:
    """Public manifest parts, deadline catalog and document types of a module."""
    manifest = _manifest_or_404(module_id)
    by_source, rows = await _db_state()
    raw = manifest.raw
    parameters = raw.get("parameters")
    goldset = raw.get("goldset")
    return {
        **_summary(manifest, by_source, rows),
        "core_api": manifest.core_api,
        "scope": public_scope(manifest),
        "legacy_aliases": list(manifest.legacy_aliases),
        "capabilities": {
            "deadlines": isinstance(raw.get("fristen"), str),
            "calculators": isinstance(raw.get("calculators"), str),
            "regime_provider": isinstance(raw.get("regimes"), dict),
            "document_templates": isinstance(raw.get("document_templates"), str),
            "goldset": isinstance(goldset, dict),
            "dossier": isinstance(raw.get("dossier"), str),
        },
        "parameter_domain": (str(parameters["domain"]) if isinstance(parameters, dict) else None),
        "deadlines": module_deadlines(manifest.id),
        "document_types": document_types(manifest),
        # P10 (WP-102): the module's dossier.yaml checklist + question list;
        # null for a module that declares no `dossier` file.
        "dossier_checklist": public_dossier_checklist(manifest.id),
        "compliance": public_compliance(manifest),
        # WP-110: published corrections; affected stored cases via
        # GET /modules/{id}/errata/{erratum_id}/cases.
        "errata": [erratum.as_dict() for erratum in module_errata(manifest)],
        # WP-111: applied signed update feeds (parameter sets, corpus notices).
        "updates": await _applied_updates(manifest.id),
        "parameter_set": module_provenance(manifest.id)[2],
    }


@router.get("/modules/{module_id}/goldset")
async def get_module_goldset(module_id: str) -> dict[str, Any]:
    """The module's declared goldset: manifest + case summaries + eval gate.

    Same ``goldset``/``cases`` shape as ``GET /api/v1/goldset``. Serves the
    goldset the module manifest declares, which may be a newer version than
    the one ``/api/v1/goldset`` serves (``GOLDSET_PATH``, D-056).
    """
    manifest = _manifest_or_404(module_id)
    declared = manifest.raw.get("goldset")
    if not isinstance(declared, dict):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "goldset_not_declared",
                "message": f"Modul '{module_id}' deklariert kein Goldset.",
                "module_id": module_id,
            },
        )
    path: Path = module_path(manifest, str(declared["path"]))
    try:
        doc = load_goldset_file(path)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Goldset nicht gefunden: {exc}",
        ) from exc
    except Exception as exc:
        logger.exception("Failed to load goldset of module %s", module_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Goldset konnte nicht geladen werden: {exc}",
        ) from exc
    gate = declared.get("gate")
    return {
        "module_id": manifest.id,
        "module_version": manifest.version,
        "gate": dict(gate) if isinstance(gate, dict) else None,
        **goldset_listing(doc),
    }


def _erratum_or_404(manifest: ModuleManifest, erratum_id: str) -> Erratum:
    for erratum in module_errata(manifest):
        if erratum.id == erratum_id:
            return erratum
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={
            "error": "erratum_unknown",
            "message": f"Modul '{manifest.id}' hat kein Erratum '{erratum_id}'.",
            "module_id": manifest.id,
            "erratum_id": erratum_id,
        },
    )


@router.get("/modules/{module_id}/errata/{erratum_id}/cases")
async def get_erratum_cases(module_id: str, erratum_id: str) -> dict[str, Any]:
    """Stored cases that ran with a module version the erratum affects.

    Matches ``case_run_area.module_id`` + ``module_version`` (D-057) against
    the erratum's ``affected_versions`` range; version comparison is semver,
    done here rather than in SQL. One entry per (case, area key).
    """
    manifest = _manifest_or_404(module_id)
    erratum = _erratum_or_404(manifest, erratum_id)
    async with async_session_factory() as session:
        rows = (
            await session.execute(
                select(
                    CaseRunArea.case_run_id,
                    CaseRunArea.legal_area,
                    CaseRunArea.module_version,
                    CaseRun.created_at,
                    CaseRun.title,
                )
                .join(CaseRun, CaseRun.id == CaseRunArea.case_run_id)
                .where(CaseRunArea.module_id == manifest.id)
                .order_by(CaseRun.created_at, CaseRunArea.case_run_id)
            )
        ).all()
    cases = [
        {
            "case_id": str(row.case_run_id),
            "legal_area": row.legal_area,
            "module_version": row.module_version,
            "created_at": row.created_at.isoformat(),
            "title": row.title,
        }
        for row in rows
        if erratum.affects(row.module_version)
    ]
    return {
        "module_id": manifest.id,
        "module_version": manifest.version,
        "erratum": erratum.as_dict(),
        "count": len(cases),
        "cases": cases,
    }
