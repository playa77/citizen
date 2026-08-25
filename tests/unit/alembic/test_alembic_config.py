"""Unit tests for WP-004: Alembic configuration and migration integrity.

Tests that do NOT require a live database:
- alembic.ini exists and has required sections
- alembic/env.py is valid Python
- Migration revision chain is valid
- Migration contains expected table creation
"""

# Semantic Version: 0.1.0

from __future__ import annotations

import ast
import configparser
import importlib
import importlib.util
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]


# ---------------------------------------------------------------------------
# Fixtures for module loading from disk (outside sys.path)
# ---------------------------------------------------------------------------


def _load_module_from_path(module_name: str, file_path: Path) -> object:
    spec = importlib.util.spec_from_file_location(module_name, str(file_path))
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# 1. alembic.ini
# ---------------------------------------------------------------------------


class TestAlembicIni:
    def test_file_exists(self) -> None:
        assert (PROJECT_ROOT / "alembic.ini").is_file()

    def test_alembic_section(self) -> None:
        cfg = configparser.ConfigParser()
        cfg.read(PROJECT_ROOT / "alembic.ini")
        assert "alembic" in cfg.sections()

    def test_script_location(self) -> None:
        cfg = configparser.ConfigParser()
        cfg.read(PROJECT_ROOT / "alembic.ini")
        assert cfg.get("alembic", "script_location") == "alembic"

    def test_async_driver_in_url(self) -> None:
        cfg = configparser.ConfigParser()
        cfg.read(PROJECT_ROOT / "alembic.ini")
        url = cfg.get("alembic", "sqlalchemy.url")
        assert "asyncpg" in url, f"Expected asyncpg driver in URL, got: {url}"


# ---------------------------------------------------------------------------
# 2. alembic/env.py
# ---------------------------------------------------------------------------


class TestAlembicEnv:
    def test_file_exists(self) -> None:
        assert (PROJECT_ROOT / "alembic" / "env.py").is_file()

    def test_valid_python(self) -> None:
        path = PROJECT_ROOT / "alembic" / "env.py"
        source = path.read_text()
        ast.parse(source)  # raises SyntaxError if invalid

    def test_imports_models_base(self) -> None:
        source = (PROJECT_ROOT / "alembic" / "env.py").read_text()
        assert "app.db.models" in source or "from app.db.models import" in source

    def test_async_migrations_function(self) -> None:
        source = (PROJECT_ROOT / "alembic" / "env.py").read_text()
        assert "run_async_migrations" in source

    def test_context_configure_called(self) -> None:
        source = (PROJECT_ROOT / "alembic" / "env.py").read_text()
        assert "context.configure" in source

    def test_target_metadata(self) -> None:
        """env.py must reference Base.metadata for autogenerate support."""
        source = (PROJECT_ROOT / "alembic" / "env.py").read_text()
        assert "target_metadata" in source


# ---------------------------------------------------------------------------
# 3. alembic/script.py.mako
# ---------------------------------------------------------------------------


class TestAlembicMakoTemplate:
    def test_file_exists(self) -> None:
        assert (PROJECT_ROOT / "alembic" / "script.py.mako").is_file()

    def test_template_placeholders(self) -> None:
        source = (PROJECT_ROOT / "alembic" / "script.py.mako").read_text()
        assert "upgrade" in source
        assert "downgrade" in source


# ---------------------------------------------------------------------------
# 4. Initial migration (alembic/versions/001_init_schema.py)
# ---------------------------------------------------------------------------


class TestInitialMigration:
    def test_file_exists(self) -> None:
        path = PROJECT_ROOT / "alembic" / "versions" / "001_init_schema.py"
        assert path.is_file()

    def test_valid_python(self) -> None:
        source = (PROJECT_ROOT / "alembic" / "versions" / "001_init_schema.py").read_text()
        ast.parse(source)

    def test_revision_id(self) -> None:
        """001 is a root migration — down_revision must be None."""
        mod = _load_module_from_path(
            "_001_init_schema",
            PROJECT_ROOT / "alembic" / "versions" / "001_init_schema.py",
        )
        assert hasattr(mod, "revision")
        assert mod.revision == "001_init_schema"
        assert mod.down_revision is None

    def test_upgrade_creates_all_tables(self) -> None:
        source = (PROJECT_ROOT / "alembic" / "versions" / "001_init_schema.py").read_text()
        expected_tables = [
            "legal_source",
            "legal_chunk",
            "chunk_embedding",
            "case_run",
            "pipeline_stage_log",
            "claim",
            "evidence_binding",
        ]
        for table in expected_tables:
            assert f'"{table}"' in source, f"Migration must create {table}"
            assert "upgrade()" in source

    def test_downgrade_drops_all_tables(self) -> None:
        source = (PROJECT_ROOT / "alembic" / "versions" / "001_init_schema.py").read_text()
        expected_tables = [
            "legal_source",
            "legal_chunk",
            "chunk_embedding",
            "case_run",
            "pipeline_stage_log",
            "claim",
            "evidence_binding",
        ]
        for table in expected_tables:
            assert f'drop_table("{table}")' in source, f"Migration must drop {table}"

    def test_pgvector_extension_enabled(self) -> None:
        source = (PROJECT_ROOT / "alembic" / "versions" / "001_init_schema.py").read_text()
        assert "CREATE EXTENSION" in source
        assert "vector" in source


# ---------------------------------------------------------------------------
# 5. Single linear migration DAG (D-024) — no DB required
# ---------------------------------------------------------------------------


class TestSingleMigrationDag:
    """Guard G2: exactly one head, one root, fully connected linear chain."""

    def _load_all_migrations(self) -> list[object]:
        versions = sorted((PROJECT_ROOT / "alembic" / "versions").glob("*.py"))
        assert versions, "No migration files found"
        return [
            _load_module_from_path(f"_mig_{f.stem}", f)
            for f in versions
            if f.stem != "__init__"
        ]

    def test_exactly_one_root(self) -> None:
        mods = self._load_all_migrations()
        roots = [m for m in mods if getattr(m, "down_revision", "x") is None]
        assert len(roots) == 1, f"Expected exactly one root migration, got {len(roots)}"

    def test_exactly_one_head(self) -> None:
        mods = self._load_all_migrations()
        revisions = {m.revision for m in mods}
        heads = [
            m
            for m in mods
            if not any(m.revision == other.down_revision for other in mods)
        ]
        assert len(heads) == 1, (
            f"Expected exactly one head revision, got {len(heads)}: "
            f"{[h.revision for h in heads]}; all revisions: {revisions}"
        )

    def test_chain_fully_connected(self) -> None:
        """Every down_revision must reference an existing revision (or be None)."""
        mods = self._load_all_migrations()
        revisions = {m.revision for m in mods}
        for m in mods:
            down = m.down_revision
            if down is None:
                continue
            assert down in revisions, f"{m.revision} points to missing revision {down}"

    def test_no_sqlite_branch_files(self) -> None:
        """The former SQLite chain must stay deleted (G2 regression guard)."""
        versions_dir = PROJECT_ROOT / "alembic" / "versions"
        for stale in [
            "007_sqlite_baseline.py",
            "008_fix_stage_name_allowed.py",
            "009_add_regime_and_notes_to_legal_parameter.py",
            "010_add_pii_mapping_to_case_run.py",
            "011_sqlite_legal_chunk_text_hash.py",
        ]:
            assert not (versions_dir / stale).exists(), f"Stale SQLite-branch file: {stale}"

    def test_collapse_migration_carries_former_sqlite_schema(self) -> None:
        """012 must contain the schema content of deleted 008/009/010."""
        source = (
            PROJECT_ROOT / "alembic" / "versions" / "012_pg_collapse_sqlite_branch.py"
        ).read_text()
        for fragment in [
            "ck_pipeline_stage_log_stage_name",
            "regime",
            "notes",
            "pii_mapping",
        ]:
            assert fragment in source, f"Collapse migration missing: {fragment}"
