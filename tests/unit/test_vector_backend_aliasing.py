"""
Regression tests for vector_backend column aliasing.

These tests guard against the dialect-specific column aliasing bug that caused
the Prüfstand goldset demo to fail on PostgreSQL (production) while SQLite
(tests) passed. The root cause: `_cosine_distance_pgvector` did not alias
dotted extra_columns (e.g. "lc.text_content"), so the row dict key was
"text_content" instead of "lc_text_content" — but retrieval.py expects
"lc_text_content". SQLite aliased correctly; pgvector did not.

We test both backends with a mock session and assert the generated SQL contains
the expected aliases. This locks in the contract that both backends MUST
produce the same row-dict key structure for the same extra_columns input.

Version: 1.0.0 | 2026-07-19
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.db.vector_backend import _cosine_distance_pgvector, _cosine_distance_sqlite

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_session() -> tuple[MagicMock, AsyncMock]:
    """
    Build a mock AsyncSession whose .execute() captures the SQL text + params.

    Returns (session_mock, execute_mock). The execute_mock's call_args will
    hold the (query, params) tuple after a call.
    """
    session = MagicMock()
    execute_mock = AsyncMock()

    # execute() returns an object with .fetchall() returning []
    result_obj = MagicMock()
    result_obj.fetchall.return_value = []
    execute_mock.return_value = result_obj
    session.execute = execute_mock

    return session, execute_mock


def _query_text(execute_mock: AsyncMock) -> str:
    """Extract the SQL text from the first positional arg of execute()."""
    call_args = execute_mock.call_args
    # execute(query, params) — query is the first positional arg
    query_obj = call_args.args[0]
    # The query is a sqlalchemy TextClause; its .text attribute holds the SQL.
    return str(query_obj.text if hasattr(query_obj, "text") else query_obj)


# ---------------------------------------------------------------------------
# pgvector backend — the bug location
# ---------------------------------------------------------------------------


class TestPgvectorAliasing:
    """Regression: pgvector backend must alias dotted extra_columns."""

    @pytest.mark.asyncio
    async def test_dotted_column_gets_aliased(self) -> None:
        """'lc.text_content' must appear as 'lc.text_content AS lc_text_content'."""
        session, execute_mock = _make_mock_session()

        await _cosine_distance_pgvector(
            session,
            embedding=[0.1, 0.2, 0.3],
            table_name="chunk_embedding",
            id_column="chunk_id",
            vector_column="embedding",
            top_k=10,
            threshold=0.3,
            extra_joins=None,
            extra_columns=["lc.text_content"],
            extra_conditions=None,
        )

        sql = _query_text(execute_mock)
        assert (
            "lc.text_content AS lc_text_content" in sql
        ), f"pgvector must alias dotted columns; got SQL: {sql}"

    @pytest.mark.asyncio
    async def test_multiple_dotted_columns_aliased(self) -> None:
        """All dotted extra_columns must be aliased, not just the first."""
        session, execute_mock = _make_mock_session()

        await _cosine_distance_pgvector(
            session,
            embedding=[0.1, 0.2, 0.3],
            table_name="chunk_embedding",
            id_column="chunk_id",
            vector_column="embedding",
            top_k=10,
            threshold=0.3,
            extra_joins=None,
            extra_columns=["lc.text_content", "lc.metadata", "ls.title"],
            extra_conditions=None,
        )

        sql = _query_text(execute_mock)
        assert "lc.text_content AS lc_text_content" in sql
        assert "lc.metadata AS lc_metadata" in sql
        assert "ls.title AS ls_title" in sql

    @pytest.mark.asyncio
    async def test_pre_aliased_column_passes_through(self) -> None:
        """A column already containing ' AS ' must not be double-aliased."""
        session, execute_mock = _make_mock_session()

        await _cosine_distance_pgvector(
            session,
            embedding=[0.1, 0.2, 0.3],
            table_name="chunk_embedding",
            id_column="chunk_id",
            vector_column="embedding",
            top_k=10,
            threshold=0.3,
            extra_joins=None,
            extra_columns=["lc.text_content AS custom_alias"],
            extra_conditions=None,
        )

        sql = _query_text(execute_mock)
        assert "lc.text_content AS custom_alias" in sql
        # Must NOT also contain the auto-aliased form
        assert "lc.text_content AS lc_text_content" not in sql

    @pytest.mark.asyncio
    async def test_no_extra_columns(self) -> None:
        """When extra_columns is None, no aliasing logic runs — just id + distance."""
        session, execute_mock = _make_mock_session()

        await _cosine_distance_pgvector(
            session,
            embedding=[0.1, 0.2, 0.3],
            table_name="chunk_embedding",
            id_column="chunk_id",
            vector_column="embedding",
            top_k=10,
            threshold=0.3,
            extra_joins=None,
            extra_columns=None,
            extra_conditions=None,
        )

        sql = _query_text(execute_mock)
        assert "ce.chunk_id AS id" in sql
        assert "distance" in sql


# ---------------------------------------------------------------------------
# SQLite backend — must remain consistent (the reference implementation)
# ---------------------------------------------------------------------------


class TestSqliteAliasing:
    """SQLite backend aliasing — the reference that pgvector must match."""

    @pytest.mark.asyncio
    async def test_dotted_column_gets_aliased(self) -> None:
        """SQLite must alias 'lc.text_content' → 'lc_text_content' (reference)."""
        session, execute_mock = _make_mock_session()

        await _cosine_distance_sqlite(
            session,
            embedding=[0.1, 0.2, 0.3],
            table_name="chunk_embedding",
            id_column="chunk_id",
            vector_column="embedding",
            top_k=10,
            threshold=0.3,
            extra_joins=None,
            extra_columns=["lc.text_content"],
            extra_conditions=None,
        )

        sql = _query_text(execute_mock)
        assert (
            "lc.text_content AS lc_text_content" in sql
        ), f"SQLite must alias dotted columns; got SQL: {sql}"


# ---------------------------------------------------------------------------
# Cross-dialect consistency — the core regression guard
# ---------------------------------------------------------------------------


class TestCrossDialectConsistency:
    """
    Both backends must produce the same aliased column names for the same input.

    This is the test that would have caught the production bug: pgvector was
    missing the aliasing that SQLite had, so retrieval.py's row["lc_text_content"]
    worked on SQLite but KeyError'd on PostgreSQL.
    """

    @pytest.mark.asyncio
    async def test_both_backends_alias_identically(self) -> None:
        extra_cols = ["lc.text_content", "lc.metadata"]

        # pgvector
        pg_session, pg_execute = _make_mock_session()
        await _cosine_distance_pgvector(
            pg_session,
            embedding=[0.1, 0.2, 0.3],
            table_name="chunk_embedding",
            id_column="chunk_id",
            vector_column="embedding",
            top_k=10,
            threshold=0.3,
            extra_joins=None,
            extra_columns=extra_cols,
            extra_conditions=None,
        )
        pg_sql = _query_text(pg_execute)

        # sqlite
        lite_session, lite_execute = _make_mock_session()
        await _cosine_distance_sqlite(
            lite_session,
            embedding=[0.1, 0.2, 0.3],
            table_name="chunk_embedding",
            id_column="chunk_id",
            vector_column="embedding",
            top_k=10,
            threshold=0.3,
            extra_joins=None,
            extra_columns=extra_cols,
            extra_conditions=None,
        )
        lite_sql = _query_text(lite_execute)

        # Both must contain the same aliased column expressions
        for expected in ["lc.text_content AS lc_text_content", "lc.metadata AS lc_metadata"]:
            assert expected in pg_sql, f"pgvector missing alias: {expected}\nSQL: {pg_sql}"
            assert expected in lite_sql, f"SQLite missing alias: {expected}\nSQL: {lite_sql}"
