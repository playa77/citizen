"""WP-94: registry → legal_module sync and the case_run_area module binding.

The sync tests run against the migrated test database inside a transaction
that is rolled back, so the shared ``legal_module`` rows stay untouched.
"""

# Semantic Version: 1.0.0

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
import yaml
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.db.models import LegalModule
from app.modules.registry import default_modules_root, load_registry
from app.modules.runtime import UnknownAreaKeyError, area_module_binding, get_manifest
from app.modules.sync import manifest_sha256, sync_legal_modules


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(os.environ["DATABASE_URL"], poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            outer = await conn.begin()
            db = AsyncSession(bind=conn, expire_on_commit=False)
            try:
                yield db
            finally:
                await db.close()
                await outer.rollback()
    finally:
        await engine.dispose()


def _write_module(root: Path, module_id: str, version: str, tier: str = "verified") -> None:
    module_dir = root / module_id
    module_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "id": module_id,
        "version": version,
        "core_api": ">=3.0,<4.0",
        "title": {"de": "T", "en": "T"},
        "tier": tier,
    }
    (module_dir / "module.yaml").write_text(yaml.safe_dump(manifest), encoding="utf-8")


async def _rows(db: AsyncSession) -> dict[str, LegalModule]:
    return {r.id: r for r in (await db.execute(select(LegalModule))).scalars()}


class TestSync:
    async def test_in_tree_modules_synced(self, session: AsyncSession) -> None:
        registry = load_registry(default_modules_root(), "provider", None, "sozialrecht")
        report = await sync_legal_modules(session, registry)
        rows = await _rows(session)
        assert set(registry.modules) <= set(rows)
        for module_id, manifest in registry.modules.items():
            row = rows[module_id]
            assert (row.version, row.tier) == (manifest.version, manifest.tier)
            assert row.manifest_sha256 == manifest_sha256(manifest)
            assert row.enabled is registry.is_enabled(module_id)
        # provider mode: verified only (D-037)
        assert rows["sozialrecht"].enabled and not rows["mietrecht"].enabled
        # second run is a no-op
        again = await sync_legal_modules(session, registry)
        assert again.inserted == again.updated == ()
        assert set(again.unchanged) == set(registry.modules)
        assert set(report.inserted) | set(report.updated) | set(report.unchanged) == set(
            registry.modules
        )

    async def test_insert_update_and_uninstalled(
        self, session: AsyncSession, tmp_path: Path
    ) -> None:
        _write_module(tmp_path, "demo_sync", "0.1.0")
        registry = load_registry(tmp_path, "dev", None, "demo_sync")
        report = await sync_legal_modules(session, registry)
        assert report.inserted == ("demo_sync",)
        # every previously synced in-tree module is now "uninstalled": kept, disabled
        rows = await _rows(session)
        assert "sozialrecht" in rows and rows["sozialrecht"].enabled is False

        await session.execute(
            text("UPDATE legal_module SET installed_at = '2000-01-01' WHERE id = 'demo_sync'")
        )
        session.expire_all()
        _write_module(tmp_path, "demo_sync", "0.2.0")
        registry = load_registry(tmp_path, "dev", None, "demo_sync")
        report = await sync_legal_modules(session, registry)
        assert report.updated == ("demo_sync",)
        session.expire_all()
        row = (await _rows(session))["demo_sync"]
        assert row.version == "0.2.0"
        assert row.installed_at.year > 2000  # new manifest → new install time

    async def test_enablement_change_keeps_installed_at(
        self, session: AsyncSession, tmp_path: Path
    ) -> None:
        _write_module(tmp_path, "demo_a", "1.0.0")
        _write_module(tmp_path, "demo_b", "1.0.0", tier="experimental")
        await sync_legal_modules(session, load_registry(tmp_path, "dev", None, "demo_a"))
        await session.execute(
            text("UPDATE legal_module SET installed_at = '2000-01-01' WHERE id = 'demo_b'")
        )
        session.expire_all()
        report = await sync_legal_modules(
            session, load_registry(tmp_path, "provider", None, "demo_a")
        )
        assert report.updated == ("demo_b",)
        session.expire_all()
        row = (await _rows(session))["demo_b"]
        assert row.enabled is False
        assert row.installed_at.year == 2000  # same manifest → install time kept


class TestAreaModuleBinding:
    @pytest.mark.parametrize(
        ("key", "module_id"),
        [
            ("sozialrecht", "sozialrecht"),
            ("schenkungsrecht", "erbrecht"),  # legacy alias (D-038)
            ("andere", "andere"),
        ],
    )
    def test_module_keys(self, key: str, module_id: str) -> None:
        assert area_module_binding(key) == (module_id, get_manifest(module_id).version)

    def test_procedural_key_has_no_module(self) -> None:
        assert area_module_binding("verwaltungsrecht") == (None, None)

    def test_unknown_key_raises(self) -> None:
        with pytest.raises(UnknownAreaKeyError):
            area_module_binding("no_such_area")


def test_binding_and_migration_backfill_agree() -> None:
    """Migration 013's frozen backfill map equals today's runtime binding for
    every v2.0.0 key, so old and new rows bind the same way."""
    import importlib.util

    path = Path(__file__).resolve().parents[2] / "alembic/versions/013_legal_module.py"
    spec = importlib.util.spec_from_file_location("_mig_013_binding", path)
    assert spec is not None and spec.loader is not None
    mig: Any = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mig)
    for key in mig._V2_AREA_KEYS:
        expected = mig._KEY_TO_MODULE_EXCEPTIONS.get(key, key)
        assert area_module_binding(key)[0] == expected
    seeded = {mid for mid, _, _ in mig._SEED_MODULES}
    assert seeded == {m for m in (area_module_binding(k)[0] for k in mig._V2_AREA_KEYS) if m}
