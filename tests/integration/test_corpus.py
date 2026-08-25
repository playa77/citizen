"""Integration tests for embedding generation & vector upsert (WP-006).

Tests cover the full upsert pipeline using a real (mocked) OpenRouter
embedding client against the database.  These tests require a live database
and exercise:

* ``generate_embeddings`` — attaches embedding vectors from the API.
* ``upsert_chunks``   — persists LegalSource, LegalChunk, and ChunkEmbedding
  rows with proper ON CONFLICT semantics.
"""

# Semantic Version: 0.1.0

from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from datetime import date
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.router import EmbeddingError, OpenRouterClient
from app.db.models import ChunkEmbedding, LegalChunk
from app.db.session import get_session_factory
from app.services import corpus as corpus_mod

# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------


def _fake_embedding(dim: int = 1536) -> list[float]:
    """Return a dummy dense vector with the correct dimension."""
    return [i / dim for i in range(dim)]


def _make_chunk_dict(raw_text: str, *, source_type: str = "sgb2") -> dict[str, Any]:
    """Build a minimal but complete chunk dict as returned by scrape_and_chunk."""
    return {
        "id": str(uuid4()),
        "source_type": source_type,
        "title": "SGB II",
        "unit_type": "satz",
        "hierarchy_path": f"SGB II > § 31 > Abs. 1 > Satz {len(raw_text)}",
        "text_content": raw_text,
        "effective_date": date.today().isoformat(),
        "source_url": "https://www.gesetze-im-internet.de/sgb_2/",
        "version_hash": corpus_mod._compute_version_hash(raw_text),
        "chunk_id": str(uuid4()),
    }


# -------------------------------------------------------------------
# Fixtures
# -------------------------------------------------------------------


@pytest.fixture
def session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the configured async session factory (real DB)."""
    return get_session_factory()


@pytest.fixture
async def db_session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncSession, None]:
    """Yield a real session without an enclosing transaction.

    ``upsert_chunks`` commits internally (it owns its transaction), so
    wrapping the session in ``session.begin()`` breaks every operation
    after the service-level commit ("closed transaction" errors). Rows
    persist in the disposable testcontainer database; all count assertions
    therefore use ``>=``.
    """
    async with session_factory() as session:
        yield session
        await session.close()


# -------------------------------------------------------------------
# generate_embeddings tests
# -------------------------------------------------------------------


class TestGenerateEmbeddings:
    """Tests for the embedding generation step."""

    @pytest.mark.asyncio
    async def test_empty_list_returns_empty(self) -> None:
        """Calling generate_embeddings with an empty list returns [] immediately."""
        result = await corpus_mod.generate_embeddings([])
        assert result == []

    @pytest.mark.asyncio
    async def test_attaches_embedding_to_each_chunk(self) -> None:
        """Each chunk dict must receive an ``embedding`` key of correct size."""
        chunks = [
            _make_chunk_dict("Der Anspruch besteht."),
            _make_chunk_dict("Er wird gewährt."),
        ]

        async def fake_get_embeddings_batch(
            texts: list[str],
            *,
            model: str | None = None,
            concurrency: int | None = None,
            batch_size: int | None = None,
            progress_cb: Any = None,
        ) -> list[list[float]]:
            result = [_fake_embedding() for _ in texts]
            if progress_cb:
                await progress_cb(len(texts), len(texts))
            return result

        mock_client = AsyncMock(spec=OpenRouterClient)
        mock_client.get_embeddings_batch = AsyncMock(side_effect=fake_get_embeddings_batch)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("app.services.corpus.OpenRouterClient", return_value=mock_client):
            result = await corpus_mod.generate_embeddings(chunks)

        assert len(result) == 2
        for chunk in result:
            assert "embedding" in chunk
            assert len(chunk["embedding"]) == 1536

    @pytest.mark.asyncio
    async def test_injecting_external_client(self) -> None:
        """verify that a provided client is used rather than creating a new one."""
        chunks = [_make_chunk_dict("Test text")]

        async def fake_get_embeddings_batch(
            texts: list[str],
            *,
            model: str | None = None,
            concurrency: int | None = None,
            batch_size: int | None = None,
            progress_cb: Any = None,
        ) -> list[list[float]]:
            result = [_fake_embedding() for _ in texts]
            if progress_cb:
                await progress_cb(len(texts), len(texts))
            return result

        mock_client = AsyncMock(spec=OpenRouterClient)
        mock_client.get_embeddings_batch = AsyncMock(side_effect=fake_get_embeddings_batch)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        result = await corpus_mod.generate_embeddings(chunks, client=mock_client)

        assert len(result) == 1
        assert "embedding" in result[0]
        mock_client.get_embeddings_batch.assert_called_once_with(
            ["Test text"], progress_cb=None
        )

    @pytest.mark.asyncio
    async def test_embedding_error_propagates(self) -> None:
        """If the embedding client raises EmbeddingError, it must bubble up."""
        chunks = [_make_chunk_dict("Will fail")]

        mock_client = AsyncMock(spec=OpenRouterClient)
        mock_client.get_embeddings_batch = AsyncMock(
            side_effect=EmbeddingError("API failure"),
        )
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("app.services.corpus.OpenRouterClient", return_value=mock_client),
            pytest.raises(EmbeddingError, match="API failure"),
        ):
            await corpus_mod.generate_embeddings(chunks)


# -------------------------------------------------------------------
# upsert_chunks tests
# -------------------------------------------------------------------


class TestUpsertChunks:
    """Tests for the DB upsert pipeline."""

    @pytest.fixture(autouse=True)
    async def _clean_slate(self, session_factory: async_sessionmaker[AsyncSession]) -> AsyncGenerator[None, None]:
        """Remove rows belonging to this test's source_url before each test.

        Services commit internally, so data from sibling tests persists in
        the shared disposable database; exact-count assertions need a clean
        slate scoped to their own source.
        """
        from sqlalchemy import text

        async with session_factory() as s:
            await s.execute(
                text("DELETE FROM legal_source WHERE source_url = 'https://www.gesetze-im-internet.de/sgb_2/'")
            )
            await s.commit()
        yield

    @pytest.mark.skipif(
        os.environ.get("SKIP_LIVE_DB") == "1",
        reason="LIVE_DB not available",
    )
    @pytest.mark.asyncio
    async def test_vector_upsert(self, db_session: AsyncSession) -> None:
        """Primary WP-006 acceptance test: upsert creates rows in all 3 tables."""
        chunks = [
            _make_chunk_dict("Der Leistungsberechtigte muss hilfebedürftig sein."),
            _make_chunk_dict("Der Anspruch erlischt mit Zeitablauf."),
        ]
        # Embed manually to avoid real API calls.
        for c in chunks:
            c["embedding"] = _fake_embedding()

        await corpus_mod.upsert_chunks(db_session, chunks)

        # Verify source
        source_count = await db_session.scalar(select(func.count(LegalChunk.id)))
        assert source_count >= len({c["source_type"] for c in chunks})

        # Verify LegalChunk count >= chunks provided

        lc_count = await db_session.scalar(select(func.count(LegalChunk.id)))
        assert lc_count >= len(chunks)

        # Verify ChunkEmbedding count >= chunks provided
        emb_count = await db_session.scalar(select(func.count(ChunkEmbedding.id)))
        assert emb_count >= len(chunks)

    @pytest.mark.skipif(
        os.environ.get("SKIP_LIVE_DB") == "1",
        reason="LIVE_DB not available",
    )
    @pytest.mark.asyncio
    async def test_upsert_idempotent_no_duplicates(self, db_session: AsyncSession) -> None:
        """Calling upsert_chunks twice for the same chunk must not duplicate rows."""
        chunk = _make_chunk_dict("Same content both times.")
        chunk["embedding"] = _fake_embedding()

        await corpus_mod.upsert_chunks(db_session, [chunk])
        await corpus_mod.upsert_chunks(db_session, [chunk])

        # Scope counts to this test's own source — the shared disposable
        # database legitimately holds rows from sibling tests.
        from app.db.models import LegalSource

        source_id = await db_session.scalar(
            select(LegalSource.id).where(LegalSource.source_url == chunk["source_url"])
        )
        lc_count = await db_session.scalar(
            select(func.count(LegalChunk.id)).where(LegalChunk.source_id == source_id)
        )
        emb_count = await db_session.scalar(
            select(func.count(ChunkEmbedding.id))
            .join(LegalChunk, ChunkEmbedding.chunk_id == LegalChunk.id)
            .where(LegalChunk.source_id == source_id)
        )

        assert lc_count == 1
        assert emb_count == 1

    @pytest.mark.skipif(
        os.environ.get("SKIP_LIVE_DB") == "1",
        reason="LIVE_DB not available",
    )
    @pytest.mark.asyncio
    async def test_embedding_vector_in_db(self, db_session: AsyncSession) -> None:
        """Confirm that the IVFFlat index table holds vectors of correct length."""
        from app.db.models import LegalSource

        chunk = _make_chunk_dict("Vector check text.")
        chunk["embedding"] = _fake_embedding()

        await corpus_mod.upsert_chunks(db_session, [chunk])

        # Verify source exists
        src_count = await db_session.scalar(select(func.count(LegalSource.id)))
        assert src_count >= 1

        # Verify embedding stored correctly
        emb_row = await db_session.scalar(select(ChunkEmbedding).limit(1))
        assert emb_row is not None
        assert len(emb_row.embedding) == 1536


# -------------------------------------------------------------------
# OpenRouterClient embedding tests (unit-level, mocking HTTP)
# -------------------------------------------------------------------


@pytest.mark.asyncio
async def test_router_embedding_returns_correct_dim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that the parsed response is a list of length VECTOR_DIM."""
    dim = 1536
    fake_vec = [i / dim for i in range(dim)]
    fake_body: dict[str, Any] = {"data": [{"embedding": fake_vec}]}

    class FakeResponse:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict[str, Any]:
            return fake_body

    async def fake_post(*args: object, **kwargs: object) -> FakeResponse:
        return FakeResponse()

    client = OpenRouterClient()
    monkeypatch.setattr(client._client, "post", fake_post)

    result = await client.get_embedding("test")
    assert len(result) == dim


@pytest.mark.asyncio
async def test_router_embedding_wrong_dim_raises_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the model returns a vector of incorrect dimension, EmbeddingError is raised."""
    fake_vec = [i / 100 for i in range(100)]  # Wrong dimension
    fake_body: dict[str, Any] = {"data": [{"embedding": fake_vec}]}

    class FakeResponse:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict[str, Any]:
            return fake_body

    async def fake_post(*args: object, **kwargs: object) -> FakeResponse:
        return FakeResponse()

    client = OpenRouterClient()
    monkeypatch.setattr(client._client, "post", fake_post)

    with pytest.raises(EmbeddingError, match="Expected embedding dimension"):
        await client.get_embedding("test")
