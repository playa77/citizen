"""Meta endpoints — server metadata, versioning, and disclaimer management.

Provides:
    GET /api/v1/meta/disclaimer/version — current disclaimer version
    GET /api/v1/meta/disclaimer/text — full disclaimer text
    GET /api/v1/meta/version — API version info
"""

# Semantic Version: 0.1.0

from __future__ import annotations

from fastapi import APIRouter

from app.core.config import _get_settings, get_app_version, get_app_version_tag

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
