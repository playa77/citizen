"""Integration tests for the retrieval engine (WP-012).

Tests cover:
* ``retrieve_chunks`` — generates embeddings via a mocked OpenRouter client,
  queries ``pgvector``, applies the diversity threshold, and enforces top-k.
* ``retrieve_chunks_for_question`` — single-question variant.
* Diversity filter correctness (cosine distance < threshold).
* Metadata join correctness (all expected keys present).

These tests require a live PostgreSQL instance with ``pgvector`` extension.
Set ``SKIP_LIVE_DB=1`` to skip DB-dependent tests.
"""

from __future__ import annotations

import math
import os
from collections.abc import AsyncGenerator, Sequence
from datetime import date
from typing import Any
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.core.router import EmbeddingError, OpenRouterClient
from app.db.session import get_session_factory
from app.services.corpus import (
    _compute_version_hash,
    _get_or_create_legal_chunk,
    _get_or_create_source,
    _upsert_embedding,
)
from app.services.retrieval import (
    RetrievalError,
    retrieve_chunks,
    retrieve_chunks_for_question,
)

# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------

_DIM = settings.VECTOR_DIM
_TOP_K = settings.TOP_K_RETRIEVAL
_THRESHOLD = settings.DIVERSITY_THRESHOLD


def _fake_embedding(dim: int = _DIM) -> list[float]:
    """Return a dummy dense vector."""
    return [i / dim for i in range(dim)]


def _cosine_distance(a: list[float], b: list[float]) -> float:
    """Compute cosine distance = 1 - cosine_similarity for two vectors."""
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 1.0
    return 1.0 - (dot / (norm_a * norm_b))


def _make_chunk_dict(raw_text: str) -> dict[str, Any]:
    """Build a minimal chunk dict with all keys needed by upsert helpers."""
    return {
        "source_type": "sgb2",
        "title": "SGB II",
        "unit_type": "satz",
        "hierarchy_path": (f"SGB II > \u00a7 31 > Abs. 1 > Satz {len(raw_text)}"),
        "text_content": raw_text,
        "effective_date": date.today().isoformat(),
        "source_url": "https://www.gesetze-im-internet.de/sgb_2/",
        "version_hash": _compute_version_hash(raw_text),
        "embedding": _fake_embedding(),
    }


# -------------------------------------------------------------------
# Fixtures
# -------------------------------------------------------------------

_session_factory: async_sessionmaker[AsyncSession] | None = None


def _factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = get_session_factory()
    return _session_factory


@pytest.fixture
def session_factory() -> async_sessionmaker[AsyncSession]:
    return _factory()


@pytest.fixture
async def db_session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncSession, None]:
    """Yield a session sharing the app engine.  Data is committed inline so
    the retrieval engine (same engine) can see the rows via MVCC.
    """
    async with session_factory() as session:
        yield session


async def _seed_database(
    session: AsyncSession,
    n_chunks: int = 20,
) -> list[dict[str, Any]]:
    """Insert *n_chunks* LegalChunk rows with embeddings so queries have
    data.  Commits immediately so other sessions can see the rows."""
    seeded: list[dict[str, Any]] = []
    for i in range(n_chunks):
        chunk = _make_chunk_dict(
            f"Rechtstext Nummer {i}: \u00a7 31 SGB II \u2014 " f"Beispielinhalt Nummer {i}."
        )
        source = await _get_or_create_source(session, chunk)
        lc = await _get_or_create_legal_chunk(session, source, chunk)
        await _upsert_embedding(session, lc, chunk)
        chunk["_lc_id"] = lc.id
        seeded.append(chunk)
    await session.commit()
    return seeded


class MockOpenRouterClient(OpenRouterClient):
    """Fake embedding client that returns deterministic vectors."""

    async def get_embedding(self, text: str, *, model: str | None = None) -> list[float]:
        return _generate_deterministic_embedding(text)

    async def get_embeddings_batch(
        self,
        texts: Sequence[str],
        *,
        model: str | None = None,
    ) -> list[list[float]]:
        return [_generate_deterministic_embedding(t) for t in texts]


def _generate_deterministic_embedding(text: str) -> list[float]:
    """Create a reproducible embedding-like vector from text."""
    h = hash(text) & 0xFFFFFFFF
    return [((h * (i + 1)) % 1000) / 1000.0 for i in range(_DIM)]


# -------------------------------------------------------------------
# retrieve_chunks tests
# -------------------------------------------------------------------


class TestRetrieveChunks:
    """Integration tests for the main ``retrieve_chunks`` function."""

    @pytest.mark.asyncio
    async def test_empty_questions_returns_empty(self) -> None:
        result = await retrieve_chunks([])
        assert result == []

    @pytest.mark.skipif(
        os.environ.get("SKIP_LIVE_DB") == "1",
        reason="LIVE_DB not available",
    )
    @pytest.mark.asyncio
    async def test_retrieval_returns_chunks_with_metadata(self, db_session: AsyncSession) -> None:
        await _seed_database(db_session, n_chunks=15)
        mock_client = MockOpenRouterClient()
        result = await retrieve_chunks(
            ["Was sind die Anforderungen an die Hilfebed\u00fcrftigkeit?"],
            client=mock_client,
        )
        assert isinstance(result, list)
        assert len(result) > 0

        mandatory_keys = {
            "chunk_id",
            "text_content",
            "hierarchy_path",
            "source_type",
            "title",
            "distance",
            "question_index",
            "effective_date",
            "unit_type",
        }
        for chunk in result:
            assert mandatory_keys <= set(
                chunk.keys()
            ), f"Missing keys: {mandatory_keys - set(chunk.keys())}"

    @pytest.mark.skipif(
        os.environ.get("SKIP_LIVE_DB") == "1",
        reason="LIVE_DB not available",
    )
    @pytest.mark.asyncio
    async def test_diversity_filter(self, db_session: AsyncSession) -> None:
        """Every returned chunk must have cosine distance < DIVERSITY_THRESHOLD."""
        await _seed_database(db_session, n_chunks=20)
        mock_client = MockOpenRouterClient()
        result = await retrieve_chunks(
            ["Frage nach dem Anspruch auf Arbeitslosengeld?"],
            client=mock_client,
        )
        for chunk in result:
            assert chunk["distance"] < _THRESHOLD, (
                f"Chunk {chunk['chunk_id']} has distance={chunk['distance']} " f">= {_THRESHOLD}"
            )

    @pytest.mark.skipif(
        os.environ.get("SKIP_LIVE_DB") == "1",
        reason="LIVE_DB not available",
    )
    @pytest.mark.asyncio
    async def test_top_k_enforcement_per_question(self, db_session: AsyncSession) -> None:
        await _seed_database(db_session, n_chunks=50)
        mock_client = MockOpenRouterClient()
        questions = [
            "Frage 1: Voraussetzungen SGB II?",
            "Frage 2: Kosten der Unterkunft?",
            "Frage 3: Verfahrensanforderungen?",
        ]
        result = await retrieve_chunks(questions, client=mock_client)
        assert len(result) <= _TOP_K * len(questions)

    @pytest.mark.skipif(
        os.environ.get("SKIP_LIVE_DB") == "1",
        reason="LIVE_DB not available",
    )
    @pytest.mark.asyncio
    async def test_deduplication_by_chunk_id(self, db_session: AsyncSession) -> None:
        await _seed_database(db_session, n_chunks=20)
        mock_client = MockOpenRouterClient()
        questions = [
            "Frage A: Gleiche Semantik?",
            "Frage B: \u00c4hnliche Frage?",
        ]
        result = await retrieve_chunks(questions, client=mock_client)
        seen: set[str] = set()
        for chunk in result:
            assert chunk["chunk_id"] not in seen, f"Duplicate chunk_id: {chunk['chunk_id']}"
            seen.add(chunk["chunk_id"])

    @pytest.mark.skipif(
        os.environ.get("SKIP_LIVE_DB") == "1",
        reason="LIVE_DB not available",
    )
    @pytest.mark.asyncio
    async def test_sorted_by_distance(self, db_session: AsyncSession) -> None:
        await _seed_database(db_session, n_chunks=20)
        mock_client = MockOpenRouterClient()
        result = await retrieve_chunks(["Sortierungs-Test Frage?"], client=mock_client)
        for i in range(1, len(result)):
            assert (
                result[i]["distance"] >= result[i - 1]["distance"]
            ), f"Results not sorted by distance at index {i}"

    @pytest.mark.skipif(
        os.environ.get("SKIP_LIVE_DB") == "1",
        reason="LIVE_DB not available",
    )
    @pytest.mark.asyncio
    async def test_retrieval_error_on_embedding_failure(self) -> None:
        mock_client = AsyncMock(spec=OpenRouterClient)
        mock_client.get_embeddings_batch = AsyncMock(side_effect=EmbeddingError("API outage"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        with pytest.raises(RetrievalError, match="Embedding API failure"):
            await retrieve_chunks(["Some question"], client=mock_client)


# -------------------------------------------------------------------
# retrieve_chunks_for_question tests
# -------------------------------------------------------------------


class TestRetrieveChunksForQuestion:
    """Tests for the single-question variant."""

    @pytest.mark.skipif(
        os.environ.get("SKIP_LIVE_DB") == "1",
        reason="LIVE_DB not available",
    )
    @pytest.mark.asyncio
    async def test_returns_results_with_metadata(self, db_session: AsyncSession) -> None:
        await _seed_database(db_session, n_chunks=15)
        mock_client = MockOpenRouterClient()
        result = await retrieve_chunks_for_question("Einzelne Testfrage?", client=mock_client)
        assert isinstance(result, list)
        if result:
            mandatory_keys = {
                "chunk_id",
                "text_content",
                "hierarchy_path",
                "source_type",
                "title",
                "distance",
                "effective_date",
                "unit_type",
            }
            for chunk in result:
                assert mandatory_keys <= set(chunk.keys())

    @pytest.mark.skipif(
        os.environ.get("SKIP_LIVE_DB") == "1",
        reason="LIVE_DB not available",
    )
    @pytest.mark.asyncio
    async def test_custom_top_k_limit(self, db_session: AsyncSession) -> None:
        await _seed_database(db_session, n_chunks=20)
        mock_client = MockOpenRouterClient()
        result = await retrieve_chunks_for_question(
            "Top-k limit test?", client=mock_client, top_k=3
        )
        assert len(result) <= 3

    @pytest.mark.skipif(
        os.environ.get("SKIP_LIVE_DB") == "1",
        reason="LIVE_DB not available",
    )
    @pytest.mark.asyncio
    async def test_custom_threshold(self, db_session: AsyncSession) -> None:
        await _seed_database(db_session, n_chunks=20)
        mock_client = MockOpenRouterClient()
        result_tight = await retrieve_chunks_for_question(
            "Threshold test?", client=mock_client, threshold=0.5
        )
        result_default = await retrieve_chunks_for_question(
            "Threshold test?", client=mock_client, threshold=0.75
        )
        assert len(result_tight) <= len(result_default)
        for chunk in result_tight:
            assert chunk["distance"] < 0.5

    @pytest.mark.skipif(
        os.environ.get("SKIP_LIVE_DB") == "1",
        reason="LIVE_DB not available",
    )
    @pytest.mark.asyncio
    async def test_retrieval_error_raises(self, db_session: AsyncSession) -> None:
        mock_client = AsyncMock(spec=OpenRouterClient)
        mock_client.get_embedding = AsyncMock(side_effect=EmbeddingError("Connection refused"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        with pytest.raises(RetrievalError, match="Embedding API failure"):
            await retrieve_chunks_for_question("Will fail", client=mock_client)


# -------------------------------------------------------------------
# Pure unit tests — no DB required
# -------------------------------------------------------------------


class TestCosineDistance:
    """Verify the cosine distance helper used in verification."""

    def test_identical_vectors_zero_distance(self) -> None:
        v = [0.1, 0.2, 0.3, 0.4]
        assert _cosine_distance(v, v) == pytest.approx(0.0, abs=1e-6)

    def test_orthogonal_vectors_distance_near_one(self) -> None:
        a = [1.0, 0.0, 0.0, 0.0]
        b = [0.0, 1.0, 0.0, 0.0]
        assert _cosine_distance(a, b) == pytest.approx(1.0, abs=1e-6)

    def test_negative_distance_is_valid(self) -> None:
        a = [0.1] * 10
        b = [0.2] * 10
        d = _cosine_distance(a, b)
        assert isinstance(d, float)
        assert d >= -1e-9
