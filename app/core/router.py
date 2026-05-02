"""OpenRouter client with deterministic fallback chain and embedding support."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_API_URL = "https://openrouter.ai/api/v1/chat/completions"
_EMBEDDING_URL = "https://openrouter.ai/api/v1/embeddings"

_HEADERS = {
    "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
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
        self.models: list[str] = [
            settings.PRIMARY_MODEL,
            settings.FALLBACK_MODEL_1,
            settings.FALLBACK_MODEL_2,
        ]
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
    ) -> str:
        """Return the assistant's final text response or raise on exhaustion.

        Args:
            messages: OpenAI-style message history.
            temperature: Sampling temperature (low = deterministic).

        Returns:
            The parsed ``content`` string from the response.

        Raises:
            RouterExhaustedError: If every model / retry attempt fails.
        """
        for model in self.models:
            for attempt in range(1, settings.MAX_RETRIES + 1):
                try:
                    payload: dict[str, Any] = {
                        "model": model,
                        "messages": messages,
                        "temperature": temperature,
                    }
                    resp = await self._client.post(
                        _API_URL,
                        json=payload,
                        headers=_HEADERS,
                    )
                    resp.raise_for_status()
                    body = resp.json()
                    content: str = body["choices"][0]["message"]["content"]
                    return content
                except (httpx.HTTPStatusError, httpx.TimeoutException, httpx.ConnectError) as exc:
                    logger.warning(
                        "chat_completion failed (model=%s, attempt=%d): %s",
                        model,
                        attempt,
                        exc,
                    )
                    if attempt < settings.MAX_RETRIES:
                        await asyncio.sleep(2 ** (attempt - 1))  # 1, 2, 4, ...
                    continue
                except (KeyError, IndexError) as exc:
                    logger.warning(
                        "Malformed API response (model=%s, attempt=%d): %s",
                        model,
                        attempt,
                        exc,
                    )
                    if attempt < settings.MAX_RETRIES:
                        await asyncio.sleep(2 ** (attempt - 1))
                    continue

            logger.info(
                "Model %s exhausted after %d retries, trying next fallback.",
                model,
                settings.MAX_RETRIES,
            )

        raise RouterExhaustedError(f"All models exhausted: {self.models}")

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
        try:
            payload: dict[str, Any] = {
                "model": model_name,
                "input": text,
            }
            resp = await self._client.post(
                _EMBEDDING_URL,
                json=payload,
                headers=_HEADERS,
            )
            resp.raise_for_status()
            body = resp.json()
            embedding: list[float] = body["data"][0]["embedding"]
            if len(embedding) != settings.VECTOR_DIM:
                raise EmbeddingError(
                    f"Expected embedding dimension {settings.VECTOR_DIM}, "
                    f"got {len(embedding)} from model {model_name!r}"
                )
            return embedding
        except (httpx.HTTPStatusError, httpx.TimeoutException, httpx.ConnectError) as exc:
            logger.error("Embedding API failed: %s", exc)
            raise EmbeddingError(f"Embedding API error: {exc}") from exc
        except (KeyError, IndexError) as exc:
            logger.error("Malformed embedding API response: %s", exc)
            raise EmbeddingError(f"Malformed embedding response: {exc}") from exc

    async def get_embeddings_batch(
        self,
        texts: Sequence[str],
        *,
        model: str | None = None,
    ) -> list[list[float]]:
        """Generate embeddings for multiple texts in parallel.

        Args:
            texts: Sequence of input strings.
            model: Override the default embedding model.

        Returns:
            A list of embedding vectors (same order as *texts*).
        """
        tasks = [self.get_embedding(t, model=model) for t in texts]
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
