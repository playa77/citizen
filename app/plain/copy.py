"""Module plain-language copy: loading, validation, category keys (WP-122, D-068).

A module declares its copy in the manifest (core_api 3.2)::

    plain_language:
      files: { de: copy/de/plain.yaml, de-LS: copy/de-LS/plain.yaml, en: copy/en/plain.yaml }
      goldset: goldset/plain-v1.0.0.yaml

Each file is one language (``citizen-plain-copy-v1.0``,
``app/plain/copy.schema.json``). Finding copy is keyed by *category key*:
the slug of the term before " – " in the module prompt profile's
``result_categories`` plus the core's open category (``einordnung_offen``).
Deadline copy is keyed by deadline spec id. Coverage of both is checked
offline by ``eval.plain_eval``; this module only loads and validates.
"""

# Semantic Version: 1.0.0 | 2026-11-17 — WP-122: initial version.

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from app.modules.content import load_section, load_yaml
from app.modules.registry import ModuleManifest, ModuleManifestError
from app.modules.runtime import get_manifest

COPY_FORMAT = "citizen-plain-copy-v1.0"
SCHEMA_PATH = Path(__file__).with_name("copy.schema.json")

#: The core's domain-neutral result category (app/services/prompts.py
#: ``_OPEN_CATEGORY``); every module must ship copy for it.
OPEN_CATEGORY_TERM = "Einordnung offen"

_UMLAUTS = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})


class PlainCopyError(ModuleManifestError):
    """A module's plain-language copy is missing or invalid."""


@dataclass(frozen=True)
class FindingCategory:
    key: str
    term: str


def category_key(term: str) -> str:
    """``"überwiegend rechtmäßig"`` → ``"ueberwiegend_rechtmaessig"``."""
    folded = term.strip().lower().translate(_UMLAUTS)
    folded = unicodedata.normalize("NFKD", folded).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "_", folded).strip("_")


def _term(category: str) -> str:
    # "rechtswidrig – ein Fehler …" → "rechtswidrig"; a dash-less entry is the term.
    return re.split(r"\s+[–-]\s+", category, maxsplit=1)[0].strip()


def _profile(manifest: ModuleManifest, seen: frozenset[str] = frozenset()) -> dict[str, Any]:
    data = load_section(manifest, "prompts")
    if isinstance(data, dict) and isinstance(data.get("inherit"), str):
        parent = data["inherit"]
        if parent in seen:
            raise PlainCopyError(f"module {manifest.id!r}: prompt profile inherit cycle")
        return _profile(get_manifest(parent), seen | {manifest.id})
    return data if isinstance(data, dict) else {}


def finding_categories(manifest: ModuleManifest) -> list[FindingCategory]:
    """The module's result categories (profile order) plus the open category."""
    raw = _profile(manifest).get("result_categories") or []
    terms = [_term(str(c)) for c in raw if str(c).strip()]
    terms.append(OPEN_CATEGORY_TERM)
    out: list[FindingCategory] = []
    for term in terms:
        key = category_key(term)
        if key and all(c.key != key for c in out):
            out.append(FindingCategory(key, term))
    return out


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def declared_copy_files(manifest: ModuleManifest) -> dict[str, str]:
    """``{language: relative path}`` from the manifest; empty if undeclared."""
    block = manifest.raw.get("plain_language")
    if not isinstance(block, dict):
        return {}
    files = block.get("files")
    return {str(k): str(v) for k, v in files.items()} if isinstance(files, dict) else {}


def copy_languages(manifest: ModuleManifest) -> list[str]:
    return list(declared_copy_files(manifest))


def validate_copy(doc: Any, manifest: ModuleManifest, language: str) -> list[str]:
    """Schema and identity errors of one copy document (empty list: valid)."""
    errors = [
        f"{'/'.join(str(p) for p in e.path) or '<root>'}: {e.message}"
        for e in sorted(_validator().iter_errors(doc), key=lambda e: list(e.path))
    ]
    if isinstance(doc, dict):
        if doc.get("module") not in (None, manifest.id):
            errors.append(f"module: {doc.get('module')!r} != {manifest.id!r}")
        if doc.get("language") not in (None, language):
            errors.append(f"language: {doc.get('language')!r} != declared key {language!r}")
    return errors


def load_copy(manifest: ModuleManifest, language: str) -> dict[str, Any]:
    """The validated copy document of *manifest* in *language*.

    Raises :class:`PlainCopyError` if the language is not declared or the
    file is invalid (a declared-but-invalid file is a module defect, not a
    request error).
    """
    files = declared_copy_files(manifest)
    if language not in files:
        raise PlainCopyError(f"module {manifest.id!r} has no plain-language copy for {language!r}")
    doc = load_yaml(manifest, files[language])
    errors = validate_copy(doc, manifest, language)
    if errors:
        raise PlainCopyError(
            f"module {manifest.id!r}: invalid copy {files[language]!r}: " + "; ".join(errors)
        )
    return dict(doc)


def plain_goldset_path(manifest: ModuleManifest) -> str | None:
    block = manifest.raw.get("plain_language")
    if isinstance(block, dict) and isinstance(block.get("goldset"), str):
        return str(block["goldset"])
    return None


__all__ = [
    "COPY_FORMAT",
    "OPEN_CATEGORY_TERM",
    "FindingCategory",
    "PlainCopyError",
    "category_key",
    "copy_languages",
    "declared_copy_files",
    "finding_categories",
    "load_copy",
    "plain_goldset_path",
    "validate_copy",
]
