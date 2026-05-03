"""Disclaimer middleware — enforces consent acceptance on all /api/* routes.

This middleware validates that incoming requests to API endpoints include the
``X-Disclaimer-Ack`` header with a value matching the current disclaimer version.
Requests without this header (or with a mismatched version) receive a 403 response
with a JSON payload describing the error.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import Settings, _get_settings

logger = logging.getLogger(__name__)

# Paths that do NOT require disclaimer acknowledgment.
EXCLUDED_PATHS = {"/health", "/docs", "/openapi.json", "/redoc"}
# Path prefixes that do NOT require disclaimer acknowledgment.
EXCLUDED_PREFIXES = ("/api/v1/meta", "/static")


def _is_excluded_path(path: str) -> bool:
    """Check if the path is excluded from disclaimer requirement."""
    if path in EXCLUDED_PATHS:
        return True
    return any(path.startswith(prefix) for prefix in EXCLUDED_PREFIXES)


def _compute_ip_hash(request: Request, salt: str) -> str:
    """Compute a hash of the client's IP address for audit logging.

    Parameters
    ----------
    request :
        The incoming request.
    salt :
        The application's secret salt.

    Returns
    -------
    str
        A short hex digest of the IP + salt combination.
    """
    # Try to get real IP (handles proxy headers)
    client_ip = request.headers.get("X-Forwarded-For", "")
    if not client_ip:
        client_ip = request.headers.get("X-Real-IP", "")
    if not client_ip and request.client:
        client_ip = request.client.host
    if not client_ip:
        client_ip = "unknown"

    # Take first IP if there are multiple (X-Forwarded-For can contain a list)
    client_ip = client_ip.split(",")[0].strip()

    combined = f"{client_ip}:{salt}"
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()[:16]


class DisclaimerMiddleware(BaseHTTPMiddleware):
    """Middleware that enforces disclaimer acceptance on API routes.

    This middleware:
    1. Skips non-API paths (health, docs, static).
    2. Checks for the presence of the ``X-Disclaimer-Ack`` header.
    3. Validates that the header value matches the current disclaimer version.
    4. On failure, returns a 403 with a JSON error payload.
    5. On success, attaches the acceptance metadata to the request state for logging.
    """

    def __init__(
        self,
        app: Any,
        settings: Settings | None = None,
    ) -> None:
        super().__init__(app)
        self._settings = settings or _get_settings()

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        # Skip excluded paths
        if _is_excluded_path(request.url.path):
            return await call_next(request)

        # Only apply to /api/* routes
        if not request.url.path.startswith("/api/"):
            return await call_next(request)

        # Check for disclaimer acknowledgment header
        ack_header = request.headers.get("X-Disclaimer-Ack")
        expected_version = self._settings.DISCLAIMER_VERSION

        if ack_header is None:
            logger.warning(
                "Disclaimer not acknowledged: missing header on %s",
                request.url.path,
            )
            return JSONResponse(
                status_code=403,
                content={
                    "error": "disclaimer_required",
                    "message": "Legal disclaimer must be acknowledged before using this API.",
                    "required_version": expected_version,
                },
            )

        if ack_header != expected_version:
            logger.warning(
                "Disclaimer version mismatch: got %s, expected %s on %s",
                ack_header,
                expected_version,
                request.url.path,
            )
            return JSONResponse(
                status_code=403,
                content={
                    "error": "disclaimer_version_mismatch",
                    "message": "Disclaimer version has been updated. Please re-acknowledge.",
                    "required_version": expected_version,
                    "acknowledged_version": ack_header,
                },
            )

        # Compute and attach acceptance metadata for downstream logging
        ip_hash = _compute_ip_hash(request, self._settings.DISCLAIMER_SALT)
        request.state.disclaimer_accepted = True
        request.state.disclaimer_version = expected_version
        request.state.disclaimer_ip_hash = ip_hash

        logger.debug(
            "Disclaimer acknowledged: version=%s, path=%s, ip_hash=%s",
            expected_version,
            request.url.path,
            ip_hash,
        )

        return await call_next(request)
