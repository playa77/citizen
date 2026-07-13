"""Retrieval engine: vector similarity query, diversity constraints, and metadata join.

Given a list of legal questions, this module:
1. Generates an embedding for each question via the OpenRouter embedding API.
2. Queries ``chunk_embedding`` using the cosine distance operator (pgvector
   or sqlite-vec, depending on the dialect-agnostic backend).
3. Filters results by ``MAX_COSINE_DISTANCE`` (cosine distance < threshold).
4. Enforces ``TOP_K_RETRIEVAL`` per question.
5. Joins with ``legal_chunk`` to fetch ``text_content``, ``hierarchy_path``,
   ``source_type``, and other metadata.
6. Deduplicates by ``chunk_id`` and sorts by aggregate relevance.
7. Returns a list of rich dictionaries.
"""

# Semantic Version: 0.2.0

from __future__ import annotations

import logging
import re
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.router import EmbeddingError, OpenRouterClient
from app.db.models import LegalChunk, LegalSource
from app.db.session import get_async_session
from app.db.vector_backend import cosine_distance

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Statute name → source_type mapping (for §-reference direct lookup, WP-20)
# ---------------------------------------------------------------------------

_STATUTE_TO_SOURCE_TYPE: dict[str, list[str]] = {
    "SGB I": ["sgb1"],
    "SGB II": ["sgb2"],
    "SGB III": ["sgb3"],
    "SGB IX": ["sgb9"],
    "SGB X": ["sgbx"],
    "SGB XII": ["sgb12"],
    "BGB": ["bgb"],
    "ErbStG": ["erbstg"],
    "HöfeV": ["hoefev"],
    "VwVfG": ["vwvfg"],
    "SGG": ["sgg"],
    "KSchG": ["kschg"],
    "BUrlG": ["burlg"],
    "TVG": ["tvg"],
}

# Regex to extract norm references like "§ 11b SGB II" or "§§ 45/48/50 SGB X"
_NORM_REF_RE = re.compile(
    r"§{1,2}\s*"
    r"(?P<para>[A-Za-z0-9]+(?:\s*/\s*[A-Za-z0-9]+)*)"
    r"(?:\s+(?:Abs\.\s*\d+(?:[-/]\s*[A-Za-z0-9]+)*|S\.\s*\d+(?:[-/]\s*[A-Za-z0-9]+)*|Nr\.\s*[A-Za-z0-9]+(?:[-/]\s*[A-Za-z0-9]+)*))*"
    r"\s+"
    r"(?P<statute>[A-Za-z\u00C0-\u024F]+(?:\s+(?![nNaA]\.F\.)[A-Za-z\u00C0-\u024F0-9]+){0,3})"
)


class RetrievalError(Exception):
    """Raised when the retrieval engine fails irrecoverably."""


async def retrieve_chunks_for_areas(
    legal_areas: list[str],
    issues: list[str],
    questions: list[str],
    normalized_text: str,
    *,
    client: OpenRouterClient | None = None,
) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    """Per-area retrieval: run retrieval once per area, merge results.

    Parameters
    ----------
    legal_areas :
        One or more legal_area keys (e.g. ``["erbrecht",
        "familienrecht"]``). Areas with no mapped source_types (e.g.
        ``"andere"``) are still represented in the result dict with an
        empty list.
    issues, questions, normalized_text :
        The standard pipeline inputs used to build the combined query.
    client :
        Optional OpenRouter client.

    Returns
    -------
    (per_area, merged)
        ``per_area`` is a ``{area: [chunk, ...]}`` mapping. ``merged``
        is the de-duplicated, distance-sorted union of all per-area
        chunks, capped at ``settings.MAX_CHUNKS_FOR_FINAL`` items.
    """
    from app.core.config import settings as _s
    from app.services.corpus_readiness import AREA_TO_SOURCE_TYPES

    if not legal_areas:
        return {}, []

    per_area_results: dict[str, list[dict[str, Any]]] = {}
    seen: set[str] = set()
    merged: list[dict[str, Any]] = []

    top_k = _s.TOP_K_RETRIEVAL
    threshold = _s.MAX_COSINE_DISTANCE

    for area in legal_areas:
        source_types = AREA_TO_SOURCE_TYPES.get(area, ())
        if not source_types:
            per_area_results[area] = []
            continue

        if _s.RETRIEVAL_MODE == "combined":
            chunks = await retrieve_chunks_combined_filtered(
                issues,
                questions,
                normalized_text,
                source_types=source_types,
                top_k=top_k,
                threshold=threshold,
                client=client,
            )
        else:
            chunks = await retrieve_chunks_per_area(
                questions,
                source_types=source_types,
                top_k=top_k,
                threshold=threshold,
                client=client,
            )

        per_area_results[area] = chunks
        for c in chunks:
            cid = c["chunk_id"]
            if cid in seen:
                continue
            seen.add(cid)
            merged.append(c)

    # Sort merged by distance ascending; cap at MAX_CHUNKS_FOR_FINAL.
    merged.sort(key=lambda c: c["distance"])
    merged = merged[: _s.MAX_CHUNKS_FOR_FINAL]

    # ── WP-20 Lever 3: §-reference direct lookup ──────────────────────────
    # Extract norm references from the document text and look up matching
    # chunks by hierarchy_path. Merge with vector results (dedup by chunk_id,
    # keeping lower distance), sort, and cap again.
    combined_source_types: set[str] = set()
    for area in legal_areas:
        combined_source_types.update(AREA_TO_SOURCE_TYPES.get(area, ()))
    if normalized_text and combined_source_types:
        norm_chunks = await retrieve_chunks_by_norm_reference(
            normalized_text,
            source_types=tuple(combined_source_types),
        )
        if norm_chunks:
            seen_norm: set[str] = set(c["chunk_id"] for c in merged)
            for nc in norm_chunks:
                nc_id = nc["chunk_id"]
                if nc_id in seen_norm:
                    # Keep the lower distance (vector result is probably better)
                    continue
                seen_norm.add(nc_id)
                merged.append(nc)
            merged.sort(key=lambda c: c["distance"])
            merged = merged[: _s.MAX_CHUNKS_FOR_FINAL]

    return per_area_results, merged


async def retrieve_chunks_combined_filtered(
    issues: list[str],
    questions: list[str],
    normalized_text: str,
    *,
    source_types: tuple[str, ...],
    top_k: int,
    threshold: float,
    client: OpenRouterClient | None = None,
) -> list[dict[str, Any]]:
    """Like :func:`retrieve_chunks_combined` but filtered to *source_types*.

    Filters via ``LegalSource.source_type IN (...)`` so multi-area
    retrieval can ask only for BGB chunks for the familienrecht area,
    for example.
    """
    if not issues and not questions:
        return []

    parts: list[str] = []
    if issues:
        parts.append("Themen:\n" + "\n".join(f"- {issue}" for issue in issues))
    if questions:
        parts.append("Rechtsfragen:\n" + "\n".join(f"- {q}" for q in questions))
    if normalized_text:
        parts.append(f"Dokumentauszug:\n{normalized_text[:1200]}")
    combined_query = "\n\n".join(parts)

    embedding: list[float] | None = None
    if client is not None:
        embedding = await client.get_embedding(combined_query)
    else:
        from app.core.router import OpenRouterClient as _ORC
        async with _ORC() as router:
            embedding = await router.get_embedding(combined_query)

    rows: list[dict[str, Any]] = []
    async for session in get_async_session():
        rows = await cosine_distance(
            session,
            embedding=embedding,
            table_name="chunk_embedding",
            id_column="chunk_id",
            vector_column="embedding",
            top_k=top_k,
            threshold=threshold,
            extra_joins=[
                "JOIN legal_chunk lc ON lc.id = ce.chunk_id",
                "JOIN legal_source ls ON ls.id = lc.source_id",
            ],
            extra_columns=[
                "lc.text_content",
                "lc.hierarchy_path",
                "lc.unit_type",
                "lc.effective_date",
                "lc.legal_area",
                "ls.source_type",
                "ls.title",
            ],
            extra_conditions=[
                "ls.is_active = 1",
                f"ls.source_type IN ({', '.join(repr(st) for st in source_types)})",
            ],
        )
        await session.close()
        break

    # Build vector result list
    vector_chunks: list[dict[str, Any]] = [
        {
            "chunk_id": str(row["id"]),
            "text_content": row["lc_text_content"],
            "hierarchy_path": row["lc_hierarchy_path"],
            "unit_type": row["lc_unit_type"],
            "effective_date": str(row["lc_effective_date"]) if row["lc_effective_date"] else "",
            "source_type": row["ls_source_type"],
            "title": row["ls_title"],
            "legal_area": row["lc_legal_area"],
            "distance": float(row["distance"]),
            "question_index": 0,
        }
        for row in rows
    ]

    # ── WP-20 Lever 4: always-on hybrid search with RRF ────────────────
    keyword_chunks = await retrieve_chunks_keyword(
        combined_query,
        top_k=settings.TOP_K_KEYWORD,
        question_index=0,
    )
    vector_chunks = _rrf_fuse(vector_chunks, keyword_chunks)
    return vector_chunks


async def retrieve_chunks_per_area(
    questions: list[str],
    *,
    source_types: tuple[str, ...],
    top_k: int,
    threshold: float,
    client: OpenRouterClient | None = None,
) -> list[dict[str, Any]]:
    """Per-question retrieval filtered to a set of source_types.

    Used by the multi-area path when RETRIEVAL_MODE != "combined".
    """
    if not questions:
        return []

    if client is not None:
        embeddings = await client.get_embeddings_batch(questions)
    else:
        from app.core.router import OpenRouterClient as _ORC
        async with _ORC() as router:
            embeddings = await router.get_embeddings_batch(questions)

    all_chunks: list[dict[str, Any]] = []
    seen: set[str] = set()

    async for session in get_async_session():
        for q_idx, emb in enumerate(embeddings):
            rows = await cosine_distance(
                session,
                embedding=emb,
                table_name="chunk_embedding",
                id_column="chunk_id",
                vector_column="embedding",
                top_k=top_k,
                threshold=threshold,
                extra_joins=[
                    "JOIN legal_chunk lc ON lc.id = ce.chunk_id",
                    "JOIN legal_source ls ON ls.id = lc.source_id",
                ],
                extra_columns=[
                    "lc.text_content",
                    "lc.hierarchy_path",
                    "lc.unit_type",
                    "lc.effective_date",
                    "lc.legal_area",
                    "ls.source_type",
                    "ls.title",
                ],
                extra_conditions=[
                    "ls.is_active = 1",
                    f"ls.source_type IN ({', '.join(repr(st) for st in source_types)})",
                ],
            )
            for row in rows:
                cid = str(row["id"])
                if cid in seen:
                    continue
                seen.add(cid)
                all_chunks.append(
                    {
                        "chunk_id": cid,
                        "text_content": row["lc_text_content"],
                        "hierarchy_path": row["lc_hierarchy_path"],
                        "unit_type": row["lc_unit_type"],
                        "effective_date": str(row["lc_effective_date"]) if row["lc_effective_date"] else "",
                        "source_type": row["ls_source_type"],
                        "title": row["ls_title"],
                        "legal_area": row["lc_legal_area"],
                        "distance": float(row["distance"]),
                        "question_index": q_idx,
                    }
                )
        await session.close()
        break

    # ── WP-20 Lever 4: always-on hybrid search with RRF ────────────────
    keyword_query = "\n".join(questions)
    keyword_chunks = await retrieve_chunks_keyword(
        keyword_query,
        top_k=settings.TOP_K_KEYWORD,
        question_index=0,
    )
    all_chunks = _rrf_fuse(all_chunks, keyword_chunks)
    return all_chunks


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

    # Step 2 — query vector backend per question and aggregate results
    all_chunks: list[dict[str, Any]] = []
    seen_chunk_ids: set[str] = set()

    async for session in get_async_session():
        for q_idx, q_embedding in enumerate(question_embeddings):
            rows = await cosine_distance(
                session,
                embedding=q_embedding,
                table_name="chunk_embedding",
                id_column="chunk_id",
                vector_column="embedding",
                top_k=top_k,
                threshold=threshold,
                extra_joins=[
                    "JOIN legal_chunk lc ON lc.id = ce.chunk_id",
                    "JOIN legal_source ls ON ls.id = lc.source_id",
                ],
                extra_columns=[
                    "lc.text_content",
                    "lc.hierarchy_path",
                    "lc.unit_type",
                    "lc.effective_date",
                    "ls.source_type",
                    "ls.title",
                ],
                extra_conditions=[
                    "ls.is_active = 1",
                ],
            )

            for row in rows:
                cid = str(row["id"])
                if cid in seen_chunk_ids:
                    continue
                seen_chunk_ids.add(cid)

                all_chunks.append(
                    {
                        "chunk_id": cid,
                        "text_content": row["lc_text_content"],
                        "hierarchy_path": row["lc_hierarchy_path"],
                        "unit_type": row["lc_unit_type"],
                        "effective_date": str(row["lc_effective_date"])
                        if row["lc_effective_date"]
                        else "",
                        "source_type": row["ls_source_type"],
                        "title": row["ls_title"],
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
        "Retrieval complete: %d unique chunks for %d questions (threshold=%.2f, top_k=%d)",
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
    generates one embedding and queries the vector backend once.

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

    # Step 2 — query vector backend once
    all_chunks: list[dict[str, Any]] = []
    async for session in get_async_session():
        rows = await cosine_distance(
            session,
            embedding=embedding,
            table_name="chunk_embedding",
            id_column="chunk_id",
            vector_column="embedding",
            top_k=top_k,
            threshold=threshold,
            extra_joins=[
                "JOIN legal_chunk lc ON lc.id = ce.chunk_id",
                "JOIN legal_source ls ON ls.id = lc.source_id",
            ],
            extra_columns=[
                "lc.text_content",
                "lc.hierarchy_path",
                "lc.unit_type",
                "lc.effective_date",
                "lc.legal_area",
                "ls.source_type",
                "ls.title",
            ],
            extra_conditions=[
                "ls.is_active = 1",
            ],
        )

        for row in rows:
            all_chunks.append(
                {
                    "chunk_id": str(row["id"]),
                    "text_content": row["lc_text_content"],
                    "hierarchy_path": row["lc_hierarchy_path"],
                    "unit_type": row["lc_unit_type"],
                    "effective_date": str(row["lc_effective_date"])
                    if row["lc_effective_date"]
                    else "",
                    "source_type": row["ls_source_type"],
                    "title": row["ls_title"],
                    "legal_area": row["lc_legal_area"],
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
    """Internal helper: execute the vector similarity query.

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
    rows = await cosine_distance(
        session,
        embedding=embedding,
        table_name="chunk_embedding",
        id_column="chunk_id",
        vector_column="embedding",
        top_k=top_k,
        threshold=threshold,
        extra_joins=[
            "JOIN legal_chunk lc ON lc.id = ce.chunk_id",
            "JOIN legal_source ls ON ls.id = lc.source_id",
        ],
        extra_columns=[
            "lc.text_content",
            "lc.hierarchy_path",
            "lc.unit_type",
            "lc.effective_date",
            "ls.source_type",
            "ls.title",
        ],
        extra_conditions=[
            "ls.is_active = 1",
        ],
    )

    return [
        {
            "chunk_id": str(row["id"]),
            "text_content": row["lc_text_content"],
            "hierarchy_path": row["lc_hierarchy_path"],
            "unit_type": row["lc_unit_type"],
            "effective_date": str(row["lc_effective_date"]) if row["lc_effective_date"] else "",
            "source_type": row["ls_source_type"],
            "title": row["ls_title"],
            "distance": float(row["distance"]),
        }
        for row in rows
    ]


# ---------------------------------------------------------------------------
# §-Reference direct lookup (WP-20 Lever 3)
# ---------------------------------------------------------------------------


def _extract_norm_references(text: str) -> list[str]:
    """Extract §-references from *text* and return normalised norm strings.

    Uses ``_NORM_REF_RE`` to match patterns like ``§ 11b SGB II`` or
    ``§§ 45/48/50 SGB X``, filters to known statutes, and explodes
    multi-paragraph references (``§§ 45/48/50`` → three individual norms).
    """
    # Strip n.F./a.F. and parentheticals for cleaner matching
    cleaned = re.sub(r"\s+(?:n\.F\.|a\.F\.)", "", text)
    cleaned = re.sub(r"\s*\([^)]*\)", "", cleaned)

    found: list[str] = []
    for match in _NORM_REF_RE.finditer(cleaned):
        raw_para = match.group("para").strip()
        statute = match.group("statute").strip()

        # Skip if statute is not in our known mapping
        if statute not in _STATUTE_TO_SOURCE_TYPE:
            continue

        # Explode multiple paragraphs (e.g. "45/48/50")
        for para in re.split(r"\s*/\s*", raw_para):
            found.append(f"§ {para} {statute}")

    if found:
        logger.info(
            "_extract_norm_references: found %d norm refs: %s",
            len(found),
            found,
        )
    return found


async def retrieve_chunks_by_norm_reference(
    document_text: str,
    source_types: tuple[str, ...],
) -> list[dict[str, Any]]:
    """Look up legal chunks by §-reference extracted from *document_text*.

    For each extracted norm reference (e.g. ``§ 11b SGB II``), builds a
    ``LIKE`` pattern on ``legal_chunk.hierarchy_path`` (e.g. ``%> § 11b%``)
    and queries ``LegalChunk`` joined with ``LegalSource``, filtered by
    *source_types* and ``is_active=True``.

    Returns chunks with ``distance=0.0`` (exact-match boost) and
    ``method="norm_reference"``. These are typically merged with vector
    results in :func:`retrieve_chunks_for_areas`.
    """
    if not document_text:
        return []

    norm_refs = _extract_norm_references(document_text)
    if not norm_refs:
        return []

    results: list[dict[str, Any]] = []
    seen: set[str] = set()

    async for session in get_async_session():
        for norm in norm_refs:
            match = _NORM_REF_RE.match(norm)
            if not match:
                continue
            para = match.group("para").strip()
            statute = match.group("statute").strip()

            # Map statute name → source_types, intersect with requested types
            statute_src_types = _STATUTE_TO_SOURCE_TYPE.get(statute, [])
            matching_src = [st for st in statute_src_types if st in source_types]
            if not matching_src:
                continue

            # hierarchy_path looks like "SGB II > § 11b > Abs. 3"
            hierarchy_pattern = f"%> § {para}%"

            stmt = (
                select(
                    LegalChunk.id.label("chunk_id"),
                    LegalChunk.text_content,
                    LegalChunk.hierarchy_path,
                    LegalChunk.unit_type,
                    LegalChunk.effective_date,
                    LegalChunk.legal_area,
                    LegalSource.source_type,
                    LegalSource.title,
                )
                .join(LegalSource, LegalSource.id == LegalChunk.source_id)
                .where(
                    LegalChunk.hierarchy_path.ilike(hierarchy_pattern),
                    LegalSource.is_active.is_(True),
                    LegalSource.source_type.in_(matching_src),
                )
                .limit(5)  # per norm reference
            )

            result = await session.execute(stmt)
            rows = result.mappings().all()

            for row in rows:
                cid = str(row["chunk_id"])
                if cid in seen:
                    continue
                seen.add(cid)
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
                        "legal_area": row["legal_area"],
                        "distance": 0.0,  # exact-match boost
                        "method": "norm_reference",
                        "question_index": 0,
                    }
                )

        await session.close()
        break

    logger.info(
        "retrieve_chunks_by_norm_reference: found %d chunks for %d norm refs",
        len(results),
        len(norm_refs),
    )
    return results


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
# Reciprocal Rank Fusion (WP-20 Lever 4)
# ---------------------------------------------------------------------------


def _rrf_fuse(
    vector_chunks: list[dict[str, Any]],
    keyword_chunks: list[dict[str, Any]],
    k: int = 60,
) -> list[dict[str, Any]]:
    """Fuse vector and keyword results using Reciprocal Rank Fusion.

    Each chunk appearing in either list gets an RRF score:
    ``(1/(k+vec_rank) if in vector results) + (1/(k+kw_rank) if in keyword results)``.
    Results sorted by RRF score descending, then mapped to ``distance = 1.0 - rrf_score``
    for consistency with the existing sort-by-distance pattern.

    Parameters
    ----------
    vector_chunks :
        Results from vector similarity search, ordered by distance ascending.
    keyword_chunks :
        Results from keyword search, ordered by relevance.
    k :
        Fusion constant (default 60, standard RRF value).

    Returns
    -------
    list[dict[str, Any]]
        Fused results with ``distance`` set to ``1.0 - rrf_score`` and
        ``_rrf_score`` attached for debugging.
    """
    if not keyword_chunks:
        return list(vector_chunks)
    if not vector_chunks:
        # Keyword chunks already have a fixed distance — return as-is
        return list(keyword_chunks)

    # Build rank maps (1-indexed position in each result list)
    vec_ranks: dict[str, int] = {
        c["chunk_id"]: i + 1 for i, c in enumerate(vector_chunks)
    }
    kw_ranks: dict[str, int] = {
        c["chunk_id"]: i + 1 for i, c in enumerate(keyword_chunks)
    }

    # Compute RRF score for every unique chunk
    scored: list[tuple[str, float]] = []
    for cid in set(vec_ranks) | set(kw_ranks):
        v_score = 1.0 / (k + vec_ranks[cid]) if cid in vec_ranks else 0.0
        k_score = 1.0 / (k + kw_ranks[cid]) if cid in kw_ranks else 0.0
        scored.append((cid, v_score + k_score))

    # Sort by RRF score descending
    scored.sort(key=lambda x: x[1], reverse=True)

    # Build full chunk dicts: prefer vector chunk data, fall back to keyword
    chunk_map: dict[str, dict[str, Any]] = {}
    for c in vector_chunks:
        chunk_map[c["chunk_id"]] = c
    for c in keyword_chunks:
        if c["chunk_id"] not in chunk_map:
            chunk_map[c["chunk_id"]] = c

    results: list[dict[str, Any]] = []
    for cid, rrf_score in scored:
        chunk = dict(chunk_map[cid])
        chunk["distance"] = 1.0 - rrf_score  # map to distance for consistency
        chunk["_rrf_score"] = rrf_score
        results.append(chunk)

    logger.debug(
        "_rrf_fuse: fused %d vector + %d keyword = %d results (k=%d)",
        len(vector_chunks),
        len(keyword_chunks),
        len(results),
        k,
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
