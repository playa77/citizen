"""P11: migration 015 (module_update ledger, corpus_source_watch).

Throw-away databases on the test server, as in ``test_migration_013.py``:
shape, ledger constraints (unique serial per module, positive serial),
idempotent replay, downgrade/upgrade round trip, ORM ↔ schema parity for
the two new tables.
"""

# Semantic Version: 1.0.0 | 2026-11-17

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Iterator
from typing import Any

import asyncpg
import pytest

from tests.unit.alembic.test_migration_013 import (
    _admin,
    _alembic,
    _execute,
    _schema,
    _url,
)

TABLES = {"module_update", "corpus_source_watch"}


@pytest.fixture(scope="module")
def database() -> Iterator[str]:
    name = f"p11_{uuid.uuid4().hex[:8]}"
    _admin(f"CREATE DATABASE {name}")
    try:
        _alembic(name, "upgrade", "head")
        yield name
    finally:
        _admin(f"DROP DATABASE IF EXISTS {name} WITH (FORCE)")


def _ledger(dbname: str, module_id: str, serial: int) -> None:
    _execute(
        dbname,
        "INSERT INTO module_update (id, module_id, serial, feed_sha256, key_id, issued_at, "
        "module_version, source, parameters, corpus_notices) VALUES "
        f"('{uuid.uuid4()}', '{module_id}', {serial}, '{'0' * 64}', 'k', now(), '1.0.0', "
        "'mem', '[]', '[]')",
    )


def test_shape(database: str) -> None:
    constraints = {name for table, name, _ in _schema(database)["constraints"] if table in TABLES}
    assert constraints == {
        "module_update_pkey",
        "uq_module_update_module_serial",
        "ck_module_update_serial_positive",
        "corpus_source_watch_pkey",
    }
    indexes = {name for table, name, _ in _schema(database)["indexes"] if table in TABLES}
    assert "idx_module_update_module" in indexes


def test_ledger_constraints(database: str) -> None:
    _ledger(database, "demo", 1)
    _ledger(database, "other", 1)  # serials are per module
    with pytest.raises(asyncpg.UniqueViolationError):
        _ledger(database, "demo", 1)
    with pytest.raises(asyncpg.CheckViolationError):
        _ledger(database, "demo", 0)


def test_replay_and_round_trip(database: str) -> None:
    before = _schema(database)
    _alembic(database, "stamp", "014_case_dossier")
    _alembic(database, "upgrade", "head")
    assert _schema(database) == before
    _alembic(database, "downgrade", "014_case_dossier")
    assert not TABLES & {t for t, *_ in _schema(database)["columns"]}
    _alembic(database, "upgrade", "head")
    assert _schema(database) == before


def test_orm_matches_migrated_schema(database: str) -> None:
    from sqlalchemy.ext.asyncio import create_async_engine

    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext
    from app.db.models import Base

    def compare(conn: Any) -> list[Any]:
        return list(compare_metadata(MigrationContext.configure(conn), Base.metadata))

    async def run() -> list[Any]:
        engine = create_async_engine(_url(database))
        try:
            async with engine.connect() as conn:
                return await conn.run_sync(compare)
        finally:
            await engine.dispose()

    def touches_new_tables(diff: Any) -> bool:
        for item in diff if isinstance(diff, list) else [diff]:
            if item[0].startswith("modify_"):
                if item[2] in TABLES:
                    return True
                continue
            obj = item[1]
            table = getattr(obj, "table", None)
            if (getattr(table, "name", None) or getattr(obj, "name", None)) in TABLES:
                return True
        return False

    assert [d for d in asyncio.run(run()) if touches_new_tables(d)] == []
