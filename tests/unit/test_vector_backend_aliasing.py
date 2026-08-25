"""
Regression tests for vector_backend column aliasing.

These tests guard against the column aliasing bug that caused the Prüfstand
goldset demo to fail on PostgreSQL (production) while SQLite (then-tests)
passed. The root cause: dotted extra_columns (e.g. "lc.text_content") were
not aliased, so the row dict key was "text_content" instead of
"lc_text_content" — but retrieval.py expects "lc_text_content".

We drive the public ``cosine_distance()`` with a mock session and assert the
generated SQL contains the expected aliases. Since D-024 there is exactly
one backend (PostgreSQL + pgvector); these mocks lock in its SQL contract
without requiring a live database.

Version: 2.0.0 | 2026-08-25 — single-backend rework (D-024); SQLite
reference path removed.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.db.vector_backend import cosine_distance

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


async def _run_cosine_distance(
    execute_mock: AsyncMock,
    extra_columns: list[str] | None,
) -> None:
    """Call cosine_distance() with fixed args, capturing SQL via execute_mock."""
    session = MagicMock()
    session.execute = execute_mock
    await cosine_distance(
        session,
        embedding=[0.1, 0.2, 0.3],
        table_name="chunk_embedding",
        id_column="chunk_id",
        vector_column="embedding",
        top_k=10,
        threshold=0.3,
        extra_joins=None,
        extra_columns=extra_columns,
        extra_conditions=None,
    )


# ---------------------------------------------------------------------------
# Aliasing contract
# ---------------------------------------------------------------------------


class TestPgvectorAliasing:
    """Regression: the backend must alias dotted extra_columns."""

    @pytest.mark.asyncio
    async def test_dotted_column_gets_aliased(self) -> None:
        """'lc.text_content' must appear as 'lc.text_content AS lc_text_content'."""
        _, execute_mock = _make_mock_session()
        await _run_cosine_distance(execute_mock, ["lc.text_content"])

        sql = _query_text(execute_mock)
        assert (
            "lc.text_content AS lc_text_content" in sql
        ), f"backend must alias dotted columns; got SQL: {sql}"

    @pytest.mark.asyncio
    async def test_multiple_dotted_columns_aliased(self) -> None:
        """All dotted extra_columns must be aliased, not just the first."""
        _, execute_mock = _make_mock_session()
        await _run_cosine_distance(
            execute_mock, ["lc.text_content", "lc.metadata", "ls.title"]
        )

        sql = _query_text(execute_mock)
        assert "lc.text_content AS lc_text_content" in sql
        assert "lc.metadata AS lc_metadata" in sql
        assert "ls.title AS ls_title" in sql

    @pytest.mark.asyncio
    async def test_pre_aliased_column_passes_through(self) -> None:
        """A column already containing ' AS ' must not be double-aliased."""
        _, execute_mock = _make_mock_session()
        await _run_cosine_distance(execute_mock, ["lc.text_content AS custom_alias"])

        sql = _query_text(execute_mock)
        assert "lc.text_content AS custom_alias" in sql
        # Must NOT also contain the auto-aliased form
        assert "lc.text_content AS lc_text_content" not in sql

    @pytest.mark.asyncio
    async def test_no_extra_columns(self) -> None:
        """When extra_columns is None, no aliasing logic runs — just id + distance."""
        _, execute_mock = _make_mock_session()
        await _run_cosine_distance(execute_mock, None)

        sql = _query_text(execute_mock)
        assert "ce.chunk_id AS id" in sql
        assert "distance" in sql

    @pytest.mark.asyncio
    async def test_pgvector_operator_and_cast_present(self) -> None:
        """The query must use pgvector's <=> operator with an explicit ::vector cast."""
        _, execute_mock = _make_mock_session()
        await _run_cosine_distance(execute_mock, None)

        sql = _query_text(execute_mock)
        assert "<=>" in sql, f"pgvector cosine operator missing; got SQL: {sql}"
        assert "::vector" in sql, f"explicit vector cast missing; got SQL: {sql}"
