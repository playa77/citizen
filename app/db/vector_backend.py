"""
Vector backend abstraction layer.

Provides dialect-agnostic cosine-distance queries for embedding retrieval.
Detects PostgreSQL+pgvector vs SQLite+sqlite-vec at module load time and
exposes the same interface regardless of backend.

Version: 1.0.0 | 2026-07-10
"""

import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Dialect detection
# ---------------------------------------------------------------------------

IS_SQLITE: bool = settings.DATABASE_URL.startswith("sqlite")

# For PostgreSQL, the cosine_distance operator is available via pgvector's
# SQLAlchemy integration. For SQLite, we use raw SQL with sqlite-vec's
# vec_distance_cosine function.

if IS_SQLITE:
    logger.info("Vector backend: sqlite-vec (cosine distance via vec_distance_cosine)")
else:
    logger.info("Vector backend: pgvector (cosine distance via <=> operator)")


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
    if IS_SQLITE:
        return await _cosine_distance_sqlite(
            session,
            embedding=embedding,
            table_name=table_name,
            id_column=id_column,
            vector_column=vector_column,
            top_k=top_k,
            threshold=threshold,
            extra_joins=extra_joins,
            extra_columns=extra_columns,
            extra_conditions=extra_conditions,
        )
    else:
        return await _cosine_distance_pgvector(
            session,
            embedding=embedding,
            table_name=table_name,
            id_column=id_column,
            vector_column=vector_column,
            top_k=top_k,
            threshold=threshold,
            extra_joins=extra_joins,
            extra_columns=extra_columns,
            extra_conditions=extra_conditions,
        )


# ---------------------------------------------------------------------------
# Backend implementations
# ---------------------------------------------------------------------------

async def _cosine_distance_sqlite(
    session: AsyncSession,
    *,
    embedding: list[float],
    table_name: str,
    id_column: str,
    vector_column: str,
    top_k: int,
    threshold: float,
    extra_joins: list[str] | None,
    extra_columns: list[str] | None,
    extra_conditions: list[str] | None,
) -> list[dict[str, Any]]:
    """
    sqlite-vec backend: uses vec_distance_cosine() function against a BLOB column.

    The embedding is serialized as a little-endian float32 blob for sqlite-vec.
    """
    import struct

    # Serialize embedding to binary blob (sqlite-vec expects LE float32)
    blob = struct.pack(f"<{len(embedding)}f", *embedding)

    # Build SELECT columns
    cols = [f"{table_name}.{id_column} AS id"]
    if extra_columns:
        for col in extra_columns:
            # Alias dotted column names so the result dict key is predictable.
            # "lc.text_content" → cursor returns "text_content" (no table prefix),
            # so we alias to "lc_text_content" for a stable, unambiguous key.
            if " AS " in col.upper():
                cols.append(col)
            else:
                alias = col.replace(".", "_")
                cols.append(f"{col} AS {alias}")
    cols.append(
        f"vec_distance_cosine({table_name}.{vector_column}, :embedding_blob) AS distance"
    )

    # Build FROM + JOINs
    from_clause = f"FROM {table_name}"
    if extra_joins:
        from_clause += " " + " ".join(extra_joins)

    # Build WHERE
    conditions = [
        f"vec_distance_cosine({table_name}.{vector_column}, :embedding_blob) < :threshold"
    ]
    if extra_conditions:
        conditions.extend(extra_conditions)
    where_clause = " AND ".join(conditions)

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
            "embedding_blob": blob,
            "threshold": threshold,
            "top_k": top_k,
        },
    )

    # Convert Row objects to dicts
    rows = result.fetchall()
    return [dict(row._mapping) for row in rows]


async def _cosine_distance_pgvector(
    session: AsyncSession,
    *,
    embedding: list[float],
    table_name: str,
    id_column: str,
    vector_column: str,
    top_k: int,
    threshold: float,
    extra_joins: list[str] | None,
    extra_columns: list[str] | None,
    extra_conditions: list[str] | None,
) -> list[dict[str, Any]]:
    """
    pgvector backend: uses .cosine_distance() on the Vector typed column.

    This is a raw SQL fallback since the ORM Vector type requires the pgvector
    SQLAlchemy extension (which depends on the pgvector Python package).
    """
    from sqlalchemy.sql import text as sa_text

    # Build SELECT columns
    cols = [f"{table_name}.{id_column} AS id"]
    if extra_columns:
        cols.extend(extra_columns)
    cols.append(f"({table_name}.{vector_column} <=> (:query_vec)::vector) AS distance")

    # Build FROM + JOINs
    from_clause = f"FROM {table_name}"
    if extra_joins:
        from_clause += " " + " ".join(extra_joins)

    # Build WHERE
    conditions = [f"({table_name}.{vector_column} <=> (:query_vec)::vector) < :threshold"]
    if extra_conditions:
        conditions.extend(extra_conditions)
    where_clause = " AND ".join(conditions)

    # Serialize embedding as pgvector literal: '[1.0, 2.0, 3.0]'
    vec_literal = "[" + ", ".join(str(x) for x in embedding) + "]"

    query = sa_text(
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


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

async def load_sqlite_vec_extension(connection: Any) -> None:
    """
    Load the sqlite-vec extension into a SQLite connection.

    Must be called once during app startup when using SQLite backend.

    Args:
        connection: A synchronous sqlite3 connection or SQLAlchemy raw connection.
    """
    if not IS_SQLITE:
        return


    import sqlite_vec

    # Get the underlying sqlite3 connection
    raw_conn = connection.connection if hasattr(connection, "connection") else connection

    raw_conn.enable_load_extension(True)
    try:
        sqlite_vec.load(raw_conn)
        logger.info("sqlite-vec extension loaded successfully.")
    except Exception as exc:
        logger.warning("Could not load sqlite-vec extension: %s. Vector search may not work.", exc)
    finally:
        raw_conn.enable_load_extension(False)
