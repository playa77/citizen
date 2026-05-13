"""Retrieval engine: pgvector query, diversity constraints, and metadata join.

Given a list of legal questions, this module:
1. Generates an embedding for each question via the OpenRouter embedding API.
2. Queries ``chunk_embedding`` using the ``<->`` cosine distance operator.
3. Filters results by ``MAX_COSINE_DISTANCE`` (cosine distance < threshold).
4. Enforces ``TOP_K_RETRIEVAL`` per question.
5. Joins with ``legal_chunk`` to fetch ``text_content``, ``hierarchy_path``,
   ``source_type``, and other metadata.
6. Deduplicates by ``chunk_id`` and sorts by aggregate relevance.
7. Returns a list of rich dictionaries.
"""

# Semantic Version: 0.1.0

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import Select, or_, select
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

    logger.info("retrieve_chunks: starting (%d questions)", len(questions))
    top_k = settings.TOP_K_RETRIEVAL
    threshold = settings.MAX_COSINE_DISTANCE

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

    # Step 4 — keyword fallback if too few results
    if (
        len(all_chunks) < _MIN_CHUNKS_FOR_FALLBACK
        and settings.RETRIEVAL_KEYWORD_FALLBACK
    ):
        logger.warning(
            "retrieve_chunks: nur %d Vektor-Ergebnisse (min=%d) – "
            "Stichwort-Fallback wird aktiviert",
            len(all_chunks),
            _MIN_CHUNKS_FOR_FALLBACK,
        )
        combined_query = "\n".join(questions)
        keyword_chunks = await retrieve_chunks_keyword(
            combined_query,
            top_k=settings.TOP_K_KEYWORD,
            question_index=0,
        )
        all_chunks = _merge_vector_and_keyword_results(all_chunks, keyword_chunks)
        logger.info(
            "retrieve_chunks: Stichwort-Fallback hat %d weitere Chunks hinzugefügt "
            "(insgesamt %d)",
            len(keyword_chunks),
            len(all_chunks),
        )

    logger.info(
        "Retrieval complete: %d unique chunks for %d questions " "(threshold=%.2f, top_k=%d)",
        len(all_chunks),
        len(questions),
        threshold,
        top_k,
    )
    return all_chunks


async def retrieve_chunks_combined(
    issues: list[str],
    questions: list[str],
    normalized_text: str,
    *,
    client: OpenRouterClient | None = None,
) -> list[dict[str, Any]]:
    """Retrieve legal chunks using a single combined embedding for speed.

    Instead of embedding each question separately (N embedding requests),
    this builds one rich German search query from issues, questions, and
    the first 1200 characters of the normalized document text, then
    generates one embedding and queries pgvector once.

    Parameters
    ----------
    issues :
        Legal issues / topics identified (stage 2).
    questions :
        Explicit legal questions (stage 3).
    normalized_text :
        Cleaned / standardised document text (stage 1).
    client :
        Optional ``OpenRouterClient`` for embedding generation.

    Returns
    -------
    list[dict[str, Any]]
        Same dict shape as :func:`retrieve_chunks`.
        ``question_index`` is always 0 (single combined query).
    """
    if not issues and not questions:
        return []

    top_k = settings.TOP_K_RETRIEVAL
    threshold = settings.MAX_COSINE_DISTANCE

    # Build the combined German search query
    parts: list[str] = []
    if issues:
        parts.append("Themen:\n" + "\n".join(f"- {issue}" for issue in issues))
    if questions:
        parts.append("Rechtsfragen:\n" + "\n".join(f"- {q}" for q in questions))
    if normalized_text:
        doc_excerpt = normalized_text[:1200]
        parts.append(f"Dokumentauszug:\n{doc_excerpt}")

    combined_query = "\n\n".join(parts)
    logger.info(
        "retrieve_chunks_combined: built query (%d chars) from %d issues + %d questions",
        len(combined_query),
        len(issues),
        len(questions),
    )

    # Step 1 — generate one embedding (with WP-011 cache)
    embedding_model = settings.EMBEDDING_MODEL
    embedding: list[float] | None = None

    if settings.ENABLE_CACHE:
        from app.services.cache import get_json_cache, make_cache_key, set_json_cache

        cache_key = make_cache_key("embedding", embedding_model, combined_query)
        async for session in get_async_session():
            try:
                cached = await get_json_cache(session, cache_key)
                if cached is not None and isinstance(cached, list):
                    embedding = [float(v) for v in cached]
                    logger.info(
                        "retrieve_chunks_combined: embedding CACHE HIT (model=%s, dim=%d)",
                        embedding_model,
                        len(embedding),
                    )
            except Exception as exc:
                logger.warning("retrieve_chunks_combined: embedding cache read failed: %s", exc)
            finally:
                await session.close()
            break

    if embedding is None:
        async with client or OpenRouterClient() as router:
            try:
                embedding = await router.get_embedding(combined_query)
            except EmbeddingError as exc:
                logger.error("Combined embedding generation failed: %s", exc)
                raise RetrievalError(f"Embedding API failure during combined retrieval: {exc}") from exc

        # ── WP-011: store embedding in cache ────────────────────────
        if settings.ENABLE_CACHE:
            async for session in get_async_session():
                try:
                    await set_json_cache(session, cache_key, embedding)
                except Exception as exc:
                    logger.warning("retrieve_chunks_combined: embedding cache write failed: %s", exc)
                finally:
                    await session.close()
                break

    # Step 2 — query pgvector once
    all_chunks: list[dict[str, Any]] = []
    async for session in get_async_session():
        stmt = (
            select(
                ChunkEmbedding.id.label("embedding_id"),
                ChunkEmbedding.chunk_id,
                ChunkEmbedding.embedding.cosine_distance(embedding).label("distance"),
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
                ChunkEmbedding.embedding.cosine_distance(embedding) < threshold,
                LegalSource.is_active.is_(True),
            )
            .order_by(ChunkEmbedding.embedding.cosine_distance(embedding).asc())
            .limit(top_k)
        )

        result = await session.execute(stmt)
        rows = result.mappings().all()

        for row in rows:
            all_chunks.append(
                {
                    "chunk_id": str(row["chunk_id"]),
                    "text_content": row["text_content"],
                    "hierarchy_path": row["hierarchy_path"],
                    "unit_type": row["unit_type"],
                    "effective_date": str(row["effective_date"])
                    if row["effective_date"]
                    else "",
                    "source_type": row["source_type"],
                    "title": row["title"],
                    "distance": float(row["distance"]),
                    "question_index": 0,
                }
            )

        await session.close()
        break

    # Step 3 — sort by distance ascending
    all_chunks.sort(key=lambda c: c["distance"])

    # Step 4 — keyword fallback if too few results
    if (
        len(all_chunks) < _MIN_CHUNKS_FOR_FALLBACK
        and settings.RETRIEVAL_KEYWORD_FALLBACK
    ):
        logger.warning(
            "retrieve_chunks_combined: nur %d Vektor-Ergebnisse (min=%d) – "
            "Stichwort-Fallback wird aktiviert",
            len(all_chunks),
            _MIN_CHUNKS_FOR_FALLBACK,
        )
        keyword_chunks = await retrieve_chunks_keyword(
            combined_query,
            top_k=settings.TOP_K_KEYWORD,
            question_index=0,
        )
        all_chunks = _merge_vector_and_keyword_results(all_chunks, keyword_chunks)
        logger.info(
            "retrieve_chunks_combined: Stichwort-Fallback hat %d weitere Chunks "
            "hinzugefügt (insgesamt %d)",
            len(keyword_chunks),
            len(all_chunks),
        )

    logger.info(
        "Combined retrieval complete: %d unique chunks (threshold=%.2f, top_k=%d)",
        len(all_chunks),
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
        (defaults to ``settings.MAX_COSINE_DISTANCE``).
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
        threshold = settings.MAX_COSINE_DISTANCE

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
        Cosine distance threshold for relevance filtering.

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


# ---------------------------------------------------------------------------
# Keyword fallback search (used when vector search returns too few results)
# ---------------------------------------------------------------------------


# German legal terms and common stop words
_LEGAL_STOP_WORDS = frozenset({
    "der", "die", "das", "den", "dem", "des", "ein", "eine", "einer", "eines",
    "einen", "einem", "und", "oder", "aber", "sondern", "doch", "nicht",
    "auch", "als", "wie", "bei", "mit", "nach", "von", "aus", "zu", "zur",
    "zum", "auf", "in", "im", "an", "am", "ist", "wird", "werden", "wurde",
    "würde", "kann", "können", "soll", "sollen", "muss", "müssen", "hat",
    "haben", "hätte", "hätten", "sein", "sind", "war", "waren", "wäre",
    "dass", "durch", "für", "gegen", "ohne", "um", "über", "unter", "vor",
    "zwischen", "bis", "ab", "seit", "außer", "innerhalb", "außerhalb",
    "§", "abs", "satz", "nr", "bzw", "ggf", "z.b", "vgl",
})


def _extract_keywords(text: str, *, max_keywords: int = 8) -> list[str]:
    """Extract meaningful German keywords from a query text.

    Strategy:
    1. Split into words, lowercased
    2. Remove stop words and short words (< 4 chars unless uppercase/capitalized)
    3. Keep capitalized words (German nouns) with higher priority
    4. Take the longest words first (they tend to be most specific)
    """
    import re as _re

    # Tokenize on whitespace and punctuation
    words = _re.findall(r"[A-Za-zÖÜÄöüäß]+", text)

    # Categorize
    capitalized = []
    lower = []
    for w in words:
        if len(w) <= 2:
            continue
        wl = w.lower()
        if wl in _LEGAL_STOP_WORDS:
            continue
        if w[0].isupper():
            capitalized.append(w)
        else:
            lower.append(w)

    # Sort: longest first (more specific), deduplicate preserving case
    seen: set[str] = set()
    result: list[str] = []

    def add_unique(word: str) -> None:
        wl = word.lower()
        if wl not in seen:
            seen.add(wl)
            result.append(word)

    # Priority: 1) longest capitalized, 2) longest lowercased
    for word in sorted(capitalized, key=len, reverse=True):
        if len(result) >= max_keywords:
            break
        add_unique(word)

    for word in sorted(lower, key=len, reverse=True):
        if len(result) >= max_keywords:
            break
        add_unique(word)

    return result


async def retrieve_chunks_keyword(
    query_text: str,
    *,
    top_k: int = 5,
    question_index: int = 0,
) -> list[dict[str, Any]]:
    """Retrieve legal chunks using keyword-based ``ilike`` search.

    Falls back to this when vector similarity returns too few results.
    Extracts meaningful German keywords from *query_text* and searches
    ``legal_chunk.text_content`` for matches using PostgreSQL ``ilike``.

    Parameters
    ----------
    query_text :
        The search query (typically a legal question or combined query).
    top_k :
        Maximum number of keyword results to return.
    question_index :
        Index to assign to each result's ``question_index`` key.

    Returns
    -------
    list[dict[str, Any]]
        Chunks with the same structure as :func:`retrieve_chunks` but with
        ``distance`` set to ``0.5`` and ``method`` set to ``"keyword"``.
    """
    keywords = _extract_keywords(query_text)
    if not keywords:
        logger.info("retrieve_chunks_keyword: no keywords extracted from query, skipping")
        return []

    logger.info(
        "retrieve_chunks_keyword: extracted %d keywords: %s",
        len(keywords),
        keywords,
    )

    # Build ilike filters for each keyword
    filters = [LegalChunk.text_content.ilike(f"%{kw}%") for kw in keywords]
    combined_filter = or_(*filters)

    results: list[dict[str, Any]] = []

    async for session in get_async_session():
        stmt = (
            select(
                LegalChunk.id.label("chunk_id"),
                LegalChunk.text_content,
                LegalChunk.hierarchy_path,
                LegalChunk.unit_type,
                LegalChunk.effective_date,
                LegalSource.source_type,
                LegalSource.title,
            )
            .join(LegalSource, LegalSource.id == LegalChunk.source_id)
            .where(combined_filter, LegalSource.is_active.is_(True))
            .limit(top_k)
        )

        result = await session.execute(stmt)
        rows = result.mappings().all()

        seen_cids: set[str] = set()
        for row in rows:
            cid = str(row["chunk_id"])
            if cid in seen_cids:
                continue
            seen_cids.add(cid)

            results.append(
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
                    "distance": 0.5,  # keyword results appear after vector results
                    "method": "keyword",
                    "question_index": question_index,
                }
            )

        await session.close()
        break

    logger.info(
        "retrieve_chunks_keyword: found %d chunks for %d keywords",
        len(results),
        len(keywords),
    )
    return results


# ---------------------------------------------------------------------------
# Fallback helper: merge vector and keyword results with deduplication
# ---------------------------------------------------------------------------

_MIN_CHUNKS_FOR_FALLBACK = 3


def _merge_vector_and_keyword_results(
    vector_chunks: list[dict[str, Any]],
    keyword_chunks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Merge vector and keyword results, deduplicating by ``chunk_id``.

    Keyword results get ``distance=0.5`` so they sort after vector results.
    """
    seen: set[str] = {c["chunk_id"] for c in vector_chunks}
    merged = list(vector_chunks)
    for kc in keyword_chunks:
        if kc["chunk_id"] not in seen:
            seen.add(kc["chunk_id"])
            merged.append(kc)
    merged.sort(key=lambda c: c["distance"])
    return merged
