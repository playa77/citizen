"""OpenRouter client with deterministic fallback chain and embedding support."""

# Semantic Version: 0.1.0

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncGenerator, Sequence
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_API_URL = "https://openrouter.ai/api/v1/chat/completions"
_EMBEDDING_URL = "https://openrouter.ai/api/v1/embeddings"


def _deduplicate_preserve_order(items: list[str]) -> list[str]:
    """Remove duplicate model names while preserving first-occurrence order."""
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result

def _headers() -> dict[str, str]:
    """Build headers dynamically so settings are not frozen at import time."""
    settings_now = settings  # triggers lazy load via __getattr__
    return {
        "Authorization": f"Bearer {settings_now.OPENROUTER_API_KEY}",
        "HTTP-Referer": "http://localhost:8000",
        "X-Title": "Citizen Legal Engine",
        "Content-Type": "application/json",
    }


class RouterExhaustedError(Exception):
    """Raised when all models in the fallback chain have been exhausted."""


class EmbeddingError(Exception):
    """Raised when the embedding API fails."""


class OpenRouterClient:
    """HTTP client for the OpenRouter API with retry / fallback logic.

    The fallback chain is: PRIMARY_MODEL → FALLBACK_MODEL_1 → FALLBACK_MODEL_2.
    Each model is retried up to ``settings.MAX_RETRIES`` times with exponential
    back-off before falling through to the next model.
    """

    def __init__(self, *, client: httpx.AsyncClient | None = None) -> None:
        self.models: list[str] = _deduplicate_preserve_order(
            [
                settings.PRIMARY_MODEL,
                settings.FALLBACK_MODEL_1,
                settings.FALLBACK_MODEL_2,
            ]
        )
        self._owned = client is None
        self._client = client or httpx.AsyncClient(timeout=settings.REQUEST_TIMEOUT)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def chat_completion(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.1,
        model: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        models: list[str] | None = None,
    ) -> str:
        """Return the assistant's final text response or raise on exhaustion.

        Args:
            messages: OpenAI-style message history.
            temperature: Sampling temperature (low = deterministic).
            model: Override the fallback chain with a single specific model.
                   When provided, only that model is used (no fallback, no retries
                   across models). Ignored if *models* is also provided.
            timeout: Per-call HTTP timeout in seconds. Overrides the client-level
                     ``settings.REQUEST_TIMEOUT`` for this call only.
            max_retries: Maximum attempts per model (defaults to
                         ``settings.MAX_RETRIES``).
            models: Explicit fallback chain (deduplicated, order-preserving). When
                    provided, *model* is ignored and this chain is used instead.

        Returns:
            The parsed ``content`` string from the response.

        Raises:
            RouterExhaustedError: If every model / retry attempt fails.
        """
        effective_max_retries = max_retries if max_retries is not None else settings.MAX_RETRIES
        timeout_config = httpx.Timeout(timeout) if timeout is not None else None

        if models is not None:
            effective_models = _deduplicate_preserve_order(models)
        elif model is not None:
            effective_models = [model]
        else:
            effective_models = self.models

        for current_model in effective_models:
            for attempt in range(1, effective_max_retries + 1):
                try:
                    payload: dict[str, Any] = {
                        "model": current_model,
                        "messages": messages,
                        "temperature": temperature,
                    }
                    logger.info(
                        "chat_completion → sending (model=%s, attempt=%d/%d, msg_chars=%d)",
                        current_model,
                        attempt,
                        effective_max_retries,
                        sum(len(m.get("content", "")) for m in messages),
                    )
                    req_start = time.monotonic()
                    resp = await self._client.post(
                        _API_URL,
                        json=payload,
                        headers=_headers(),
                        timeout=timeout_config,
                    )
                    req_elapsed = time.monotonic() - req_start
                    resp.raise_for_status()
                    body = resp.json()
                    content: str = body["choices"][0]["message"]["content"]
                    prompt_chars = sum(len(m.get("content", "")) for m in messages)
                    response_chars = len(content)
                    logger.info(
                        "chat_completion OK (model=%s, attempt=%d/%d, elapsed=%.2fs, prompt_chars=%d, response_chars=%d)",
                        current_model,
                        attempt,
                        effective_max_retries,
                        req_elapsed,
                        prompt_chars,
                        response_chars,
                    )
                    return content
                except (httpx.HTTPStatusError, httpx.TimeoutException, httpx.ConnectError) as exc:
                    fail_elapsed = time.monotonic() - req_start
                    fail_reason = type(exc).__name__
                    if isinstance(exc, httpx.HTTPStatusError):
                        fail_reason = f"HTTP {exc.response.status_code}"
                    logger.warning(
                        "chat_completion FAILED (model=%s, attempt=%d/%d, elapsed=%.2fs, reason=%s): %s",
                        current_model,
                        attempt,
                        effective_max_retries,
                        fail_elapsed,
                        fail_reason,
                        exc,
                    )
                    if attempt < effective_max_retries:
                        await asyncio.sleep(2 ** (attempt - 1))  # 1, 2, 4, ...
                    continue
                except (KeyError, IndexError) as exc:
                    fail_elapsed = time.monotonic() - req_start
                    logger.warning(
                        "Malformed API response (model=%s, attempt=%d/%d, elapsed=%.2fs, reason=malformed_response): %s",
                        current_model,
                        attempt,
                        effective_max_retries,
                        fail_elapsed,
                        exc,
                    )
                    if attempt < effective_max_retries:
                        await asyncio.sleep(2 ** (attempt - 1))
                    continue

            logger.info(
                "Model %s exhausted after %d retries, trying next fallback.",
                current_model,
                effective_max_retries,
            )

        raise RouterExhaustedError(f"All models exhausted: {effective_models}")

    async def chat_completion_stream(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.1,
        model: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        models: list[str] | None = None,
    ) -> AsyncGenerator[str, None]:
        """Stream tokens from a chat completion via SSE.

        Accepts the same parameters as :meth:`chat_completion` but adds
        ``"stream": true`` to the request payload and yields each content
        token string as it arrives from the SSE stream.

        Args:
            Same as :meth:`chat_completion`.

        Yields:
            Content token strings from ``choices[0].delta.content``.

        Raises:
            RouterExhaustedError: If every model / retry attempt fails.
        """
        effective_max_retries = max_retries if max_retries is not None else settings.MAX_RETRIES
        timeout_config = httpx.Timeout(timeout) if timeout is not None else None

        if models is not None:
            effective_models = _deduplicate_preserve_order(models)
        elif model is not None:
            effective_models = [model]
        else:
            effective_models = self.models

        for current_model in effective_models:
            for attempt in range(1, effective_max_retries + 1):
                try:
                    payload: dict[str, Any] = {
                        "model": current_model,
                        "messages": messages,
                        "temperature": temperature,
                        "stream": True,
                    }
                    logger.info(
                        "chat_completion_stream → streaming (model=%s, attempt=%d/%d, msg_chars=%d)",
                        current_model,
                        attempt,
                        effective_max_retries,
                        sum(len(m.get("content", "")) for m in messages),
                    )
                    req_start = time.monotonic()
                    async with self._client.stream(
                        "POST",
                        _API_URL,
                        json=payload,
                        headers=_headers(),
                        timeout=timeout_config,
                    ) as resp:
                        resp.raise_for_status()
                        token_count = 0
                        async for line in resp.aiter_lines():
                            line = line.strip()
                            if not line:
                                continue
                            if line.startswith("data: "):
                                data_str = line[6:]
                                if data_str == "[DONE]":
                                    break
                                try:
                                    chunk = json.loads(data_str)
                                    delta = chunk["choices"][0]["delta"]
                                    content = delta.get("content", "")
                                    if content:
                                        token_count += 1
                                        yield content
                                except (KeyError, IndexError, json.JSONDecodeError):
                                    continue

                    req_elapsed = time.monotonic() - req_start
                    logger.info(
                        "chat_completion_stream OK (model=%s, attempt=%d/%d, elapsed=%.2fs, tokens=%d)",
                        current_model,
                        attempt,
                        effective_max_retries,
                        req_elapsed,
                        token_count,
                    )
                    return

                except (httpx.HTTPStatusError, httpx.TimeoutException, httpx.ConnectError) as exc:
                    fail_elapsed = time.monotonic() - req_start
                    fail_reason = type(exc).__name__
                    if isinstance(exc, httpx.HTTPStatusError):
                        fail_reason = f"HTTP {exc.response.status_code}"
                    logger.warning(
                        "chat_completion_stream FAILED (model=%s, attempt=%d/%d, elapsed=%.2fs, reason=%s): %s",
                        current_model,
                        attempt,
                        effective_max_retries,
                        fail_elapsed,
                        fail_reason,
                        exc,
                    )
                    if attempt < effective_max_retries:
                        await asyncio.sleep(2 ** (attempt - 1))
                    continue

            logger.info(
                "Model %s exhausted after %d retries, trying next fallback.",
                current_model,
                effective_max_retries,
            )

        raise RouterExhaustedError(f"All models exhausted: {effective_models}")

    async def get_embedding(self, text: str, *, model: str | None = None) -> list[float]:
        """Generate an embedding vector for *text* via the OpenRouter embeddings endpoint.

        Args:
            text: Input text to embed.
            model: Override the default ``settings.EMBEDDING_MODEL``.

        Returns:
            A ``list[float]`` of length ``settings.VECTOR_DIM``.

        Raises:
            EmbeddingError: On HTTP or parsing failure.
        """
        model_name = model or settings.EMBEDDING_MODEL
        prompt_chars = len(text)
        req_start: float = 0.0
        logger.info(
            "get_embedding → sending (model=%s, input_chars=%d)",
            model_name,
            prompt_chars,
        )
        try:
            payload: dict[str, Any] = {
                "model": model_name,
                "input": text,
            }
            req_start = time.monotonic()
            resp = await self._client.post(
                _EMBEDDING_URL,
                json=payload,
                headers=_headers(),
            )
            req_elapsed = time.monotonic() - req_start
            resp.raise_for_status()
            body = resp.json()
            # ── Detect OpenRouter-level error responses ─────────────────
            if "error" in body and "data" not in body:
                err_detail = body["error"]
                err_msg = err_detail.get("message", str(err_detail)) if isinstance(err_detail, dict) else str(err_detail)
                fail_elapsed = time.monotonic() - req_start
                logger.error(
                    "get_embedding FAILED (model=%s, elapsed=%.2fs, reason=api_error): %s | body=%s",
                    model_name,
                    fail_elapsed,
                    err_msg,
                    str(body)[:500],
                )
                raise EmbeddingError(f"Embedding API returned error: {err_msg}") from None
            embedding: list[float] = body["data"][0]["embedding"]
            if len(embedding) != settings.VECTOR_DIM:
                raise EmbeddingError(
                    f"Expected embedding dimension {settings.VECTOR_DIM}, "
                    f"got {len(embedding)} from model {model_name!r}"
                )
            logger.info(
                "get_embedding OK (model=%s, elapsed=%.2fs, input_chars=%d, dim=%d)",
                model_name,
                req_elapsed,
                prompt_chars,
                len(embedding),
            )
            return embedding
        except (httpx.HTTPStatusError, httpx.TimeoutException, httpx.ConnectError) as exc:
            fail_elapsed = time.monotonic() - req_start
            fail_reason = type(exc).__name__
            if isinstance(exc, httpx.HTTPStatusError):
                fail_reason = f"HTTP {exc.response.status_code}"
            logger.error(
                "get_embedding FAILED (model=%s, elapsed=%.2fs, reason=%s): %s",
                model_name,
                fail_elapsed,
                fail_reason,
                exc,
            )
            raise EmbeddingError(f"Embedding API error: {exc}") from exc
        except (KeyError, IndexError) as exc:
            fail_elapsed = time.monotonic() - req_start
            # Capture response body for diagnostics when structure is unexpected
            try:
                response_preview = str(body)[:500]
            except Exception:
                response_preview = "<unavailable>"
            logger.error(
                "get_embedding FAILED (model=%s, elapsed=%.2fs, reason=malformed_response): %s | body=%s",
                model_name,
                fail_elapsed,
                exc,
                response_preview,
            )
            raise EmbeddingError(f"Malformed embedding response: {exc}") from exc

    async def get_embeddings_batch(
        self,
        texts: Sequence[str],
        *,
        model: str | None = None,
        concurrency: int = 8,
    ) -> list[list[float]]:
        """Generate embeddings for multiple texts with bounded concurrency.

        Args:
            texts: Sequence of input strings.
            model: Override the default embedding model.
            concurrency: Maximum number of simultaneous requests (default 8).

        Returns:
            A list of embedding vectors (same order as *texts*).
        """
        if not texts:
            return []

        semaphore = asyncio.Semaphore(concurrency)

        async def embed_one(text: str) -> list[float]:
            async with semaphore:
                return await self.get_embedding(text, model=model)

        tasks = [embed_one(t) for t in texts]
        results = await asyncio.gather(*tasks)
        return list(results)

    async def close(self) -> None:
        """Close the underlying httpx client if owned."""
        if self._owned:
            await self._client.aclose()

    async def __aenter__(self) -> OpenRouterClient:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.close()
