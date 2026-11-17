"""Core plain-language copy: disclaimer summary, AI notice, privacy (WP-125, D-068).

Domain-neutral texts that every consumer surface needs, in Bürgersprache,
Leichte Sprache and plain English (``app/plain/core/<language>.yaml``,
``citizen-plain-core-copy-v1.0``). Each file is pinned to the disclaimer
and disclosure versions it summarises; :func:`load_core_copy` refuses a file
whose pin no longer matches the running versions, so a disclaimer bump can
never ship a stale plain summary (the endpoint answers 503 until the copy is
re-checked and re-pinned).
"""

# Semantic Version: 1.0.0 | 2026-11-17 — WP-125: initial version.

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from app.plain.languages import register_for

CORE_COPY_FORMAT = "citizen-plain-core-copy-v1.0"
CORE_COPY_DIR = Path(__file__).with_name("core")
#: Profile keys with own privacy copy; anything else reads ``unknown``.
_REQUIRED = {
    "disclaimer": ("title", "points", "ack_label", "full_text_note"),
    "ai_notice": ("title", "text"),
    "privacy": ("title", "storage", "deletion", "inference", "deployment", "residual_risk"),
}


class CoreCopyError(RuntimeError):
    """Core copy missing, malformed, or pinned to another disclaimer/disclosure version."""


def core_languages() -> list[str]:
    order = {"de": 0, "de-LS": 1, "en": 2}
    langs = [p.stem for p in CORE_COPY_DIR.glob("*.yaml")]
    return sorted(langs, key=lambda lang: (order.get(lang, 9), lang))


def structural_errors(doc: Any, language: str) -> list[str]:
    if not isinstance(doc, dict):
        return ["document is not a mapping"]
    errors: list[str] = []
    if doc.get("format") != CORE_COPY_FORMAT:
        errors.append(f"format must be {CORE_COPY_FORMAT!r}")
    if doc.get("language") != language:
        errors.append(f"language {doc.get('language')!r} != file name {language!r}")
    for section, keys in _REQUIRED.items():
        block = doc.get(section)
        if not isinstance(block, dict):
            errors.append(f"missing section {section!r}")
            continue
        errors.extend(f"{section}.{k} missing" for k in keys if not block.get(k))
    privacy = doc.get("privacy") or {}
    if isinstance(privacy, dict):
        if "unknown" not in (privacy.get("inference") or {}):
            errors.append("privacy.inference.unknown missing")
        for mode in ("dev", "self", "provider"):
            if mode not in (privacy.get("deployment") or {}):
                errors.append(f"privacy.deployment.{mode} missing")
    return errors


@lru_cache(maxsize=16)
def _read(language: str) -> dict[str, Any]:
    path = CORE_COPY_DIR / f"{language}.yaml"
    if not path.is_file():
        raise CoreCopyError(f"no core copy for language {language!r}")
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    errors = structural_errors(doc, language)
    if errors:
        raise CoreCopyError(f"core copy {path.name}: " + "; ".join(errors))
    return dict(doc)


def load_core_copy(
    language: str, *, disclaimer_version: str, disclosure_version: str
) -> dict[str, Any]:
    """Validated core copy; raises :class:`CoreCopyError` on a stale pin."""
    doc = _read(language)
    if doc.get("disclaimer_version") != disclaimer_version:
        raise CoreCopyError(
            f"core copy {language!r} summarises disclaimer {doc.get('disclaimer_version')!r}, "
            f"running disclaimer is {disclaimer_version!r}"
        )
    if str(doc.get("disclosure_version")) != disclosure_version:
        raise CoreCopyError(
            f"core copy {language!r} summarises disclosure {doc.get('disclosure_version')!r}, "
            f"running disclosure is {disclosure_version!r}"
        )
    return doc


def language_meta(doc: dict[str, Any]) -> dict[str, Any]:
    reg = register_for(str(doc["language"]))
    return {
        "language": reg.language,
        "bcp47": reg.bcp47,
        "register": reg.register,
        "review_status": (doc.get("review") or {}).get("status", "draft"),
    }


__all__ = [
    "CORE_COPY_DIR",
    "CORE_COPY_FORMAT",
    "CoreCopyError",
    "core_languages",
    "language_meta",
    "load_core_copy",
    "structural_errors",
]
