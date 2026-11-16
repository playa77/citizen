"""Composite preset endpoints.

Endpoints:
    GET  /api/v1/presets              List all presets
    GET  /api/v1/presets/{id}         Get one preset
    POST /api/v1/presets/suggest      LLM-suggested composite for a case
    POST /api/v1/presets/apply        Apply a preset (returns IntakeResult-shaped dict)

WP-93: the preset catalog, the keyword fallback table and the fallback
preset are module data (``modules/<id>/intake.yaml``) assembled by
``app.modules.areas``; the catch-all area replaces the hard-coded literal.

WP-95: ``suggest`` and ``apply`` responses carry ``resolved_modules`` (one
entry per area key of the suggestion / preset, primary first) so a client
can see the owning module, legacy-alias mapping and enablement before it
calls ``/analyze``.
"""

# Semantic Version: 0.6.0 | 2026-11-16 — prompt set 3.0.0: P-10 rewritten with a
# "no match" path (F-16); tolerant JSON parsing and an additive "match" field
# ("llm" | "keyword_fallback") on /presets/suggest (CR-11).
# 0.5.0 | 2026-11-16 — WP-95: resolved_modules on suggest/apply
# (additive key).
# 0.4.0

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Body, HTTPException, status

from app.core.router import OpenRouterClient
from app.modules.areas import area_tables
from app.modules.runtime import resolved_modules
from app.services.presets import get_preset, list_presets
from app.services.prompts import (
    JSON_OBJECT_ONLY,
    STRICT_SUFFIX,
    stage_max_tokens,
    stage_temperature,
)
from app.services.reasoning import JSONParseError, _parse_json_response

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Always-LLM-suggest with keyword fallback
# ---------------------------------------------------------------------------


def _render_suggest_system() -> str:
    """P-10 (prompt set 3.0.0): catalogue and areas from module data.

    Has an explicit "no match" answer (``preset_id: ""``) instead of forcing a
    pick (F-16); the route then falls back to keyword matching and reports
    ``match: "keyword_fallback"`` (CR-11).
    """
    tables = area_tables()
    return (
        "<rolle>\n"
        "Du ordnest die Fallschilderung einer Person einer Fallvorlage zu. Du berätst nicht "
        "rechtlich.\n"
        "</rolle>\n\n"
        "<katalog>\n"
        + "\n".join(f"- {p['id']}: {p['name']} — {p['description']}" for p in list_presets())
        + "\n</katalog>\n\n"
        "<regeln>\n"
        "- preset_id: die id der Vorlage, deren Beschreibung den Gegenstand der Schilderung "
        'trifft; einzelne Stichwörter genügen nicht. Passt keine: "".\n'
        "- primary_area: genau einer dieser Werte: "
        + ", ".join(tables.keys)
        + f'. Unklar: "{tables.catch_all}".\n'
        "- secondary_areas: weitere Werte aus derselben Liste, ohne primary_area.\n"
        "</regeln>\n\n"
        "<ausgabeformat>\n"
        f'{{ "preset_id": "{tables.fallback_preset}", "primary_area": "{tables.default_module}", '
        '"secondary_areas": [] }\n\n' + JSON_OBJECT_ONLY + "\n</ausgabeformat>"
    )


_SUGGEST_SYSTEM = _render_suggest_system()

# (preset_id, primary_area, keywords) — module data; the default module's
# entries come last so it wins ties only as the initial fallback.
_KEYWORD_FALLBACK: list[tuple[str, str, tuple[str, ...]]] = [
    (fb.preset_id, fb.primary_area, fb.keywords) for fb in area_tables().preset_fallback
]


def _fallback_suggestion() -> tuple[str, str]:
    tables = area_tables()
    preset = get_preset(tables.fallback_preset)
    primary = preset["legal_areas"][0] if preset and preset["legal_areas"] else tables.catch_all
    return tables.fallback_preset, primary


def _keyword_suggest(text: str) -> dict[str, Any]:
    haystack = (text or "").lower()
    best = _fallback_suggestion()
    best_score = 0
    for pid, primary, kws in _KEYWORD_FALLBACK:
        score = sum(1 for kw in kws if kw in haystack)
        if score > best_score:
            best_score = score
            best = (pid, primary)
    return {
        "preset_id": best[0],
        "primary_area": best[1],
        "secondary_areas": [],
        "match": "keyword_fallback",
    }


async def _call_llm_suggest(text: str) -> dict[str, Any]:
    """Call the LLM to suggest a preset. Always uses LLM; on failure falls
    back to keyword matching per the plan (Decision #7)."""
    client = OpenRouterClient()
    try:
        raw = await client.chat_completion(
            [
                {"role": "system", "content": _SUGGEST_SYSTEM + STRICT_SUFFIX},
                {"role": "user", "content": text[:4000]},
            ],
            temperature=stage_temperature("preset_suggest"),
            max_tokens=stage_max_tokens("preset_suggest"),
            max_retries=1,
        )
    except Exception as exc:
        logger.warning("LLM suggest failed (%s); using keyword fallback", exc)
        return _keyword_suggest(text)
    finally:
        await client.close()

    # Parse JSON — tolerant of fences/prose (CR-11; a fenced answer used to
    # drop silently into the keyword fallback).
    try:
        parsed = _parse_json_response(raw, context="preset suggestion")
    except JSONParseError:
        return _keyword_suggest(text)
    if not isinstance(parsed, dict):
        return _keyword_suggest(text)

    preset_id = str(parsed.get("preset_id") or "").strip()
    if not get_preset(preset_id):
        return _keyword_suggest(text)
    tables = area_tables()
    primary = str(parsed.get("primary_area") or tables.catch_all).strip()
    if primary not in tables.keys:
        primary = tables.catch_all
    secs = parsed.get("secondary_areas") or []
    secs_clean = [s for s in secs if s in tables.keys and s != primary]
    return {
        "preset_id": preset_id,
        "primary_area": primary,
        "secondary_areas": secs_clean,
        "match": "llm",
    }


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
    suggestion = await _call_llm_suggest(text)
    keys = [suggestion["primary_area"], *suggestion["secondary_areas"]]
    return {**suggestion, "resolved_modules": resolved_modules(keys)}


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
    legal_areas = list(preset["legal_areas"])
    primary_area = legal_areas[0] if legal_areas else area_tables().catch_all
    return {
        "preset_id": preset_id,
        "preset_name": preset["name"],
        "legal_areas": legal_areas,
        "primary_area": primary_area,
        "enriched_text": initial_text,  # callers can post-process as needed
        "resolved_modules": resolved_modules(legal_areas or [primary_area]),
    }
