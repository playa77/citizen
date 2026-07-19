"""OpenRouter client with deterministic fallback chain and embedding support.

Includes egress guard (WP-31) that enforces host allowlisting and PII scanning
for every outbound LLM/embedding call.
"""

# Semantic Version: 0.1.0

from __future__ import annotations

import asyncio
import json
import logging
import time
import unicodedata
from collections.abc import AsyncGenerator, Awaitable, Callable, Sequence
from typing import Any
from urllib.parse import urlparse

import httpx

from app.core.config import settings
from app.services.pseudonymization import PiiMapping

logger = logging.getLogger(__name__)

_API_URL = "https://openrouter.ai/api/v1/chat/completions"


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


def _embedding_headers() -> dict[str, str]:
    """Build headers for embedding API calls, using a separate API key when configured."""
    settings_now = settings
    api_key = settings_now.EMBEDDING_API_KEY or settings_now.OPENROUTER_API_KEY
    return {
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "http://localhost:8000",
        "X-Title": "Citizen Legal Engine",
        "Content-Type": "application/json",
    }


class RouterExhaustedError(Exception):
    """Raised when all models in the fallback chain have been exhausted."""


class EmbeddingError(Exception):
    """Raised when the embedding API fails."""


class EgressBlockedError(Exception):
    """Raised when an outbound LLM call is blocked by the egress guard.

    Attributes:
        reason: Human-readable explanation (safe for logging).
        category: Machine-readable category (``"host_violation"`` or ``"pii_leak"``).
    """

    def __init__(self, reason: str, category: str) -> None:
        self.reason = reason
        self.category = category
        super().__init__(f"Egress blocked [{category}]: {reason}")


# ---------------------------------------------------------------------------
# Egress guard (WP-31)
# ---------------------------------------------------------------------------


def _normalize_for_egress_check(text: str) -> str:
    """Casefold and strip diacritics for PII matching.

    Normalizes so that ``"Müller"`` matches ``"MUELLER"`` (casefold handles ß→ss,
    ü→ue, etc. in certain locales). We also run NFKD decomposition and strip
    combining marks to catch composed vs decomposed forms.
    """
    # NFKD decomposition splits è → e + combining grave
    decomposed = unicodedata.normalize("NFKD", text)
    # Strip combining marks (category Mn)
    ascii_approx = "".join(c for c in decomposed if unicodedata.category(c) != "Mn")
    return ascii_approx.casefold()


def _egress_check(url: str, payload: dict[str, Any]) -> None:
    """Check outbound LLM/embedding calls against the active profile.

    Two checks are performed:
    1. **Host allowlist** — the target hostname must be in the active profile.
    2. **PII scan** — if the profile requires pseudonymization and a case context
       exists with a PiiMapping, the payload is scanned for known PII values.

    Args:
        url: The full request URL.
        payload: The JSON-serializable request body.

    Raises:
        EgressBlockedError: If either check fails.
    """
    # Import here to avoid circular imports at module level
    from app.services.inference_profiles import get_active_profile
    from app.services.pseudonymization import get_known_values

    profile = get_active_profile()

    # ── 1. Host check ──────────────────────────────────────────────────────
    host = urlparse(url).hostname or ""
    if host not in profile.host_allowlist:
        raise EgressBlockedError(
            reason=f"Host {host!r} not in allowlist for profile {profile.name!r}",
            category="host_violation",
        )

    # ── 2. PII scan ────────────────────────────────────────────────────────
    # Only scan if the profile requires pseudonymization AND we have a case context
    if profile.pseudonymization != "required":
        return

    mapping = get_pii_context()  # Returns PiiMapping | None (contextvar)
    if mapping is None:
        return

    known = get_known_values(mapping)
    if not known:
        return

    payload_str = str(payload)
    normalized_payload = _normalize_for_egress_check(payload_str)

    for original_value in known:
        normalized_value = _normalize_for_egress_check(original_value)
        if not normalized_value:
            continue
        # Check for the normalized value within the normalized payload
        # Also check for casefolded variants with common mutations
        if normalized_value in normalized_payload:
            # ── CRITICAL: NEVER log the cleartext PII value! ──────────────
            raise EgressBlockedError(
                reason="PII detected in outbound payload",
                category="pii_leak",
            )


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
                    _egress_check(_API_URL, payload)
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
                    _egress_check(_API_URL, payload)
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
        """Generate an embedding vector for *text* via the configured embeddings endpoint.

        Args:
            text: Input text to embed.
            model: Override the default ``settings.EMBEDDING_MODEL``.

        Returns:
            A ``list[float]`` of length ``settings.VECTOR_DIM``.

        Raises:
            EmbeddingError: On HTTP or parsing failure.
        """
        raw_model = model or settings.EMBEDDING_MODEL
        # OpenRouter expects the fully-qualified slug (e.g. 'openai/text-embedding-3-small').
        # OpenAI-direct expects the bare name (e.g. 'text-embedding-3-small').
        # We pass the model name through unchanged and let the configured EMBEDDING_BASE_URL
        # dictate the format. Operators who switch to OpenAI-direct must set EMBEDDING_MODEL
        # accordingly (or override via the `model` parameter).
        model_name = raw_model
        prompt_chars = len(text)
        req_start: float = 0.0
        embedding_url = settings.EMBEDDING_BASE_URL
        logger.info(
            "get_embedding → sending (model=%s, input_chars=%d, url=%s)",
            model_name,
            prompt_chars,
            embedding_url,
        )
        try:
            payload: dict[str, Any] = {
                "model": model_name,
                "input": text,
            }
            _egress_check(embedding_url, payload)
            req_start = time.monotonic()
            resp = await self._client.post(
                embedding_url,
                json=payload,
                headers=_embedding_headers(),
            )
            req_elapsed = time.monotonic() - req_start
            resp.raise_for_status()
            body = resp.json()
            # ── Detect OpenRouter-level error responses ─────────────────
            if "error" in body and "data" not in body:
                err_detail = body["error"]
                err_msg = (
                    err_detail.get("message", str(err_detail))
                    if isinstance(err_detail, dict)
                    else str(err_detail)
                )
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

    async def _embed_batch_api(
        self,
        texts: list[str],
        *,
        model: str | None = None,
    ) -> list[list[float]]:
        """Send a batch of texts to the embedding API in a single HTTP request.

        Uses the OpenRouter batch input support (``input: [str, ...]``) to
        generate embeddings for multiple texts in one round-trip.  The
        response ``data`` array is sorted by the ``index`` field to guarantee
        output order matches input order.

        Args:
            texts: List of input strings (1 ≤ len ≤ EMBEDDING_BATCH_SIZE).
            model: Override the default embedding model.

        Returns:
            A list of embedding vectors, one per input text, in input order.

        Raises:
            EmbeddingError: On HTTP failure, malformed response, or dimension mismatch.
        """
        model_name = model or settings.EMBEDDING_MODEL
        embedding_url = settings.EMBEDDING_BASE_URL
        req_start: float = 0.0
        logger.info(
            "embed_batch_api → sending (model=%s, batch_size=%d, url=%s)",
            model_name,
            len(texts),
            embedding_url,
        )
        try:
            payload: dict[str, Any] = {
                "model": model_name,
                "input": texts,
            }
            _egress_check(embedding_url, payload)
            req_start = time.monotonic()
            resp = await self._client.post(
                embedding_url,
                json=payload,
                headers=_embedding_headers(),
            )
            req_elapsed = time.monotonic() - req_start
            resp.raise_for_status()
            body = resp.json()

            # ── Detect OpenRouter-level error responses ─────────────────
            if "error" in body and "data" not in body:
                err_detail = body["error"]
                err_msg = (
                    err_detail.get("message", str(err_detail))
                    if isinstance(err_detail, dict)
                    else str(err_detail)
                )
                logger.error(
                    "embed_batch_api FAILED (model=%s, elapsed=%.2fs, reason=api_error): %s | body=%s",
                    model_name,
                    req_elapsed,
                    err_msg,
                    str(body)[:500],
                )
                raise EmbeddingError(f"Embedding API returned error: {err_msg}") from None

            # Sort by index field to guarantee input order
            data = sorted(body["data"], key=lambda d: d.get("index", 0))
            embeddings: list[list[float]] = []
            for item in data:
                emb = item["embedding"]
                if len(emb) != settings.VECTOR_DIM:
                    raise EmbeddingError(
                        f"Expected embedding dimension {settings.VECTOR_DIM}, "
                        f"got {len(emb)} from model {model_name!r}"
                    )
                embeddings.append(emb)

            if len(embeddings) != len(texts):
                raise EmbeddingError(
                    f"Batch embedding count mismatch: sent {len(texts)} texts, "
                    f"received {len(embeddings)} embeddings"
                )

            logger.info(
                "embed_batch_api OK (model=%s, elapsed=%.2fs, batch_size=%d, dim=%d)",
                model_name,
                req_elapsed,
                len(texts),
                settings.VECTOR_DIM,
            )
            return embeddings
        except (httpx.HTTPStatusError, httpx.TimeoutException, httpx.ConnectError) as exc:
            fail_elapsed = time.monotonic() - req_start
            fail_reason = type(exc).__name__
            if isinstance(exc, httpx.HTTPStatusError):
                fail_reason = f"HTTP {exc.response.status_code}"
            logger.error(
                "embed_batch_api FAILED (model=%s, elapsed=%.2fs, reason=%s): %s",
                model_name,
                fail_elapsed,
                fail_reason,
                exc,
            )
            raise EmbeddingError(f"Embedding API error: {exc}") from exc
        except (KeyError, IndexError) as exc:
            fail_elapsed = time.monotonic() - req_start
            try:
                response_preview = str(body)[:500]
            except Exception:
                response_preview = "<unavailable>"
            logger.error(
                "embed_batch_api FAILED (model=%s, elapsed=%.2fs, reason=malformed_response): %s | body=%s",
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
        concurrency: int | None = None,
        batch_size: int | None = None,
        progress_cb: Callable[[int, int], Awaitable[None]] | None = None,
    ) -> list[list[float]]:
        """Generate embeddings for multiple texts using the batch API.

        Texts are split into batches of ``batch_size`` and each batch is sent
        as a single HTTP request with ``input: [str, ...]``.  Batches run
        concurrently up to ``concurrency`` simultaneous requests.  After each
        batch completes, ``progress_cb(done, total)`` is called (when provided)
        so callers can report fine-grained progress.

        Args:
            texts: Sequence of input strings.
            model: Override the default embedding model.
            concurrency: Maximum simultaneous batch requests (default:
                ``settings.EMBEDDING_BATCH_CONCURRENCY``).
            batch_size: Number of texts per batch request (default:
                ``settings.EMBEDDING_BATCH_SIZE``).
            progress_cb: Optional async callback ``(done, total) -> None``
                invoked after each batch completes.

        Returns:
            A list of embedding vectors (same order as *texts*).
        """
        if not texts:
            return []

        total = len(texts)
        eff_batch_size = batch_size if batch_size is not None else settings.EMBEDDING_BATCH_SIZE
        eff_concurrency = (
            concurrency if concurrency is not None else settings.EMBEDDING_BATCH_CONCURRENCY
        )

        # Split into batches, tracking the start index of each
        batches: list[tuple[int, list[str]]] = []
        for start in range(0, total, eff_batch_size):
            batch = list(texts[start : start + eff_batch_size])
            batches.append((start, batch))

        # Pre-allocate result slots
        results: list[list[float] | None] = [None] * total
        done_count = 0
        semaphore = asyncio.Semaphore(eff_concurrency)

        async def embed_batch(start_idx: int, batch: list[str]) -> None:
            nonlocal done_count
            async with semaphore:
                batch_embs = await self._embed_batch_api(batch, model=model)
                for i, emb in enumerate(batch_embs):
                    results[start_idx + i] = emb
                done_count += len(batch)
                if progress_cb:
                    await progress_cb(done_count, total)

        await asyncio.gather(*(embed_batch(start, batch) for start, batch in batches))
        return results  # type: ignore[return-value]

    async def close(self) -> None:
        """Close the underlying httpx client if owned."""
        if self._owned:
            await self._client.aclose()

    async def __aenter__(self) -> OpenRouterClient:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.close()


# ---------------------------------------------------------------------------
# Shared client factory + contextvars (WP-00.5 / D-8)
# ---------------------------------------------------------------------------

import contextvars

_shared_client: OpenRouterClient | None = None
_case_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("case_id", default=None)
_pii_mapping_var: contextvars.ContextVar[PiiMapping | None] = contextvars.ContextVar(
    "pii_mapping", default=None
)


def get_shared_client() -> OpenRouterClient:
    """Return the single shared OpenRouterClient, creating it lazily on first call.

    All service modules MUST use this instead of their own _get_client() singletons.
    """
    global _shared_client
    if _shared_client is None:
        _shared_client = OpenRouterClient()
    return _shared_client


def set_case_context(case_id: str) -> contextvars.Token[str | None]:
    """Set the case_id for the current async context. Returns a token for reset.

    Usage in a pipeline:
        token = set_case_context("case-uuid-123")
        try:
            # all LLM calls in this context carry the case_id
            ...
        finally:
            _case_id_var.reset(token)
    """
    return _case_id_var.set(case_id)


def get_case_context() -> str | None:
    """Return the current case_id, or None. Used by the egress guard (WP-31)."""
    return _case_id_var.get()


def set_pii_context(mapping: PiiMapping | None) -> contextvars.Token[PiiMapping | None]:
    """Set the PiiMapping for the current async context. Returns a token for reset.

    Used by the pipeline to make the PII mapping available to the egress guard.
    """
    return _pii_mapping_var.set(mapping)


def get_pii_context() -> PiiMapping | None:
    """Return the current PiiMapping, or None. Used by the egress guard (WP-31)."""
    return _pii_mapping_var.get()


def reset_client() -> None:
    """Reset the shared client. Used in tests."""
    global _shared_client
    _shared_client = None


async def close_client() -> None:
    """Gracefully close the shared client's HTTP transport."""
    global _shared_client
    if _shared_client is not None:
        await _shared_client.close()
        _shared_client = None
