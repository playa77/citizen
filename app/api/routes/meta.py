"""Meta endpoints — server metadata, versioning, and disclaimer management.

Provides:
    GET /api/v1/meta/disclaimer/version — current disclaimer version
    GET /api/v1/meta/disclaimer/text — full disclaimer text
    GET /api/v1/meta/version — API version info
"""

from __future__ import annotations

from fastapi import APIRouter

from app.core.config import _get_settings

router = APIRouter()

# Disclaimer text (German) — loaded from config or hardcoded for v1.0.0
_DISCLAIMER_TEXT_V1 = """
**Rechtlicher Hinweis und Haftungsausschluss**

Dieses Tool dient ausschließlich zu Informationszwecken und ersetzt keine rechtliche Beratung.
Die bereitgestellten Informationen basieren auf einer automatisierten Analyse von Dokumenten
und Gesetzes_texten und können fehlerhaft, unvollständig oder veraltet sein.

**Nutzungsbedingungen:**
1. Dieses Tool darf nicht als唯一 Rechtsquelle verwendet werden.
2. Die Ergebnisse stellen keine rechtliche Beratung dar und begründen kein Mandatsverhältnis.
3. Für Entscheidungen auf Basis der Tool-Ausgaben wird keine Haftung übernommen.
4. Nutzer sollten stets einen zugelassenen Rechtsanwalt oder eine anerkannte
   Beratungsstelle (z.B. Arbeitsagentur, Sozialamt) konsultieren.
5. Die Nutzung erfolgt auf eigene Verantwortung.

**Datenschutz:**
- Hochgeladene Dokumente werden temporär verarbeitet und nicht dauerhaft gespeichert.
- IP-Adressen werden anonymisiert protokolliert.
- Es werden keine personenbezogenen Daten an Dritte weitergegeben.

**Version:** v1.0.0
""".strip()


@router.get("/meta/disclaimer/version")
async def get_disclaimer_version() -> dict[str, str]:
    """Return the current disclaimer version."""
    settings = _get_settings()
    return {"version": settings.DISCLAIMER_VERSION}


@router.get("/meta/disclaimer/text")
async def get_disclaimer_text() -> dict[str, str]:
    """Return the full disclaimer text (German)."""
    return {"text": _DISCLAIMER_TEXT_V1, "version": _get_settings().DISCLAIMER_VERSION}


@router.get("/meta/version")
async def get_api_version() -> dict[str, str]:
    """Return API version information."""
    settings = _get_settings()
    return {
        "api_version": "1.0.0",
        "disclaimer_version": settings.DISCLAIMER_VERSION,
    }
