"""Unit tests for WP-004: Alembic configuration and migration integrity.

Tests that do NOT require a live database:
- alembic.ini exists and has required sections
- alembic/env.py is valid Python
- Migration revision chain is valid
- Migration contains expected table creation
"""

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
