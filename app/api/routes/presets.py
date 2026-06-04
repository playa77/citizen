"""Composite preset endpoints.

Endpoints:
    GET  /api/v1/presets              List all presets
    GET  /api/v1/presets/{id}         Get one preset
    POST /api/v1/presets/suggest      LLM-suggested composite for a case
    POST /api/v1/presets/apply        Apply a preset (returns IntakeResult-shaped dict)
"""

# Semantic Version: 0.3.0

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, Body, HTTPException, status

from app.core.router import OpenRouterClient
from app.db.models import LEGAL_AREA_ALLOWED
from app.services.presets import get_preset, list_presets

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Always-LLM-suggest with keyword fallback
# ---------------------------------------------------------------------------

_SUGGEST_SYSTEM = (
    "Du bist ein juristischer Erstberater. Dir wird die Schilderung "
    "eines Bürgers vorgelegt. Wähle EINE ID aus dem folgenden Katalog "
    "von Fall-Presets, die am besten passt:\n\n"
    + "\n".join(f"- {p['id']}: {p['name']} — {p['description']}" for p in list_presets())
    + "\n\nZugelassene Rechtsgebiete: "
    + ", ".join(LEGAL_AREA_ALLOWED)
    + "\n\nAntworte GENAU mit einem JSON-Objekt: {\"preset_id\": \"<id>\", "
    "\"primary_area\": \"<legal_area>\", \"secondary_areas\": [\"<legal_area>\", ...]}.\n"
    "Gib ausschließlich gültiges JSON zurück."
)

_KEYWORD_FALLBACK: list[tuple[str, str, tuple[str, ...]]] = [
    # (preset_id, primary_area, keywords)
    ("erbe-mit-testament", "erbrecht", ("testament", "erbschein", "erblasser", "erbfolge")),
    ("erbe-mit-familie", "erbrecht", ("geschieden", "scheidung", "zugewinn", "ex-mann", "ex-frau")),
    ("schenkung-zu-lebzeiten", "schenkungsrecht", ("schenkung", "schenken", "verschenk")),
    ("hofesuebergabe", "erbrecht", ("hof", "landwirtschaft", "höfeordnung")),
    ("sozialrecht-allgemein", "sozialrecht", ("jobcenter", "bürgergeld", "sanktion", "sozialamt", "sgb")),
]


def _keyword_suggest(text: str) -> dict[str, str]:
    haystack = (text or "").lower()
    best = ("sozialrecht-allgemein", "sozialrecht")
    best_score = 0
    for pid, primary, kws in _KEYWORD_FALLBACK:
        score = sum(1 for kw in kws if kw in haystack)
        if score > best_score:
            best_score = score
            best = (pid, primary)
    return {"preset_id": best[0], "primary_area": best[1], "secondary_areas": []}


async def _call_llm_suggest(text: str) -> dict[str, str]:
    """Call the LLM to suggest a preset. Always uses LLM; on failure falls
    back to keyword matching per the plan (Decision #7)."""
    client = OpenRouterClient()
    try:
        raw = await client.chat_completion(
            [
                {"role": "system", "content": _SUGGEST_SYSTEM},
                {"role": "user", "content": text[:4000]},
            ],
            temperature=0.1,
            max_retries=1,
        )
    except Exception as exc:
        logger.warning("LLM suggest failed (%s); using keyword fallback", exc)
        return _keyword_suggest(text)
    finally:
        await client.close()

    # Parse JSON.
    try:
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            return _keyword_suggest(text)
    except (json.JSONDecodeError, ValueError):
        return _keyword_suggest(text)

    preset_id = str(parsed.get("preset_id") or "").strip()
    if not get_preset(preset_id):
        return _keyword_suggest(text)
    primary = str(parsed.get("primary_area") or "andere").strip()
    if primary not in LEGAL_AREA_ALLOWED:
        primary = "andere"
    secs = parsed.get("secondary_areas") or []
    secs_clean = [s for s in secs if s in LEGAL_AREA_ALLOWED and s != primary]
    return {"preset_id": preset_id, "primary_area": primary, "secondary_areas": secs_clean}


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/presets")
async def get_presets() -> list[dict[str, Any]]:
    """List all available case-type presets."""
    return list_presets()


@router.get("/presets/{preset_id}")
async def get_preset_endpoint(preset_id: str) -> dict[str, Any]:
    """Return a single preset by id, or 404 if unknown."""
    preset = get_preset(preset_id)
    if preset is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Preset '{preset_id}' not found.",
        )
    return preset


@router.post("/presets/suggest")
async def post_suggest_preset(
    payload: dict[str, Any] = Body(...),  # noqa: B008
) -> dict[str, Any]:
    """Suggest a preset for the given case text.

    Body: ``{"text": "<case description>"}``
    """
    text = str(payload.get("text") or "").strip()
    if not text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="'text' must be non-empty.",
        )
    return await _call_llm_suggest(text)


@router.post("/presets/apply")
async def post_apply_preset(
    payload: dict[str, Any] = Body(...),  # noqa: B008
) -> dict[str, Any]:
    """Apply a preset — return a ready-to-use composite suggestion.

    Body: ``{"preset_id": "...", "session_id": "...", "initial_text": "..."}``

    Returns a dict with the preset's legal_areas and a ``text`` enrichment
    suitable for the pipeline input.
    """
    preset_id = str(payload.get("preset_id") or "").strip()
    initial_text = str(payload.get("initial_text") or "").strip()
    if not preset_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="'preset_id' is required.",
        )
    preset = get_preset(preset_id)
    if preset is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Preset '{preset_id}' not found.",
        )
    return {
        "preset_id": preset_id,
        "preset_name": preset["name"],
        "legal_areas": list(preset["legal_areas"]),
        "primary_area": preset["legal_areas"][0] if preset["legal_areas"] else "andere",
        "enriched_text": initial_text,  # callers can post-process as needed
    }
