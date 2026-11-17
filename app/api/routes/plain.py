"""Plain-language and consumer-compliance endpoints (roadmap P12, D-068).

Provides:
    GET /api/v1/cases/{case_id}/plain         — finding + deadlines + banner in
                                                plain language (WP-122)
    GET /api/v1/modules/{module_id}/plain     — a module's plain-language copy
    GET /api/v1/meta/disclaimer/plain         — disclaimer summary in Bürgersprache /
                                                Leichte Sprache / plain English + ack
                                                instructions (WP-125)
    GET /api/v1/meta/privacy                  — effective privacy posture of this
                                                installation, plain texts (WP-125)

The ``/meta/*`` routes sit under the disclaimer middleware's excluded prefix
on purpose: a person must be able to read the disclaimer summary and the
privacy posture *before* acknowledging. All texts are fixed copy; nothing
here calls an LLM. Dates in deadline texts come from the Fristen core only.
"""

# Semantic Version: 1.0.0 | 2026-11-17 — P12 (WP-122, WP-125): initial version.

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from app.core.config import _get_settings
from app.db.session import async_session_factory
from app.dossier.builder import deadlines_section
from app.modules.runtime import MODULE_UNKNOWN, module_registry
from app.plain.copy import PlainCopyError
from app.plain.core_copy import CoreCopyError, core_languages, language_meta, load_core_copy
from app.plain.service import (
    PlainLanguageRequestError,
    case_plain,
    ergebnis_of,
    module_plain,
    parse_languages,
)
from app.services import dossier_service
from app.services.disclosure import DISCLOSURE_VERSION, build_disclosure_and_provenance
from app.services.dossier_service import CaseNotFoundError

logger = logging.getLogger(__name__)

router = APIRouter()

PLAIN_LANGUAGE_INVALID = "PLAIN_LANGUAGE_INVALID"
PLAIN_LANGUAGE_UNAVAILABLE = "PLAIN_LANGUAGE_UNAVAILABLE"

_LANG_QUERY = Query(
    None,
    description="Comma-separated language keys, e.g. 'de,de-LS,en' (default: de).",
)


def _languages(raw: str | None, *, default: tuple[str, ...] = ("de",)) -> list[str]:
    try:
        return parse_languages(raw, default=default)
    except PlainLanguageRequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": PLAIN_LANGUAGE_INVALID, "message": str(exc), "values": exc.values},
        ) from None


def _copy_defect(exc: Exception) -> HTTPException:
    # A declared-but-invalid copy file is a module/core defect, not a client error.
    logger.error("plain-language copy defect: %s", exc)
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail={"error": "plain_copy_invalid", "message": str(exc)},
    )


def _final_output(case: Any) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for log in case.stage_logs or []:
        if log.stage_name == "generation" and isinstance(log.output_snapshot, dict):
            out.update(log.output_snapshot)
    return out


# ---------------------------------------------------------------------------
# Cases
# ---------------------------------------------------------------------------


@router.get("/cases/{case_id}/plain")
async def get_case_plain(case_id: UUID, lang: str | None = _LANG_QUERY) -> dict[str, Any]:
    """Plain-language finding and deadlines of a stored case.

    Deadlines are evaluated live by the Fristen core from the case's current
    chronology decisions and confirmed facts (the same inputs the dossier
    uses), so a confirmation made via ``PUT …/dossier/chronology`` shows here
    at once — no dossier build needed.
    """
    languages = _languages(lang)
    async with async_session_factory() as db:
        try:
            loaded = await dossier_service.load_case(db, case_id)
        except CaseNotFoundError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Case not found"
            ) from None
    inputs = dossier_service.case_inputs(loaded, revision=0)
    try:
        body = case_plain(
            _final_output(loaded.case),
            loaded.legal_areas,
            deadlines_section(inputs),
            languages,
        )
    except PlainCopyError as exc:
        raise _copy_defect(exc) from exc
    disclosure, provenance = build_disclosure_and_provenance(
        _get_settings(), loaded.legal_areas or None
    )
    return {
        "case_id": str(case_id),
        **body,
        "has_ergebnis": ergebnis_of(_final_output(loaded.case)) is not None,
        "disclosure": disclosure.model_dump(mode="json"),
        "provenance": provenance.model_dump(mode="json"),
    }


# ---------------------------------------------------------------------------
# Modules
# ---------------------------------------------------------------------------


@router.get("/modules/{module_id}/plain")
async def get_module_plain(module_id: str, lang: str | None = _LANG_QUERY) -> dict[str, Any]:
    """The module's plain-language copy (all languages unless ``lang`` names some)."""
    manifest = module_registry().modules.get(module_id)
    if manifest is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": MODULE_UNKNOWN,
                "message": f"Kein installiertes Modul mit der Kennung '{module_id}'.",
                "module_id": module_id,
            },
        )
    languages = _languages(lang, default=()) if lang else None
    try:
        body = module_plain(manifest, languages)
    except PlainCopyError as exc:
        raise _copy_defect(exc) from exc
    if not body["available_languages"]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": PLAIN_LANGUAGE_UNAVAILABLE,
                "message": f"Modul '{module_id}' hat noch keine Texte in einfacher Sprache.",
                "module_id": module_id,
            },
        )
    return body


# ---------------------------------------------------------------------------
# Meta (no disclaimer ack needed — readable before acknowledging)
# ---------------------------------------------------------------------------


def _core(language: str) -> dict[str, Any]:
    settings = _get_settings()
    if language not in core_languages():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": PLAIN_LANGUAGE_UNAVAILABLE,
                "message": f"No core plain-language copy for {language!r}.",
                "available": core_languages(),
            },
        )
    try:
        return load_core_copy(
            language,
            disclaimer_version=str(settings.DISCLAIMER_VERSION),
            disclosure_version=DISCLOSURE_VERSION,
        )
    except CoreCopyError as exc:
        # Stale pin after a disclaimer bump: refuse rather than show a
        # summary of a text the person is no longer acknowledging.
        logger.error("core plain copy unusable: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": "plain_copy_stale", "message": str(exc)},
        ) from exc


@router.get("/meta/disclaimer/plain")
async def get_disclaimer_plain(lang: str | None = _LANG_QUERY) -> dict[str, Any]:
    """Disclaimer summary + Art. 50 notice in plain language, with ack instructions."""
    languages = _languages(lang)
    settings = _get_settings()
    texts: dict[str, Any] = {}
    for language in languages:
        doc = _core(language)
        texts[language] = {
            **language_meta(doc),
            "disclaimer": doc["disclaimer"],
            "ai_notice": doc["ai_notice"],
        }
    return {
        "version": settings.DISCLAIMER_VERSION,
        "disclosure_version": DISCLOSURE_VERSION,
        "available_languages": core_languages(),
        "texts": texts,
        "ack": {
            "header": "X-Disclaimer-Ack",
            "value": settings.DISCLAIMER_VERSION,
            "note": (
                "Send this header on every request after the person has confirmed "
                "the ack_label; re-ask when GET /api/v1/meta/disclaimer/version changes."
            ),
        },
        "full_text": {"de": "DISCLAIMER_DE.md", "en": "DISCLAIMER_EN.md"},
    }


@router.get("/meta/privacy")
async def get_privacy(lang: str | None = _LANG_QUERY) -> dict[str, Any]:
    """Effective privacy posture of this installation (non-secret settings) + plain texts."""
    from app.services.inference_profiles import get_active_profile

    settings = _get_settings()
    languages = _languages(lang)
    try:
        profile = get_active_profile()
        inference: dict[str, Any] = {
            "profile": profile.name,
            "data_residency": profile.data_residency,
            "pseudonymization": profile.pseudonymization,
            "avv_status": profile.avv_status,
            "external_hosts": [
                h for h in profile.host_allowlist if h not in ("localhost", "127.0.0.1", "::1")
            ],
        }
        profile_key = profile.name
    except ValueError as exc:
        logger.warning("privacy view: active profile unavailable: %s", exc)
        inference = {"profile": str(settings.INFERENCE_PROFILE), "error": "profile_unavailable"}
        profile_key = "unknown"
    mode = str(settings.DEPLOYMENT_MODE)
    texts: dict[str, Any] = {}
    for language in languages:
        privacy = _core(language)["privacy"]
        by_profile = privacy["inference"]
        texts[language] = {
            **language_meta(_core(language)),
            "title": privacy["title"],
            "storage": privacy["storage"],
            "deletion": privacy["deletion"],
            "inference": by_profile.get(profile_key, by_profile["unknown"]),
            "deployment": privacy["deployment"][mode],
            "residual_risk": privacy["residual_risk"],
        }
    return {
        "deployment_mode": mode,
        "synthetic_data_only": bool(settings.CITIZEN_SYNTHETIC_DATA_ONLY),
        "inference": inference,
        "storage": {
            "cases_stored": True,
            "delete_case": "DELETE /api/v1/cases/{case_id}",
            "delete_conversation": "DELETE /api/v1/conversations/{conversation_id}",
            "note": (
                "Deleting a case removes its analysis, claims, dossiers and area rows; "
                "conversation documents attached to it stay until their conversation is "
                "deleted."
            ),
        },
        "texts": texts,
    }
