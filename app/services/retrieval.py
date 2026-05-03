"""Retrieval engine: pgvector query, diversity constraints, and metadata join.

Given a list of legal questions, this module:
1. Generates an embedding for each question via the OpenRouter embedding API.
2. Queries ``chunk_embedding`` using the ``<->`` cosine distance operator.
3. Filters results by ``DIVERSITY_THRESHOLD`` (cosine distance < threshold).
4. Enforces ``TOP_K_RETRIEVAL`` per question.
5. Joins with ``legal_chunk`` to fetch ``text_content``, ``hierarchy_path``,
   ``source_type``, and other metadata.
6. Deduplicates by ``chunk_id`` and sorts by aggregate relevance.
7. Returns a list of rich dictionaries.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.router import EmbeddingError, OpenRouterClient
from app.db.models import ChunkEmbedding, LegalChunk, LegalSource
from app.db.session import get_async_session

logger = logging.getLogger(__name__)


class RetrievalError(Exception):
    """Raised when the retrieval engine fails irrecoverably."""


async def retrieve_chunks(
    questions: list[str],
    *,
    client: OpenRouterClient | None = None,
    session_factory: None = None,  # unused, kept for interface compatibility
) -> list[dict[str, Any]]:
    """Retrieve diverse, ranked legal chunks for each question.

    Parameters
    ----------
    questions :
        A list of legal questions (strings) produced by the decomposition
        stage.
    client :
        Optional ``OpenRouterClient`` for embedding generation. A new client
        is created when *None*.

    Returns
    -------
    list[dict[str, Any]]
        Each dict contains at minimum:
        ``chunk_id``, ``text_content``, ``hierarchy_path``, ``source_type``,
        ``title``, ``effective_date``, ``distance``, ``question_index``.
    """
    if not questions:
        return []

    top_k = settings.TOP_K_RETRIEVAL
    threshold = settings.DIVERSITY_THRESHOLD

    # Step 1 — generate question embeddings
    async with client or OpenRouterClient() as router:
        try:
            question_embeddings = await router.get_embeddings_batch(questions)
        except EmbeddingError as exc:
            logger.error("Embedding generation failed for retrieval: %s", exc)
            raise RetrievalError(f"Embedding API failure during retrieval: {exc}") from exc

    # Step 2 — query pgvector per question and aggregate results
    all_chunks: list[dict[str, Any]] = []
    seen_chunk_ids: set[str] = set()

    async for session in get_async_session():
        for q_idx, q_embedding in enumerate(question_embeddings):
            stmt = (
                select(
                    ChunkEmbedding.id.label("embedding_id"),
                    ChunkEmbedding.chunk_id,
                    ChunkEmbedding.embedding.cosine_distance(q_embedding).label("distance"),
                    LegalChunk.id.label("lc_id"),
                    LegalChunk.text_content,
                    LegalChunk.hierarchy_path,
                    LegalChunk.unit_type,
                    LegalChunk.effective_date,
                    LegalSource.source_type,
                    LegalSource.title,
                )
                .join(LegalChunk, LegalChunk.id == ChunkEmbedding.chunk_id)
                .join(LegalSource, LegalSource.id == LegalChunk.source_id)
                .where(
                    ChunkEmbedding.embedding.cosine_distance(q_embedding) < threshold,
                    LegalSource.is_active.is_(True),
                )
                .order_by(ChunkEmbedding.embedding.cosine_distance(q_embedding).asc())
                .limit(top_k)
            )

            result = await session.execute(stmt)
            rows = result.mappings().all()

            for row in rows:
                cid = str(row["chunk_id"])
                if cid in seen_chunk_ids:
                    continue
                seen_chunk_ids.add(cid)

                all_chunks.append(
                    {
                        "chunk_id": cid,
                        "text_content": row["text_content"],
                        "hierarchy_path": row["hierarchy_path"],
                        "unit_type": row["unit_type"],
                        "effective_date": str(row["effective_date"])
                        if row["effective_date"]
                        else "",
                        "source_type": row["source_type"],
                        "title": row["title"],
                        "distance": float(row["distance"]),
                        "question_index": q_idx,
                    }
                )

        await session.close()
        break  # one session is sufficient — we fetched everything

    # Step 3 — sort by aggregate relevance (distance ascending)
    all_chunks.sort(key=lambda c: c["distance"])

    logger.info(
        "Retrieval complete: %d unique chunks for %d questions " "(threshold=%.2f, top_k=%d)",
        len(all_chunks),
        len(questions),
        threshold,
        top_k,
    )
    return all_chunks


async def retrieve_chunks_for_question(
    question: str,
    *,
    client: OpenRouterClient | None = None,
    top_k: int | None = None,
    threshold: float | None = None,
    session: AsyncSession | None = None,
) -> list[dict[str, Any]]:
    """Retrieve chunks for a *single* question with optional overrides.

    This variant is useful for unit/integration tests or targeted queries
    where per-question control is needed.

    Parameters
    ----------
    question :
        A single legal question.
    client :
        Optional ``OpenRouterClient`` for embedding generation.
    top_k :
        Maximum number of chunks to return (defaults to ``settings.TOP_K_RETRIEVAL``).
    threshold :
        Maximum cosine distance for diversity filtering
        (defaults to ``settings.DIVERSITY_THRESHOLD``).
    session :
        Optional ``AsyncSession``. When *None*, opens a new session via
        ``get_async_session``.

    Returns
    -------
    list[dict[str, Any]]
        Same structure as :func:`retrieve_chunks` but without the
        ``question_index`` key.
    """
    if top_k is None:
        top_k = settings.TOP_K_RETRIEVAL
    if threshold is None:
        threshold = settings.DIVERSITY_THRESHOLD

    # Step 1 — embed the question
    async with client or OpenRouterClient() as router:
        try:
            embedding = await router.get_embedding(question)
        except EmbeddingError as exc:
            logger.error("Embedding generation failed: %s", exc)
            raise RetrievalError(f"Embedding API failure: {exc}") from exc

    # Step 2 — query and join
    results: list[dict[str, Any]] = []

    if session is not None:
        results = await _execute_query(session, embedding, top_k, threshold)
    else:
        async for sess in get_async_session():
            results = await _execute_query(sess, embedding, top_k, threshold)
            await sess.close()
            break

    results.sort(key=lambda c: c["distance"])
    return results


async def _execute_query(
    session: AsyncSession,
    embedding: list[float],
    top_k: int,
    threshold: float,
) -> list[dict[str, Any]]:
    """Internal helper: execute the pgvector similarity query.

    Parameters
    ----------
    session :
        Active ``AsyncSession``.
    embedding :
        Dense embedding vector for the question.
    top_k :
        Maximum results per question.
    threshold :
        Cosine distance threshold for diversity filtering.

    Returns
    -------
    list[dict[str, Any]]
        Retrieved chunks with metadata.
    """
    dist_col = ChunkEmbedding.embedding.cosine_distance(embedding)

    stmt: Select[tuple[Any, ...]] = (
        select(
            ChunkEmbedding.chunk_id,
            dist_col.label("distance"),
            LegalChunk.text_content,
            LegalChunk.hierarchy_path,
            LegalChunk.unit_type,
            LegalChunk.effective_date,
            LegalSource.source_type,
            LegalSource.title,
        )
        .join(LegalChunk, LegalChunk.id == ChunkEmbedding.chunk_id)
        .join(LegalSource, LegalSource.id == LegalChunk.source_id)
        .where(
            dist_col < threshold,
            LegalSource.is_active.is_(True),
        )
        .order_by(dist_col.asc())
        .limit(top_k)
    )

    result = await session.execute(stmt)
    rows = result.mappings().all()

    return [
        {
            "chunk_id": str(row["chunk_id"]),
            "text_content": row["text_content"],
            "hierarchy_path": row["hierarchy_path"],
            "unit_type": row["unit_type"],
            "effective_date": str(row["effective_date"]) if row["effective_date"] else "",
            "source_type": row["source_type"],
            "title": row["title"],
            "distance": float(row["distance"]),
        }
        for row in rows
    ]
