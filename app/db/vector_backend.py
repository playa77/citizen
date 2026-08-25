"""
Vector backend for PostgreSQL + pgvector.

Provides cosine-distance similarity search against the embedding table via
pgvector's ``<=>`` operator. Single backend since D-024 — the former
SQLite/sqlite-vec dual path was removed together with its last consumer.

Version: 2.0.0 | 2026-08-25
"""

import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def cosine_distance(
    session: AsyncSession,
    /,
    *,
    embedding: list[float],
    table_name: str = "chunk_embedding",
    id_column: str = "chunk_id",
    vector_column: str = "embedding",
    top_k: int = 10,
    threshold: float = 0.3,
    extra_joins: list[str] | None = None,
    extra_columns: list[str] | None = None,
    extra_conditions: list[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Run a cosine-distance similarity search against the embedding table.

    Returns rows as dicts with at minimum: id, distance, plus any extra_columns.

    Args:
        session: Async SQLAlchemy session.
        embedding: The query embedding vector (list of floats).
        table_name: Name of the embedding table (default: chunk_embedding).
        id_column: Name of the ID column to return (default: chunk_id).
        vector_column: Name of the vector column (default: embedding).
        top_k: Maximum number of results to return.
        threshold: Maximum cosine distance (lower = more similar).
        extra_joins: SQL JOIN clauses to add (e.g., ["JOIN legal_chunk lc ON lc.id = ce.chunk_id"]).
        extra_columns: Additional columns to SELECT.
        extra_conditions: Additional WHERE conditions (e.g., ["ls.is_active = 1"]).

    Returns:
        List of result dicts with 'id', 'distance', and any extra_columns.
    """
    # Build SELECT columns — table is aliased as `ce` in FROM clause (see below)
    cols = [f"ce.{id_column} AS id"]
    if extra_columns:
        for col in extra_columns:
            # Alias dotted column names so the result dict key is predictable.
            # "lc.text_content" → "lc_text_content". Without this aliasing,
            # retrieval.py's expected row keys diverge between dialects and
            # joined tables with same-named columns become ambiguous
            # (see DECISIONS.md §D-016).
            if " AS " in col.upper():
                cols.append(col)
            else:
                alias = col.replace(".", "_")
                cols.append(f"{col} AS {alias}")
    cols.append(f"(ce.{vector_column} <=> (:query_vec)::vector) AS distance")

    # Build FROM + JOINs — alias the embedding table as `ce` so extra_joins
    # (which reference `ce.chunk_id` per the documented contract) resolve correctly.
    from_clause = f"FROM {table_name} AS ce"
    if extra_joins:
        from_clause += " " + " ".join(extra_joins)

    # Build WHERE
    conditions = [f"(ce.{vector_column} <=> (:query_vec)::vector) < :threshold"]
    if extra_conditions:
        conditions.extend(extra_conditions)
    where_clause = " AND ".join(conditions)

    # Serialize embedding as pgvector literal: '[1.0, 2.0, 3.0]'
    vec_literal = "[" + ", ".join(str(x) for x in embedding) + "]"

    query = text(
        f"SELECT {', '.join(cols)} "
        f"{from_clause} "
        f"WHERE {where_clause} "
        f"ORDER BY distance ASC "
        f"LIMIT :top_k"
    )

    result = await session.execute(
        query,
        {
            "query_vec": vec_literal,
            "threshold": threshold,
            "top_k": top_k,
        },
    )

    rows = result.fetchall()
    return [dict(row._mapping) for row in rows]
