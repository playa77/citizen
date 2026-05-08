"""Simple local caching service for expensive operations.

Provides JSON-based key-value caching backed by the ``cache_entry`` table.
Used to avoid redundant LLM/embedding calls during development and for
repeated user submissions.

Cache keys are deterministic SHA-256 hashes that include the model name
and input text to guarantee correctness across model changes and input
variations.
"""

# Semantic Version: 0.1.0

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import CacheEntry
from app.db.session import get_async_session

logger = logging.getLogger(__name__)


def _now_utc() -> datetime:
    """Return current UTC as a naive datetime (DB is without timezone)."""
    return datetime.now(tz=timezone.utc).replace(tzinfo=None)


def make_cache_key(namespace: str, model: str, text: str) -> str:
    """Create a deterministic SHA-256 cache key.

    Parameters
    ----------
    namespace :
        A logical grouping (e.g. "triage", "embedding", "retrieval").
    model :
        The model identifier (e.g. "openai/text-embedding-3-small").
    text :
        The input text to hash.

    Returns
    -------
    str
        A 64-character hex digest, prefixed with the namespace for easy
        inspection.
    """
    payload = f"{model}\0{text}"
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"{namespace}:{digest}"


async def get_json_cache(
    session: AsyncSession,
    key: str,
) -> Any | None:
    """Retrieve a cached value by key.

    Automatically skips entries whose *expires_at* has passed (they are
    treated as misses).

    Parameters
    ----------
    session :
        An active ``AsyncSession``.
    key :
        The cache key returned by :func:`make_cache_key`.

    Returns
    -------
    Any | None
        The deserialized JSON value, or *None* if no valid entry exists.
    """
    stmt = select(CacheEntry).where(CacheEntry.key == key)
    result = await session.execute(stmt)
    entry: CacheEntry | None = result.scalar_one_or_none()

    if entry is None:
        return None

    # Check expiry
    if entry.expires_at is not None:
        now = _now_utc()
        if entry.expires_at <= now:
            logger.debug("Cache key %s expired at %s", key, entry.expires_at)
            return None

    logger.debug("Cache HIT for key %s", key)
    return entry.value_json


async def set_json_cache(
    session: AsyncSession,
    key: str,
    value: Any,
    *,
    ttl_sec: int | None = None,
) -> None:
    """Store a value in the cache.

    Uses an upsert pattern (``INSERT ... ON CONFLICT DO UPDATE``) so that
    re-caching a key updates the existing row rather than raising a
    duplicate-key error.

    Parameters
    ----------
    session :
        An active ``AsyncSession``.
    key :
        The cache key returned by :func:`make_cache_key`.
    value :
        Any JSON-serializable Python value.
    ttl_sec :
        Time-to-live in seconds. If *None*, the entry never expires.
        Defaults to ``settings.CACHE_TTL_SEC`` when omitted.
    """
    from app.core.config import settings as s

    if ttl_sec is None and s.CACHE_TTL_SEC:
        ttl_sec = s.CACHE_TTL_SEC

    expires_at: datetime | None = None
    if ttl_sec is not None:
        expires_at = _now_utc() + _seconds_to_timedelta(ttl_sec)

    # Upsert: insert or update
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    stmt = pg_insert(CacheEntry).values(
        key=key,
        value_json=value,
        created_at=_now_utc(),
        expires_at=expires_at,
    ).on_conflict_do_update(
        index_elements=["key"],
        set_={
            "value_json": value,
            "created_at": _now_utc(),
            "expires_at": expires_at,
        },
    )
    await session.execute(stmt)
    await session.commit()
    logger.debug("Cache SET for key %s (ttl=%s)", key, ttl_sec)


def _seconds_to_timedelta(seconds: int) -> Any:
    """Convert seconds to a timedelta. Lazy import to avoid top-level import."""
    from datetime import timedelta
    return timedelta(seconds=seconds)
