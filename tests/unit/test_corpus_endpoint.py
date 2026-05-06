"""Unit tests for corpus update background task (WP-013).

Covers the internal ``_run_corpus_update`` function in ``app.api.routes.corpus``.
"""

# Semantic Version: 0.1.0

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, call, patch

import pytest

from app.api.routes.corpus import _run_corpus_update, _job_store

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def clear_job_store():
    """Ensure in-memory job store is clean before each test."""
    _job_store.clear()
    yield
    _job_store.clear()


async def test_run_corpus_update_success(monkeypatch, caplog):
    """Happy path: scraper returns chunks for each source type, embeddings generated, DB upsert succeeds."""
    caplog.set_level(logging.INFO, logger="app.api.routes.corpus")

    job_id = "job-xyz"
    # Pre-seed job store as the endpoint would before scheduling
    _job_store[job_id] = {"status": "queued"}

    # Fake chunks — minimally valid for upsert
    fake_chunks = [
        {
            "id": "1",
            "source_type": "sgb2",
            "title": "SGB II",
            "unit_type": "satz",
            "hierarchy_path": "SGB II > § 31 > Abs. 1 > Satz 1",
            "text_content": "Der Anspruch besteht.",
            "effective_date": "2024-01-01",
            "source_url": "https://example.com",
            "version_hash": "hash1",
            "chunk_id": "1",
            "embedding": [0.0] * 1536,
        }
    ]

    # Mock session
    mock_session = AsyncMock()
    mock_session.commit = AsyncMock()

    # Async context manager behaviour
    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_cm.__aexit__ = AsyncMock(return_value=None)

    with (
        patch("app.api.routes.corpus.scrape_and_chunk", new_callable=AsyncMock) as mock_scrape,
        patch("app.api.routes.corpus.get_session_factory", return_value=lambda: mock_cm),
        patch("app.api.routes.corpus.upsert_chunks", new_callable=AsyncMock) as mock_upsert,
        patch("app.api.routes.corpus.generate_embeddings", new_callable=AsyncMock) as mock_embed,
    ):
        mock_scrape.return_value = fake_chunks
        mock_embed.side_effect = lambda chunks: chunks  # passthrough — embeddings already present
        await _run_corpus_update(job_id)

    # Verify scraper called for each source type in order
    assert mock_scrape.await_count == 4
    source_types = [call_.kwargs["source_type"] for call_ in mock_scrape.await_args_list]
    assert source_types == ["sgb2", "sgbx", "weisung", "bsg"]
    # Verify embed called once with all chunks
    mock_embed.assert_awaited_once()
    # Verify upsert called with chunks
    mock_upsert.assert_awaited_once()
    # Verify job store updated
    assert _job_store[job_id]["status"] == "completed"
    assert _job_store[job_id]["chunks_processed"] == 4


async def test_run_corpus_update_failure(monkeypatch, caplog):
    """If embedding generation fails, job status becomes failed and error is recorded."""
    caplog.set_level(logging.ERROR, logger="app.api.routes.corpus")

    job_id = "job-fail"
    _job_store[job_id] = {"status": "queued"}

    fake_chunks = [
        {
            "id": "1",
            "source_type": "sgb2",
            "title": "SGB II",
            "unit_type": "satz",
            "hierarchy_path": "SGB II > § 31 > Abs. 1 > Satz 1",
            "text_content": "Der Anspruch besteht.",
            "effective_date": "2024-01-01",
            "source_url": "https://example.com",
            "version_hash": "hash1",
            "chunk_id": "1",
            "embedding": [0.0] * 1536,
        }
    ]

    with (
        patch("app.api.routes.corpus.scrape_and_chunk", new_callable=AsyncMock) as mock_scrape,
        patch("app.api.routes.corpus.generate_embeddings", new_callable=AsyncMock) as mock_embed,
    ):
        mock_scrape.return_value = fake_chunks
        mock_embed.side_effect = RuntimeError("Network down")
        await _run_corpus_update(job_id)

    assert _job_store[job_id]["status"] == "failed"
    assert "Network down" in _job_store[job_id]["error"]
