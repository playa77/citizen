"""WP-94: migration 013 (legal_module, case_run_area module binding, domain rewrite).

Runs the real Alembic chain against throw-away databases created on the test
server (the session database is never migrated up or down here):

* exit criterion "fresh and upgraded DBs identical": a database migrated to
  ``012`` holding v2.0.0 data and then upgraded must equal a database
  migrated straight to head — schema (columns, constraints, indexes) and the
  migration-owned data (``legal_module`` seed rows, ``legal_parameter``
  domains);
* backfill of ``case_run_area.module_id`` from the frozen key → module map;
* idempotent replay (D-005/D-027): re-running 013 on an upgraded database;
* downgrade → upgrade round trip;
* the ORM model of the WP-94 tables matches the migrated schema.
"""

# Semantic Version: 1.0.0

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import asyncpg
import pytest
from sqlalchemy.engine import make_url

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _url(dbname: str) -> str:
    url = make_url(os.environ["DATABASE_URL"]).set(database=dbname)
    return url.render_as_string(hide_password=False)


def _dsn(dbname: str) -> str:
    return _url(dbname).replace("postgresql+asyncpg://", "postgresql://", 1)


def _admin(sql: str) -> None:
    async def run() -> None:
        conn = await asyncpg.connect(_dsn(make_url(os.environ["DATABASE_URL"]).database or ""))
        try:
            await conn.execute(sql)
        finally:
            await conn.close()

    asyncio.run(run())


def _alembic(dbname: str, *args: str) -> None:
    env = {**os.environ, "DATABASE_URL": _url(dbname)}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode == 0, f"alembic {' '.join(args)} failed:\n{result.stderr}"


def _query(dbname: str, sql: str, *args: Any) -> list[tuple[Any, ...]]:
    async def run() -> list[tuple[Any, ...]]:
        conn = await asyncpg.connect(_dsn(dbname))
        try:
            return [tuple(r) for r in await conn.fetch(sql, *args)]
        finally:
            await conn.close()

    return asyncio.run(run())


def _execute(dbname: str, sql: str) -> None:
    async def run() -> None:
        conn = await asyncpg.connect(_dsn(dbname))
        try:
            await conn.execute(sql)
        finally:
            await conn.close()

    asyncio.run(run())


def _schema(dbname: str) -> dict[str, list[tuple[Any, ...]]]:
    """Comparable schema snapshot of the public schema."""
    return {
        "columns": _query(
            dbname,
            "SELECT table_name, column_name, data_type, character_maximum_length, "
            "is_nullable, column_default FROM information_schema.columns "
            "WHERE table_schema = 'public' ORDER BY 1, 2",
        ),
        "constraints": _query(
            dbname,
            "SELECT conrelid::regclass::text, conname, pg_get_constraintdef(oid) "
            "FROM pg_constraint WHERE connamespace = 'public'::regnamespace ORDER BY 1, 2",
        ),
        "indexes": _query(
            dbname,
            "SELECT tablename, indexname, indexdef FROM pg_indexes "
            "WHERE schemaname = 'public' ORDER BY 1, 2",
        ),
    }


def _owned_data(dbname: str) -> dict[str, list[tuple[Any, ...]]]:
    return {
        "legal_module": _query(
            dbname,
            "SELECT id, version, tier, manifest_sha256, enabled FROM legal_module ORDER BY id",
        ),
        "legal_parameter": _query(
            dbname,
            "SELECT parameter_key, domain, valid_from FROM legal_parameter ORDER BY 1, 3",
        ),
    }


# v2.0.0 case rows written before WP-94: (area key, expected module_id).
_LEGACY_ROWS = (
    ("sozialrecht", "sozialrecht"),
    ("schenkungsrecht", "erbrecht"),
    ("verwaltungsrecht", None),
    ("andere", "andere"),
)


def _insert_v2_data(dbname: str) -> uuid.UUID:
    case_id = uuid.uuid4()
    rows = ", ".join(
        f"('{uuid.uuid4()}', '{case_id}', '{key}', {str(i == 0).lower()})"
        for i, (key, _) in enumerate(_LEGACY_ROWS)
    )
    _execute(
        dbname,
        "INSERT INTO case_run (id, session_id, input_text, status) "
        f"VALUES ('{case_id}', 'wp94-test', 'synthetic', 'completed'); "
        f"INSERT INTO case_run_area (id, case_run_id, legal_area, is_primary) VALUES {rows}",
    )
    return case_id


@pytest.fixture(scope="module")
def databases() -> Iterator[tuple[str, str]]:
    suffix = uuid.uuid4().hex[:8]
    fresh, upgraded = f"wp94_fresh_{suffix}", f"wp94_upgraded_{suffix}"
    for name in (fresh, upgraded):
        _admin(f"CREATE DATABASE {name}")
    try:
        _alembic(fresh, "upgrade", "head")
        _alembic(upgraded, "upgrade", "012_pg_collapse_sqlite_branch")
        _insert_v2_data(upgraded)
        _alembic(upgraded, "upgrade", "head")
        yield fresh, upgraded
    finally:
        for name in (fresh, upgraded):
            _admin(f"DROP DATABASE IF EXISTS {name} WITH (FORCE)")


def test_fresh_and_upgraded_are_identical(databases: tuple[str, str]) -> None:
    fresh, upgraded = databases
    assert _schema(fresh) == _schema(upgraded)
    assert _owned_data(fresh) == _owned_data(upgraded)


def test_upgrade_shape(databases: tuple[str, str]) -> None:
    fresh, _ = databases
    constraints = {name for _, name, _ in _schema(fresh)["constraints"]}
    assert "ck_case_run_area_legal_area" not in constraints
    assert {"fk_case_run_area_module_id", "ck_legal_module_tier"} <= constraints
    modules = _owned_data(fresh)["legal_module"]
    assert [m[0] for m in modules] == sorted(
        [
            "sozialrecht",
            "erbrecht",
            "familienrecht",
            "mietrecht",
            "arbeitsrecht",
            "vertragsrecht",
            "strafrecht",
            "andere",
        ]
    )
    assert all(m[3] is None and m[4] is False for m in modules)  # unsynced seed rows
    domains = {d for _, d, _ in _owned_data(fresh)["legal_parameter"]}
    assert domains == {"sozialrecht"}
    default = _query(
        fresh,
        "SELECT column_default FROM information_schema.columns "
        "WHERE table_name = 'legal_parameter' AND column_name = 'domain'",
    )
    assert default == [(None,)]


def test_backfill_maps_legacy_keys(databases: tuple[str, str]) -> None:
    _, upgraded = databases
    rows = dict(
        _query(upgraded, "SELECT legal_area, module_id FROM case_run_area")  # type: ignore[arg-type]
    )
    assert rows == dict(_LEGACY_ROWS)
    versions = _query(upgraded, "SELECT DISTINCT module_version FROM case_run_area")
    assert versions == [(None,)]  # not recorded before WP-94


def test_fk_rejects_unknown_module(databases: tuple[str, str]) -> None:
    fresh, _ = databases
    case_id = uuid.uuid4()
    with pytest.raises(asyncpg.ForeignKeyViolationError):
        _execute(
            fresh,
            "INSERT INTO case_run (id, session_id, input_text, status) "
            f"VALUES ('{case_id}', 'wp94-fk', 'synthetic', 'completed'); "
            "INSERT INTO case_run_area (id, case_run_id, legal_area, module_id) "
            f"VALUES ('{uuid.uuid4()}', '{case_id}', 'x', 'no_such_module')",
        )


def test_replay_is_idempotent(databases: tuple[str, str]) -> None:
    _, upgraded = databases
    before = (_schema(upgraded), _owned_data(upgraded))
    _alembic(upgraded, "stamp", "012_pg_collapse_sqlite_branch")
    _alembic(upgraded, "upgrade", "head")
    assert (_schema(upgraded), _owned_data(upgraded)) == before


def test_downgrade_round_trip(databases: tuple[str, str]) -> None:
    fresh, _ = databases
    before = (_schema(fresh), _owned_data(fresh))
    _alembic(fresh, "downgrade", "012_pg_collapse_sqlite_branch")
    tables = {t for t, *_ in _schema(fresh)["columns"]}
    assert "legal_module" not in tables
    constraints = {name for _, name, _ in _schema(fresh)["constraints"]}
    assert "ck_case_run_area_legal_area" in constraints
    _alembic(fresh, "upgrade", "head")
    assert (_schema(fresh), _owned_data(fresh)) == before


def test_orm_matches_migrated_schema(databases: tuple[str, str]) -> None:
    """No autogenerate diff on the tables WP-94 touches."""
    from sqlalchemy.ext.asyncio import create_async_engine

    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext
    from app.db.models import Base

    fresh, _ = databases

    def compare(conn: Any) -> list[Any]:
        return list(compare_metadata(MigrationContext.configure(conn), Base.metadata))

    async def run() -> list[Any]:
        engine = create_async_engine(_url(fresh))
        try:
            async with engine.connect() as conn:
                return await conn.run_sync(compare)
        finally:
            await engine.dispose()

    # Objects WP-94 added or changed. Other columns of the touched tables
    # carry pre-existing ORM/DB drift (e.g. naive vs. tz-aware created_at)
    # that is out of scope here.
    wp94_columns = {
        ("case_run_area", "module_id"),
        ("case_run_area", "module_version"),
        ("legal_parameter", "domain"),
    }
    wp94_names = {"fk_case_run_area_module_id", "idx_case_run_area_module"}

    def is_wp94(diff: Any) -> bool:
        items = diff if isinstance(diff, list) else [diff]
        for item in items:
            if item[0].startswith("modify_"):  # (op, schema, table, column, ...)
                if item[2] == "legal_module" or (item[2], item[3]) in wp94_columns:
                    return True
                continue
            obj = item[1]
            table = getattr(obj, "table", None)
            table_name = getattr(table, "name", None) or getattr(obj, "name", None)
            if table_name == "legal_module" or getattr(obj, "name", None) in wp94_names:
                return True
            if item[0] in ("add_column", "remove_column") and (item[2], item[3].name) in (
                wp94_columns
            ):
                return True
        return False

    relevant = [d for d in asyncio.run(run()) if is_wp94(d)]
    assert relevant == []
