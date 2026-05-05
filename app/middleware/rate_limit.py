"""In-memory rate limiting middleware for the local FastAPI application.

Implements a simple token-bucket-style limiter per client IP that
guards against runaway or bug-induced request floods.
"""

# Semantic Version: 0.1.0

from __future__ import annotations

import logging
import time
from collections import defaultdict
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

from app.core.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# in-memory window store  (lives for process lifetime; fine for single-user v1)
# ---------------------------------------------------------------------------
WindowStore: defaultdict[str, list[float]] = defaultdict(list)


def _prune_old_entries(client_id: str, window_sec: float) -> None:
    """Remove timestamps outside the current sliding window."""
    cutoff = time.monotonic() - window_sec
    WindowStore[client_id] = [t for t in WindowStore[client_id] if t > cutoff]


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate-limit middleware that enforces a sliding-window request cap.

    Rate limiting values are read from *settings* at construction time and are
    held for the lifetime of the middleware instance.
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)
        self._max_requests = settings.RATE_LIMIT_REQUESTS
        self._window_sec = settings.RATE_LIMIT_WINDOW
        logger.info(
            "RateLimitMiddleware initialised: %s requests / %s s",
            self._max_requests,
            self._window_sec,
        )

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if not self._max_requests or not self._window_sec:
            # Rate limiting disabled (e.g. both set to 0).
            return await call_next(request)

        client_id: str = request.client.host if request.client else "unknown"

        _prune_old_entries(client_id, self._window_sec)

        if len(WindowStore[client_id]) >= self._max_requests:
            logger.warning(
                "Rate limit exceeded for client %s (%d req / %d s)",
                client_id,
                self._max_requests,
                self._window_sec,
            )
            return JSONResponse(
                status_code=429,
                content={
                    "error": "rate_limit_exceeded",
                    "detail": (
                        f"Too many requests. Limit: {self._max_requests} requests "
                        f"per {self._window_sec} seconds."
                    ),
                },
            )

        WindowStore[client_id].append(time.monotonic())
        return await call_next(request)
