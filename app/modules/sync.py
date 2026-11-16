"""Registry → ``legal_module`` table sync (WP-94; ARCHITECTURE.md § 3.1, § 4).

At startup the registry writes one ``legal_module`` row per installed module
so audit records (``case_run_area.module_id`` / ``module_version``) can
reference a module id that exists in the database, and so the stored
enablement matches the running configuration.

Rules (D-057):

* insert a row for every installed module that has none;
* update ``version``, ``tier``, ``manifest_sha256`` and ``enabled`` of
  existing rows; ``installed_at`` is reset only when the manifest content
  changed (new ``manifest_sha256``) — it records when the current manifest
  was first seen, not the process start;
* never delete: a row whose module is no longer installed stays (case rows
  reference it) and is marked ``enabled = false``.

The caller owns the transaction (``sync_legal_modules`` flushes, the caller
commits).
"""

# Semantic Version: 1.0.0

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import LegalModule
from app.modules.registry import ModuleManifest, ModuleRegistry

logger = logging.getLogger(__name__)


def manifest_sha256(manifest: ModuleManifest) -> str:
    """SHA-256 of the manifest file bytes (identifies the installed manifest)."""
    return hashlib.sha256((manifest.path / "module.yaml").read_bytes()).hexdigest()


@dataclass(frozen=True)
class SyncReport:
    inserted: tuple[str, ...]
    updated: tuple[str, ...]
    unchanged: tuple[str, ...]
    disabled_uninstalled: tuple[str, ...]


async def sync_legal_modules(session: AsyncSession, registry: ModuleRegistry) -> SyncReport:
    """Upsert one ``legal_module`` row per installed module (see module docstring)."""
    existing = {row.id: row for row in (await session.execute(select(LegalModule))).scalars()}
    inserted: list[str] = []
    updated: list[str] = []
    unchanged: list[str] = []
    for module_id in sorted(registry.modules):
        manifest = registry.modules[module_id]
        digest = manifest_sha256(manifest)
        enabled = registry.is_enabled(module_id)
        row = existing.get(module_id)
        if row is None:
            session.add(
                LegalModule(
                    id=module_id,
                    version=manifest.version,
                    tier=manifest.tier,
                    manifest_sha256=digest,
                    enabled=enabled,
                )
            )
            inserted.append(module_id)
            continue
        current = (row.version, row.tier, row.manifest_sha256, row.enabled)
        if current == (manifest.version, manifest.tier, digest, enabled):
            unchanged.append(module_id)
            continue
        if row.manifest_sha256 != digest:
            row.installed_at = func.now()
        row.version = manifest.version
        row.tier = manifest.tier
        row.manifest_sha256 = digest
        row.enabled = enabled
        updated.append(module_id)

    disabled: list[str] = []
    for module_id, row in sorted(existing.items()):
        if module_id not in registry.modules and row.enabled:
            row.enabled = False
            disabled.append(module_id)

    await session.flush()
    report = SyncReport(tuple(inserted), tuple(updated), tuple(unchanged), tuple(disabled))
    logger.info(
        "legal_module sync: inserted=%s updated=%s unchanged=%d disabled(uninstalled)=%s",
        list(report.inserted),
        list(report.updated),
        len(report.unchanged),
        list(report.disabled_uninstalled),
    )
    return report


__all__ = ["SyncReport", "manifest_sha256", "sync_legal_modules"]
