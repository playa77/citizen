"""Module catalog endpoints (WP-95; ARCHITECTURE.md § 5, D-039).

Provides:
    GET /api/v1/modules                      — installed modules (summary)
    GET /api/v1/modules/{module_id}          — public manifest parts, deadline
                                               catalog, document types
    GET /api/v1/modules/{module_id}/goldset  — the module's declared goldset
                                               (manifest + case summaries)

Read-only views over the running module registry. Every field is module
data or registry state; the routes contain no area-specific logic. Only
*public* manifest parts are served: file paths and code references
(``corpus``, ``calculators``, ``regimes.provider``, …) are reduced to
capability flags.

Database-backed fields degrade instead of failing: when the database is
unreachable, ``corpus`` and ``installed_at`` are ``null`` — the catalog
itself comes from the filesystem and stays available.
"""

# Semantic Version: 1.0.0 | 2026-11-16 — WP-95: initial version.

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.api.routes.goldset import goldset_listing, load_goldset_file
from app.db.models import LegalModule
from app.db.session import async_session_factory
from app.fristen.specs import DeadlineSpec, Duration
from app.modules.areas import area_tables
from app.modules.content import module_path
from app.modules.registry import ModuleManifest
from app.modules.runtime import (
    MODULE_UNKNOWN,
    deadline_specs,
    document_templates,
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
        "title": dict(manifest.title),
        "area_keys": _area_keys(manifest.id),
        "corpus": (
            source_type_status(_module_source_types(manifest.id), by_source)
            if by_source is not None
            else None
        ),
        "installed_at": _installed_at(manifest, rows),
    }


def _duration(duration: Duration) -> dict[str, int]:
    return {"days": duration.days, "months": duration.months, "years": duration.years}


def _deadline(spec: DeadlineSpec) -> dict[str, Any]:
    return {
        "id": spec.id,
        "label_de": spec.label_de,
        "trigger": spec.trigger,
        "duration": _duration(spec.duration),
        "basis": spec.basis,
        "fristbeginn_basis": spec.fristbeginn_basis,
        "bekanntgabe_fiction": spec.bekanntgabe_fiction,
        "rollover": spec.rollover,
        "missing_rechtsbehelfsbelehrung": (
            {
                "duration": _duration(spec.missing_rechtsbehelfsbelehrung.duration),
                "basis": spec.missing_rechtsbehelfsbelehrung.basis,
            }
            if spec.missing_rechtsbehelfsbelehrung is not None
            else None
        ),
        "severity": spec.severity,
        "applies_when": dict(spec.applies_when),
    }


def _document_types(manifest: ModuleManifest) -> list[dict[str, Any]]:
    """Declared action-draft types with their template titles (if any)."""
    templates = (document_templates(manifest.id) or {}).get("templates") or {}
    result: list[dict[str, Any]] = []
    for doc_id in manifest.raw.get("documents") or []:
        template = templates.get(doc_id) or {}
        result.append({"id": doc_id, "title": template.get("title")})
    return result


def _public_compliance(manifest: ModuleManifest) -> dict[str, Any] | None:
    """Public compliance facts (referral duty, special regimes); no file paths."""
    compliance = manifest.raw.get("compliance")
    if not isinstance(compliance, dict):
        return None
    referral = compliance.get("referral")
    return {
        "special_regimes": list(compliance.get("special_regimes") or []),
        "referral": dict(referral) if isinstance(referral, dict) else None,
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
    scope = raw.get("scope") or {}
    parameters = raw.get("parameters")
    goldset = raw.get("goldset")
    return {
        **_summary(manifest, by_source, rows),
        "core_api": manifest.core_api,
        "scope": {
            "summary_de": scope.get("summary_de"),
            "own_matter_only": scope.get("own_matter_only"),
            "out_of_scope": list(scope.get("out_of_scope") or []),
        },
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
        "deadlines": [_deadline(spec) for spec in deadline_specs(manifest.id)],
        "document_types": _document_types(manifest),
        # Dossier checklists arrive with roadmap P10 (WP-102); until a module
        # declares a `dossier` file this stays null.
        "dossier_checklist": None,
        "compliance": _public_compliance(manifest),
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
