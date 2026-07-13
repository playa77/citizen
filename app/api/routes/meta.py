"""Meta endpoints — server metadata, versioning, and disclaimer management.

Provides:
    GET /api/v1/meta/disclaimer/version — current disclaimer version
    GET /api/v1/meta/disclaimer/text — full disclaimer text
    GET /api/v1/meta/version — API version info
    GET /api/v1/meta/legal-timestamp — parameter & corpus freshness dates
    GET /api/v1/meta/active-profile — active inference profile info (WP-31)
"""

# Semantic Version: 0.2.0

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from sqlalchemy import func as sa_func
from sqlalchemy import select

from app.core.config import _get_settings, get_app_version, get_app_version_tag
from app.db.models import LegalParameter, LegalSource
from app.db.session import get_async_session

router = APIRouter()

# Disclaimer text (German) — loaded from config; version inserted at runtime

_DISCLAIMER_TEXT = f"""
<h3>Rechtlicher Hinweis und Haftungsausschluss</h3>

<p>Dieses Tool dient ausschließlich zu Informationszwecken und ersetzt keine rechtliche Beratung.
Die bereitgestellten Informationen basieren auf einer automatisierten Analyse von Dokumenten
und Gesetzestexten und können fehlerhaft, unvollständig oder veraltet sein.</p>

<h3>Nutzungsbedingungen:</h3>
<ol>
<li>Dieses Tool darf nicht als einzige Rechtsquelle verwendet werden.</li>
<li>Die Ergebnisse stellen keine rechtliche Beratung dar und begründen kein Mandatsverhältnis.</li>
<li>Für Entscheidungen auf Basis der Tool-Ausgaben wird keine Haftung übernommen.</li>
<li>Nutzer sollten stets einen zugelassenen Rechtsanwalt oder eine anerkannte
    Beratungsstelle (z.B. Arbeitsagentur, Sozialamt) konsultieren.</li>
<li>Die Nutzung erfolgt auf eigene Verantwortung.</li>
</ol>

<h3>Datenschutz:</h3>
<ul>
<li>Hochgeladene Dokumente werden temporär verarbeitet und nicht dauerhaft gespeichert.</li>
<li>IP-Adressen werden anonymisiert protokolliert.</li>
<li>Es werden keine personenbezogenen Daten an Dritte weitergegeben.</li>
</ul>

<p><strong>Version:</strong> {get_app_version_tag()}</p>
""".strip()


@router.get("/meta/disclaimer/version")
async def get_disclaimer_version() -> dict[str, str]:
    """Return the current disclaimer version."""
    settings = _get_settings()
    return {"version": settings.DISCLAIMER_VERSION}


@router.get("/meta/disclaimer/text")
async def get_disclaimer_text() -> dict[str, str]:
    """Return the full disclaimer text (German)."""
    return {"text": _DISCLAIMER_TEXT, "version": _get_settings().DISCLAIMER_VERSION}


@router.get("/meta/version")
async def get_api_version() -> dict[str, str]:
    """Return API version information."""
    settings = _get_settings()
    return {
        "api_version": get_app_version(),
        "disclaimer_version": settings.DISCLAIMER_VERSION,
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
