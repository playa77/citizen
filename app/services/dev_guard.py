"""Dev-instance Art. 2(8) hardening guards (WP-62).

Three guards keep an internet-reachable development instance inside the
Art. 2(8) development-phase exemption of the AI Act (VO (EU) 2024/1689):

1. Startup assertion — refuse to run when ``DEPLOYMENT_MODE=dev`` unless the
   ``CITIZEN_SYNTHETIC_DATA_ONLY`` flag is explicitly ``true``.
2. Ingest guard — reject document uploads that are not explicitly tagged as
   synthetic/goldset when the dev synthetic-data-only posture is active.
3. (Served in app/middleware/dev_headers.py + /robots.txt: noindex.)

The deployer must deliberately opt in; there is no silent default that lets a
dev instance process real documents.
"""

# Semantic Version: 1.0.0 | 2026-08-07 — WP-62

from __future__ import annotations

import logging

from fastapi import HTTPException, Request, status

from app.core.config import _get_settings

logger = logging.getLogger(__name__)

#: Allowed document tags on a synthetic-data-only dev instance.
SYNTHETIC_TAGS = {"synthetic", "goldset"}


class DevGuardError(Exception):
    """Raised when the dev synthetic-data-only posture is violated at startup."""


def is_dev_mode() -> bool:
    """Return ``True`` when the active deployment mode is ``dev``."""
    return _get_settings().DEPLOYMENT_MODE == "dev"


def synthetic_data_only() -> bool:
    """Return ``True`` when the dev synthetic-data-only flag is set."""
    return bool(_get_settings().CITIZEN_SYNTHETIC_DATA_ONLY)


def check_dev_synthetic_data_startup() -> None:
    """Assert that a dev instance is configured for synthetic data only.

    Raises
    ------
    DevGuardError
        If ``DEPLOYMENT_MODE=dev`` and ``CITIZEN_SYNTHETIC_DATA_ONLY`` is not
        truthy. The application must not start in that state.
    """
    if is_dev_mode() and not synthetic_data_only():
        raise DevGuardError(
            "DEPLOYMENT_MODE=dev requires CITIZEN_SYNTHETIC_DATA_ONLY=true. "
            "The dev instance is restricted to synthetic data only (Art. 2(8) AI Act); "
            "set CITIZEN_SYNTHETIC_DATA_ONLY=true in the environment to run it."
        )


def check_synthetic_data_request(request: Request) -> None:
    """Reject untagged document uploads on a synthetic-data-only dev instance.

    When the instance runs in ``DEPLOYMENT_MODE=dev`` AND
    ``CITIZEN_SYNTHETIC_DATA_ONLY=true``, every document-ingesting request must
    carry an ``X-Document-Tag`` header with value ``synthetic`` or ``goldset``.

    Raises
    ------
    HTTPException(403)
        If the posture is active and the tag is missing or not in
        ``SYNTHETIC_TAGS``.
    """
    if not is_dev_mode() or not synthetic_data_only():
        return

    tag = request.headers.get("X-Document-Tag", "").strip().lower()
    if tag not in SYNTHETIC_TAGS:
        logger.warning(
            "Rejecting document upload without synthetic-data tag on dev instance "
            "(path=%s, tag=%r)",
            request.url.path,
            tag,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "synthetic_data_only",
                "message": (
                    "Diese Entwicklungsinstanz verarbeitet ausschließlich synthetische "
                    "Daten. Keine Nutzung für reale Fälle. Bitte kennzeichnen Sie "
                    "Testdaten mit dem Header 'X-Document-Tag: synthetic' oder "
                    "'X-Document-Tag: goldset'."
                ),
                "mode": "dev",
                "synthetic_data_only": True,
            },
        )
