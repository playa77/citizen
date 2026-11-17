"""WP-100: migration 014 (case_dossier table).

Throw-away databases on the test server, as in ``test_migration_013.py``:
shape, cascade on case delete, revision constraints, idempotent replay,
downgrade/upgrade round trip, ORM ↔ schema parity for the new table.
"""

# Semantic Version: 1.0.0

from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import Any

import asyncpg
import pytest

from tests.unit.alembic.test_migration_013 import (
    _admin,
    _alembic,
    _execute,
    _query,
    _schema,
    _url,
)


@pytest.fixture(scope="module")
def database() -> Iterator[str]:
    name = f"wp100_{uuid.uuid4().hex[:8]}"
    _admin(f"CREATE DATABASE {name}")
    try:
        _alembic(name, "upgrade", "head")
        yield name
    finally:
        _admin(f"DROP DATABASE IF EXISTS {name} WITH (FORCE)")


def _case(dbname: str) -> uuid.UUID:
    case_id = uuid.uuid4()
    _execute(
        dbname,
        "INSERT INTO case_run (id, session_id, input_text, status) "
        f"VALUES ('{case_id}', 'wp100', 'synthetic', 'completed')",
    )
    return case_id


def _dossier(dbname: str, case_id: uuid.UUID, revision: int) -> None:
    _execute(
        dbname,
        "INSERT INTO case_dossier (id, case_run_id, revision, schema_version, dossier_json, "
        f"content_sha256) VALUES ('{uuid.uuid4()}', '{case_id}', {revision}, "
        f"'citizen-dossier-v1.0', '{{}}', '{'0' * 64}')",
    )


def test_shape(database: str) -> None:
    constraints = {
        name for table, name, _ in _schema(database)["constraints"] if table == "case_dossier"
    }
    assert constraints == {
        "case_dossier_pkey",
        "fk_case_dossier_case_run_id",
        "uq_case_dossier_case_revision",
        "ck_case_dossier_revision_positive",
    }
    indexes = {name for table, name, _ in _schema(database)["indexes"] if table == "case_dossier"}
    assert "idx_case_dossier_case" in indexes


def test_revision_rules_and_cascade(database: str) -> None:
    case_id = _case(database)
    _dossier(database, case_id, 1)
    with pytest.raises(asyncpg.UniqueViolationError):
        _dossier(database, case_id, 1)
    with pytest.raises(asyncpg.CheckViolationError):
        _dossier(database, case_id, 0)
    _execute(database, f"DELETE FROM case_run WHERE id = '{case_id}'")
    assert _query(database, "SELECT count(*) FROM case_dossier") == [(0,)]


def test_replay_and_round_trip(database: str) -> None:
    before = _schema(database)
    _alembic(database, "stamp", "013_legal_module")
    _alembic(database, "upgrade", "head")
    assert _schema(database) == before
    _alembic(database, "downgrade", "013_legal_module")
    assert "case_dossier" not in {t for t, *_ in _schema(database)["columns"]}
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

    import asyncio

    def touches_case_dossier(diff: Any) -> bool:
        for item in diff if isinstance(diff, list) else [diff]:
            if item[0].startswith("modify_"):
                if item[2] == "case_dossier":
                    return True
                continue
            obj = item[1]
            table = getattr(obj, "table", None)
            if (getattr(table, "name", None) or getattr(obj, "name", None)) == "case_dossier":
                return True
        return False

    assert [d for d in asyncio.run(run()) if touches_case_dossier(d)] == []
