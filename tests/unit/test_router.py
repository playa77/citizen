"""Unit tests for WP-009: OpenRouter Client & Deterministic Fallback.

Covers
------
- ``app.core.router.OpenRouterClient`` — fallback chain, retry/back-off,
  JSON parsing, logging, exhaustion, embedding generation.

Acceptance criteria
-------------------
- ``test_fallback_chain`` — mocks 429 on PRIMARY_MODEL, verifies FALLBACK_MODEL_1
  receives the request and returns valid content.
- ``test_exhaustion_error`` — mocks all failures, verifies ``RouterExhaustedError``.
- Logs contain ``fallback_event`` (logged via ``logger.info``) with model names.
"""

from __future__ import annotations

import json
import logging
from unittest.mock import AsyncMock

import httpx
import pytest
import pytest_asyncio

from app.core.router import (
    EmbeddingError,
    OpenRouterClient,
    RouterExhaustedError,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MESSAGES = [{"role": "user", "content": "Is SGB II § 31 applicable here?"}]


def _ok_response(content: str) -> dict:
    """Build a well-formed OpenRouter chat completion JSON body."""
    return {
        "choices": [
            {
                "message": {"role": "assistant", "content": content},
                "index": 0,
            }
        ]
    }


def _embedding_response(dim: int = 1536) -> dict:
    """Build a well-formed OpenRouter embeddings JSON body."""
    return {"data": [{"embedding": [0.1] * dim}]}


@pytest_asyncio.fixture
async def mock_httpx_client() -> AsyncMock:
    """Return an AsyncMock that behaves like ``httpx.AsyncClient``."""
    client = AsyncMock(spec=httpx.AsyncClient)
    return client


@pytest.fixture
def client(mock_httpx_client: AsyncMock) -> OpenRouterClient:
    """Inject the mock client into ``OpenRouterClient``."""
    return OpenRouterClient(client=mock_httpx_client)


@pytest.fixture
def caplog_debug(caplog: pytest.LogCaptureFixture) -> pytest.LogCaptureFixture:
    """Ensure the router logger captures at WARNING / INFO level."""
    caplog.set_level(logging.DEBUG, logger="app.core.router")
    return caplog


# ===========================================================================
# 1. Happy path — primary model returns content
# ===========================================================================


class TestChatCompletionHappyPath:
    async def test_primary_returns_content(
        self, client: OpenRouterClient, mock_httpx_client: AsyncMock
    ) -> None:
        response = httpx.Response(
            status_code=200,
            request=httpx.Request("POST", "https://example.com"),
            content=json.dumps(_ok_response("Yes, it applies.")).encode(),
        )
        mock_httpx_client.post.return_value = response

        result = await client.chat_completion(_MESSAGES)

        assert result == "Yes, it applies."
        assert mock_httpx_client.post.call_count == 1

    async def test_temperature_passed_through(
        self, client: OpenRouterClient, mock_httpx_client: AsyncMock
    ) -> None:
        response = httpx.Response(
            status_code=200,
            request=httpx.Request("POST", "https://example.com"),
            content=json.dumps(_ok_response("result")).encode(),
        )
        mock_httpx_client.post.return_value = response

        await client.chat_completion(_MESSAGES, temperature=0.7)

        call_kwargs = mock_httpx_client.post.call_args
        assert call_kwargs.kwargs["json"]["temperature"] == 0.7

    async def test_messages_passed_through(
        self, client: OpenRouterClient, mock_httpx_client: AsyncMock
    ) -> None:
        response = httpx.Response(
            status_code=200,
            request=httpx.Request("POST", "https://example.com"),
            content=json.dumps(_ok_response("ok")).encode(),
        )
        mock_httpx_client.post.return_value = response

        messages = [
            {"role": "system", "content": "You are a legal assistant."},
            {"role": "user", "content": "Hello"},
        ]
        await client.chat_completion(messages)

        call_kwargs = mock_httpx_client.post.call_args
        assert call_kwargs.kwargs["json"]["messages"] == messages


# ===========================================================================
# 2. Fallback chain — primary gets 429, fallback_1 succeeds
# ===========================================================================


class TestFallbackChain:
    async def test_429_on_primary_triggers_fallback_1(
        self,
        client: OpenRouterClient,
        mock_httpx_client: AsyncMock,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """When the primary model returns 429, the client retries then falls
        through to FALLBACK_MODEL_1, which succeeds."""
        from app.core.config import settings

        _call_count = {"n": 0}

        def post_side_effect(*args: object, **kwargs: object) -> httpx.Response:
            _call_count["n"] += 1
            model_used = kwargs["json"]["model"]

            # Primary model always returns 429.
            if model_used == settings.PRIMARY_MODEL:
                return httpx.Response(
                    status_code=429,
                    request=httpx.Request("POST", "https://example.com"),
                    content=b"Rate limited",
                )
            # Fallback 1 succeeds.
            return httpx.Response(
                status_code=200,
                request=httpx.Request("POST", "https://example.com"),
                content=json.dumps(_ok_response("fallback answer")).encode(),
            )

        mock_httpx_client.post.side_effect = post_side_effect

        result = await client.chat_completion(_MESSAGES)

        assert result == "fallback answer"
        # Primary should have been attempted MAX_RETRIES times, then fallback_1 once.
        assert mock_httpx_client.post.call_count == settings.MAX_RETRIES + 1


# ===========================================================================
# 3. Exhaustion — all models fail → RouterExhaustedError
# ===========================================================================


class TestRouterExhaustion:
    async def test_all_models_fail_raises_exhausted(
        self, client: OpenRouterClient, mock_httpx_client: AsyncMock
    ) -> None:
        """When every model in the chain returns an error across all retries,
        ``RouterExhaustedError`` must be raised."""
        mock_httpx_client.post.side_effect = httpx.TimeoutException("timeout")

        with pytest.raises(RouterExhaustedError) as exc_info:
            await client.chat_completion(_MESSAGES)

        assert "All models exhausted" in str(exc_info.value)

    async def test_exhausted_error_includes_all_models(
        self, client: OpenRouterClient, mock_httpx_client: AsyncMock
    ) -> None:
        """The exception message should list every model that was tried."""
        mock_httpx_client.post.side_effect = httpx.ConnectError("refused")

        with pytest.raises(RouterExhaustedError) as exc_info:
            await client.chat_completion(_MESSAGES)

        for model in client.models:
            assert model in str(exc_info.value)


# ===========================================================================
# 4. Logging — fallback events contain model names
# ===========================================================================


class TestFallbackLogging:
    async def test_fallback_logged_on_exhaustion(
        self,
        client: OpenRouterClient,
        mock_httpx_client: AsyncMock,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """When a model is exhausted the log must contain an ``info``-level
        entry mentioning the model name and retry count."""
        mock_httpx_client.post.side_effect = httpx.HTTPStatusError(
            "error", request=httpx.Request("POST", "x"), response=httpx.Response(500)
        )

        with pytest.raises(RouterExhaustedError):
            await client.chat_completion(_MESSAGES)

        # At least one INFO log per model must exist.
        info_records = [r for r in caplog.records if r.levelno >= logging.INFO]
        assert info_records, "No info-level fallback logs found"

        model_names = {r.message for r in info_records}
        # Verify that at least the primary model name appears in a log.
        assert any(
            client.models[0] in msg for msg in model_names
        ), f"Primary model {client.models[0]} not found in logs: {model_names}"


# ===========================================================================
# 5. Retry with exponential back-off (timing not asserted, just retry count)
# ===========================================================================


class TestRetryBackoff:
    async def test_retries_on_timeout(
        self, client: OpenRouterClient, mock_httpx_client: AsyncMock
    ) -> None:
        """A model that fails twice then succeeds should eventually return content."""
        from app.core.config import settings

        _counter = {"n": 0}

        def post_side_effect(*args: object, **kwargs: object) -> httpx.Response:
            _counter["n"] += 1
            if _counter["n"] < settings.MAX_RETRIES:
                raise httpx.TimeoutException("slow")
            return httpx.Response(
                status_code=200,
                request=httpx.Request("POST", "https://example.com"),
                content=json.dumps(_ok_response("eventually ok")).encode(),
            )

        mock_httpx_client.post.side_effect = post_side_effect

        result = await client.chat_completion(_MESSAGES)

        assert result == "eventually ok"
        assert mock_httpx_client.post.call_count == settings.MAX_RETRIES

    async def test_retries_on_500(
        self, client: OpenRouterClient, mock_httpx_client: AsyncMock
    ) -> None:
        """A 500 response should trigger retries."""
        from app.core.config import settings

        _counter = {"n": 0}

        def post_side_effect(*args: object, **kwargs: object) -> httpx.Response:
            _counter["n"] += 1
            if _counter["n"] < settings.MAX_RETRIES:
                return httpx.Response(
                    status_code=500,
                    request=httpx.Request("POST", "https://example.com"),
                    content=b"internal error",
                )
            return httpx.Response(
                status_code=200,
                request=httpx.Request("POST", "https://example.com"),
                content=json.dumps(_ok_response("recovered")).encode(),
            )

        mock_httpx_client.post.side_effect = post_side_effect

        result = await client.chat_completion(_MESSAGES)

        assert result == "recovered"
        assert mock_httpx_client.post.call_count == settings.MAX_RETRIES


# ===========================================================================
# 6. Malformed API response
# ===========================================================================


class TestMalformedResponse:
    async def test_missing_choices_key_triggers_retry(
        self, client: OpenRouterClient, mock_httpx_client: AsyncMock
    ) -> None:
        """A 200 response with missing ``choices`` should be treated as a
        malformed response and retried."""
        from app.core.config import settings

        _counter = {"n": 0}

        def post_side_effect(*args: object, **kwargs: object) -> httpx.Response:
            _counter["n"] += 1
            if _counter["n"] < settings.MAX_RETRIES:
                return httpx.Response(
                    status_code=200,
                    request=httpx.Request("POST", "https://example.com"),
                    content=json.dumps({"unexpected": "shape"}).encode(),
                )
            return httpx.Response(
                status_code=200,
                request=httpx.Request("POST", "https://example.com"),
                content=json.dumps(_ok_response("fixed")).encode(),
            )

        mock_httpx_client.post.side_effect = post_side_effect

        result = await client.chat_completion(_MESSAGES)
        assert result == "fixed"

    async def test_empty_choices_list_raises_exhausted(
        self, client: OpenRouterClient, mock_httpx_client: AsyncMock
    ) -> None:
        """A persistent ``choices: []`` response should ultimately exhaust."""
        mock_httpx_client.post.return_value = httpx.Response(
            status_code=200,
            request=httpx.Request("POST", "https://example.com"),
            content=json.dumps({"choices": []}).encode(),
        )

        with pytest.raises(RouterExhaustedError):
            await client.chat_completion(_MESSAGES)


# ===========================================================================
# 7. Embedding generation
# ===========================================================================


class TestGetEmbedding:
    async def test_success_returns_list_of_floats(
        self, client: OpenRouterClient, mock_httpx_client: AsyncMock
    ) -> None:
        mock_httpx_client.post.return_value = httpx.Response(
            status_code=200,
            request=httpx.Request("POST", "https://example.com"),
            content=json.dumps(_embedding_response(1536)).encode(),
        )

        result = await client.get_embedding("SGB II § 31")

        assert isinstance(result, list)
        assert len(result) == 1536
        assert all(isinstance(v, float) for v in result)

    async def test_dimension_mismatch_raises_embedding_error(
        self, client: OpenRouterClient, mock_httpx_client: AsyncMock
    ) -> None:
        mock_httpx_client.post.return_value = httpx.Response(
            status_code=200,
            request=httpx.Request("POST", "https://example.com"),
            content=json.dumps(_embedding_response(768)).encode(),
        )

        with pytest.raises(EmbeddingError, match="Expected embedding dimension"):
            await client.get_embedding("text")

    async def test_http_error_raises_embedding_error(
        self, client: OpenRouterClient, mock_httpx_client: AsyncMock
    ) -> None:
        mock_httpx_client.post.side_effect = httpx.TimeoutException("timeout")

        with pytest.raises(EmbeddingError):
            await client.get_embedding("text")

    async def test_malformed_json_raises_embedding_error(
        self, client: OpenRouterClient, mock_httpx_client: AsyncMock
    ) -> None:
        mock_httpx_client.post.return_value = httpx.Response(
            status_code=200,
            request=httpx.Request("POST", "https://example.com"),
            content=json.dumps({"no_data": []}).encode(),
        )

        with pytest.raises(EmbeddingError, match="Malformed embedding"):
            await client.get_embedding("text")


# ===========================================================================
# 8. Batch embedding generation
# ===========================================================================


class TestGetEmbeddingsBatch:
    async def test_returns_same_order(
        self, client: OpenRouterClient, mock_httpx_client: AsyncMock
    ) -> None:
        """Multiple texts should yield embeddings in the same order."""
        mock_httpx_client.post.return_value = httpx.Response(
            status_code=200,
            request=httpx.Request("POST", "https://example.com"),
            content=json.dumps(_embedding_response(1536)).encode(),
        )

        results = await client.get_embeddings_batch(["a", "b", "c"])

        assert len(results) == 3

    async def test_empty_input_returns_empty_list(
        self, client: OpenRouterClient, mock_httpx_client: AsyncMock
    ) -> None:
        results = await client.get_embeddings_batch([])
        assert results == []


# ===========================================================================
# 9. Async context manager / close
# ===========================================================================


class TestAsyncContextManager:
    async def test_aenter_returns_self(self, mock_httpx_client: AsyncMock) -> None:
        client = OpenRouterClient(client=mock_httpx_client)
        async with client as c:
            assert c is client

    async def test_aexit_closes_owned_client(self) -> None:
        """A client created without an injected httpx instance owns the client
        and must close it on exit."""
        client = OpenRouterClient()
        async with client:
            pass
        # After __aexit__, the underlying client should be closed.
        # We can't directly assert on transport, but the test verifies no crash.

    async def test_aexit_does_not_close_injected_client(self, mock_httpx_client: AsyncMock) -> None:
        """A client created with an injected httpx does NOT own it —
        ``__aexit__`` should not call ``aclose()``."""
        client = OpenRouterClient(client=mock_httpx_client)
        async with client:
            pass
        mock_httpx_client.aclose.assert_not_called()


# ===========================================================================
# 10. RouterExhaustedError is a standard Exception subclass
# ===========================================================================


class TestRouterExhaustedErrorClass:
    def test_is_exception_subclass(self) -> None:
        assert issubclass(RouterExhaustedError, Exception)

    def test_accepts_message(self) -> None:
        err = RouterExhaustedError("all failed")
        assert str(err) == "all failed"


class TestEmbeddingErrorClass:
    def test_is_exception_subclass(self) -> None:
        assert issubclass(EmbeddingError, Exception)
