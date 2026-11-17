"""Meta endpoints — server metadata, versioning, and disclaimer management.

Provides:
    GET /api/v1/meta/disclaimer/version — current disclaimer version
    GET /api/v1/meta/disclaimer/text — full disclaimer text
    GET /api/v1/meta/disclosure — Art. 50(1) AI-system notification (D-032)
    GET /api/v1/meta/version — API version info (incl. disclosure_version)
    GET /api/v1/meta/legal-timestamp — parameter & corpus freshness dates
    GET /api/v1/meta/active-profile — active inference profile info (WP-31)
    GET /api/v1/meta/deployment-mode — active deployment posture (WP-62/WP-66)
"""

# Semantic Version: 0.6.0 | 2026-11-17 — WP-125: /meta/disclaimer/text rendered from
# the pinned plain-language core copy (the old text misstated storage).
# 0.5.0 | 2026-11-16 — WP-95: /meta/version carries
# `modules: {id: version}` of the enabled modules (additive key).
# 0.4.0 | 2026-08-25 — Art. 50 disclosure endpoint (D-032):
# /meta/disclosure added (ack-guarded via route-level dependency), /meta/version
# carries disclosure_version.

from __future__ import annotations

from html import escape
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import func as sa_func
from sqlalchemy import select

from app.core.config import _get_settings, get_app_version
from app.db.models import LegalParameter, LegalSource
from app.db.session import get_async_session
from app.modules.runtime import module_registry
from app.plain.core_copy import CoreCopyError, load_core_copy
from app.services.disclosure import (
    DISCLOSURE_VERSION,
    DisclosureInfo,
    build_disclosure,
)

router = APIRouter()

# Disclaimer text (German). Since core 3.4.0 (WP-125, D-068) it is rendered
# from the plain-language core copy pinned to the running disclaimer version
# (app/plain/core/de.yaml). The former hard-coded text claimed that uploads
# are "nicht dauerhaft gespeichert" — false since cases persist in Postgres —
# and named authorities as advice centres; it was never versioned with the
# disclaimer. Shape unchanged: {"text": <HTML>, "version": <disclaimer version>}.


def _disclaimer_html(disclaimer_version: str) -> str:
    try:
        doc = load_core_copy(
            "de", disclaimer_version=disclaimer_version, disclosure_version=DISCLOSURE_VERSION
        )
    except CoreCopyError:
        # Stale pin: point to the authoritative documents rather than show a
        # summary of another disclaimer version.
        return (
            "<h3>Rechtlicher Hinweis</h3>"
            "<p>Citizen ist keine Rechtsberatung. Maßgeblich ist der vollständige "
            f"rechtliche Hinweis in DISCLAIMER_DE.md (Fassung {escape(disclaimer_version)}).</p>"
        )
    d = doc["disclaimer"]
    privacy = doc["privacy"]
    items = "".join(f"<li>{escape(str(point))}</li>" for point in d["points"])
    return (
        "<h2>Rechtlicher Hinweis (Kurzfassung)</h2>"
        f"<h3>{escape(str(d['title']))}</h3><ul>{items}</ul>"
        f"<h3>{escape(str(privacy['title']))}</h3>"
        f"<p>{escape(str(privacy['storage']))} {escape(str(privacy['deletion']))}</p>"
        f"<p>{escape(str(d['full_text_note']))}</p>"
        f"<p><strong>Version:</strong> {escape(disclaimer_version)}</p>"
    )


@router.get("/meta/disclaimer/version")
async def get_disclaimer_version() -> dict[str, str]:
    """Return the current disclaimer version."""
    settings = _get_settings()
    return {"version": settings.DISCLAIMER_VERSION}


@router.get("/meta/disclaimer/text")
async def get_disclaimer_text() -> dict[str, str]:
    """Return the disclaimer summary as HTML (German); plain JSON: /meta/disclaimer/plain."""
    version = str(_get_settings().DISCLAIMER_VERSION)
    return {"text": _disclaimer_html(version), "version": version}


async def require_disclaimer_ack(
    x_disclaimer_ack: Annotated[str | None, Header()] = None,
) -> None:
    """Route-level ``X-Disclaimer-Ack`` enforcement for /meta/disclosure.

    The DisclaimerMiddleware excludes the whole ``/api/v1/meta`` prefix, so a
    middleware-based guard would require editing the disclaimer system — out
    of scope for D-032. This dependency mirrors the middleware's error
    contract (403 with ``error``/``required_version``) for this one endpoint;
    existing meta endpoints keep their current (unprotected) contract.
    """
    settings = _get_settings()
    if x_disclaimer_ack is None:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "disclaimer_required",
                "message": "Legal disclaimer must be acknowledged before using this API.",
                "required_version": settings.DISCLAIMER_VERSION,
            },
        )
    if x_disclaimer_ack != settings.DISCLAIMER_VERSION:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "disclaimer_version_mismatch",
                "message": "Disclaimer version has been updated. Please re-acknowledge.",
                "required_version": settings.DISCLAIMER_VERSION,
                "acknowledged_version": x_disclaimer_ack,
            },
        )


@router.get(
    "/meta/disclosure",
    response_model=DisclosureInfo,
    dependencies=[Depends(require_disclaimer_ack)],
)
async def get_disclosure() -> DisclosureInfo:
    """Return the canonical Art. 50(1) AI-system notification (D-032).

    This is the reference endpoint for consuming clients that want to cache or
    pre-fetch the current disclosure text. It does NOT vary by deployment
    mode: the client may need the text in any mode to inform the natural
    person before presenting AI-generated results.
    """
    return build_disclosure()


@router.get("/meta/version")
async def get_api_version() -> dict[str, Any]:
    """Return API version information.

    ``modules`` maps every *enabled* module id to its version (WP-95) — the
    module set a request can run with in this deployment.
    """
    settings = _get_settings()
    registry = module_registry()
    return {
        "api_version": get_app_version(),
        "disclaimer_version": settings.DISCLAIMER_VERSION,
        # Art. 50(1) disclosure text version (D-032) — distinct from both the
        # API version and the disclaimer version.
        "disclosure_version": DISCLOSURE_VERSION,
        "modules": {
            module_id: registry.modules[module_id].version for module_id in sorted(registry.enabled)
        },
    }


@router.get("/meta/legal-timestamp")
async def get_legal_timestamp() -> dict[str, Any]:
    """Return the freshness dates for legal parameters and corpus sources.

    Returns ``parameter_freshness`` — the latest ``valid_to`` across all
    ``legal_parameter`` rows, and ``corpus_freshness`` — the latest
    ``updated_at`` across all ``legal_source`` rows.

    If no data exists yet, the corresponding field is ``None``.
    """
    parameter_freshness_str: str | None = None
    corpus_freshness_str: str | None = None

    async for session in get_async_session():
        # Latest parameter valid_to (latest effective end date)
        param_result = await session.execute(select(sa_func.max(LegalParameter.valid_to)))
        pf = param_result.scalar()
        if pf is not None:
            parameter_freshness_str = pf.isoformat()

        # Latest source updated_at
        source_result = await session.execute(select(sa_func.max(LegalSource.updated_at)))
        sf = source_result.scalar()
        if sf is not None:
            # sf is a datetime from LegalSource.updated_at
            corpus_freshness_str = sf.isoformat()[:10]
        break  # session context manager yields once

    return {
        "parameter_freshness": parameter_freshness_str,
        "corpus_freshness": corpus_freshness_str,
    }


@router.get("/meta/active-profile")
async def get_active_profile_info() -> dict[str, str]:
    """Return the active inference profile information (WP-31).

    Returns the profile name, label, AVV status, and pseudonymization setting
    for display in the frontend UI.
    """
    from app.services.inference_profiles import get_active_profile

    profile = get_active_profile()
    return {
        "profile": profile.name,
        "label": profile.label,
        "avv_status": profile.avv_status,
        "pseudonymization": profile.pseudonymization,
    }


@router.get("/meta/deployment-mode")
async def get_deployment_mode() -> dict[str, Any]:
    """Return the active deployment posture (WP-62/WP-66, D-019).

    Exposes the raw ``DEPLOYMENT_MODE`` value, the dev synthetic-data-only
    flag, and the persistent dev-instance banner text for UI display.
    """
    s = _get_settings()
    is_dev = s.DEPLOYMENT_MODE == "dev"
    return {
        "mode": s.DEPLOYMENT_MODE,
        "synthetic_data_only": bool(s.CITIZEN_SYNTHETIC_DATA_ONLY),
        "dev": is_dev,
        "dev_banner": (
            "ENTWICKLUNGSINSTANZ — Testbetrieb mit synthetischen Daten. "
            "Keine Nutzung für reale Fälle. Ausgaben sind nicht belastbar."
        )
        if is_dev
        else None,
    }
