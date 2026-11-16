"""Dev-instance response headers middleware (WP-62).

Adds ``X-Robots-Tag: noindex, nofollow`` to every response while the
instance runs in ``DEPLOYMENT_MODE=dev`` so search engines do not index the
internet-reachable development instance.
"""

# Semantic Version: 1.0.0 | 2026-08-07 — WP-62

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import _get_settings


class DevNoIndexMiddleware(BaseHTTPMiddleware):
    """Middleware that applies noindex headers on dev instances."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        response = await call_next(request)
        if _get_settings().DEPLOYMENT_MODE == "dev":
            response.headers["X-Robots-Tag"] = "noindex, nofollow"
        return response
