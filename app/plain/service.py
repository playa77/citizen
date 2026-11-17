"""Plain-language views for the API (WP-122/WP-125, D-068).

Assembles the ``plain`` objects served by ``/analyze`` (opt-in),
``/cases/{id}/plain``, ``/modules/{id}/plain``, ``/meta/disclaimer/plain``
and ``/meta/privacy``. No database access here except through the loaded
case passed in; no LLM calls.
"""

# Semantic Version: 1.0.0 | 2026-11-17 — WP-122/WP-125: initial version.

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from app.modules.registry import ModuleManifest
from app.modules.runtime import get_manifest, request_modules
from app.plain.copy import copy_languages, finding_categories, load_copy
from app.plain.render import (
    PLAIN_SPEC_VERSION,
    deadline_banner,
    render_deadline,
    render_finding,
)

#: Language keys a request may name (copy-file keys: ``de``, ``de-LS``, ``en``…).
_LANG_RE = re.compile(r"^[a-z]{2}(-LS)?$")
MAX_LANGUAGES = 6
DEFAULT_LANGUAGES: tuple[str, ...] = ("de",)


class PlainLanguageRequestError(ValueError):
    """Malformed language list (→ 422 ``PLAIN_LANGUAGE_INVALID``)."""

    def __init__(self, message: str, values: list[str]) -> None:
        super().__init__(message)
        self.values = values


def parse_languages(raw: Any, *, default: Sequence[str] = DEFAULT_LANGUAGES) -> list[str]:
    """Accept a list or a comma-separated string; dedupe, keep order."""
    if raw is None or raw == "" or raw == []:
        return list(default)
    if isinstance(raw, str):
        values = [v.strip() for v in raw.split(",")]
    elif isinstance(raw, list):
        values = [str(v).strip() for v in raw]
    else:
        raise PlainLanguageRequestError("languages must be a list or a comma-separated string", [])
    values = [v for v in values if v]
    bad = [v for v in values if not _LANG_RE.match(v)]
    if bad:
        raise PlainLanguageRequestError("language keys look like 'de', 'de-LS' or 'en'", bad)
    unique = list(dict.fromkeys(values))
    if len(unique) > MAX_LANGUAGES:
        raise PlainLanguageRequestError(f"at most {MAX_LANGUAGES} languages", unique)
    return unique or list(default)


def ergebnis_of(final_output: Mapping[str, Any] | None) -> str | None:
    """The ``ergebnis`` section of a pipeline result (flat or nested)."""
    if not final_output:
        return None
    value = final_output.get("ergebnis")
    if value is None and isinstance(final_output.get("final_output"), Mapping):
        value = final_output["final_output"].get("ergebnis")
    return str(value) if value is not None else None


def _first_with_copy(module_ids: Iterable[str]) -> ModuleManifest | None:
    for module_id in module_ids:
        manifest = get_manifest(module_id)
        if copy_languages(manifest):
            return manifest
    return None


def finding_view(
    final_output: Mapping[str, Any] | None,
    legal_areas: list[str] | None,
    languages: Sequence[str],
) -> dict[str, Any] | None:
    """Plain finding for the case's primary module with copy; ``None`` if none has copy."""
    manifest = _first_with_copy(request_modules(legal_areas or None))
    if manifest is None:
        return None
    return render_finding(manifest, ergebnis_of(final_output), languages)


def analysis_plain(
    final_output: Mapping[str, Any] | None,
    legal_areas: list[str] | None,
    languages: Sequence[str],
) -> dict[str, Any]:
    """The ``plain`` object of the ``/analyze`` terminal event."""
    return {
        "spec_version": PLAIN_SPEC_VERSION,
        "languages": list(languages),
        "finding": finding_view(final_output, legal_areas, languages),
    }


def case_plain(
    final_output: Mapping[str, Any] | None,
    legal_areas: list[str] | None,
    deadline_section: Mapping[str, Any],
    languages: Sequence[str],
) -> dict[str, Any]:
    """Finding + deadlines + banner for one stored case."""
    rendered: list[dict[str, Any]] = []
    for item in deadline_section.get("items") or []:
        manifest = get_manifest(str(item["module_id"]))
        entry = render_deadline(manifest, item, languages)
        entry["assumptions"] = list(item.get("assumptions") or [])
        rendered.append(entry)
    return {
        "spec_version": PLAIN_SPEC_VERSION,
        "languages": list(languages),
        "finding": finding_view(final_output, legal_areas, languages),
        "deadlines": rendered,
        "banner": deadline_banner(rendered),
        "facts_used": dict(deadline_section.get("facts_used") or {}),
    }


def module_plain(manifest: ModuleManifest, languages: Sequence[str] | None) -> dict[str, Any]:
    """The module's copy (all declared languages, or the requested ones)."""
    available = copy_languages(manifest)
    wanted = list(languages) if languages else available
    copies: dict[str, Any] = {}
    for language in wanted:
        if language in available:
            copies[language] = load_copy(manifest, language)
    return {
        "module_id": manifest.id,
        "module_version": manifest.version,
        "spec_version": PLAIN_SPEC_VERSION,
        "available_languages": available,
        "categories": [{"key": c.key, "term": c.term} for c in finding_categories(manifest)],
        "copy": copies,
        "missing_languages": [lang for lang in wanted if lang not in available],
    }


__all__ = [
    "DEFAULT_LANGUAGES",
    "MAX_LANGUAGES",
    "PlainLanguageRequestError",
    "analysis_plain",
    "case_plain",
    "ergebnis_of",
    "finding_view",
    "module_plain",
    "parse_languages",
]
