"""Module dossier content: load, validate, select and merge (WP-102).

A module's ``dossier.yaml`` (manifest key ``dossier``) declares the
Dokumentencheckliste, the Fragenliste for the advice/lawyer appointment and
the chronology cues, as data validated against
``module-dossier.schema.json``. Item selection is deterministic: an item
without ``when`` always applies; ``when.any_keyword`` applies when any
keyword occurs (case-insensitive) in the case's document texts.

Multi-module cases (ARCHITECTURE.md § 3.2) merge generically: modules in case
area order; items sharing a ``merge_key`` across modules are emitted once
(first module's wording wins) and list every contributing module.
"""

# Semantic Version: 1.0.0 | 2026-11-16 — WP-102 initial.

from __future__ import annotations

import json
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import jsonschema

from app.dossier.chronology import ChronologyCue
from app.modules.content import load_section, module_path
from app.modules.registry import ModuleManifestError
from app.modules.runtime import get_manifest

MODULE_DOSSIER_FORMAT = "citizen-module-dossier-v1.0"
_SCHEMA_PATH = Path(__file__).with_name("module-dossier.schema.json")


@lru_cache(maxsize=1)
def _schema() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    return data


def validate_module_dossier(data: Any, *, context: str) -> None:
    """Raise ``ModuleManifestError`` if *data* violates the content schema.

    Beyond the JSON Schema: ids are unique per list.
    """
    try:
        jsonschema.validate(data, _schema())
    except jsonschema.ValidationError as exc:
        path = "/".join(str(p) for p in exc.absolute_path) or "<root>"
        raise ModuleManifestError(
            f"{context}: dossier content invalid at {path}: {exc.message}"
        ) from None
    for key in ("checklist", "questions"):
        ids = [item["id"] for item in data[key]]
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        if dupes:
            raise ModuleManifestError(f"{context}: duplicate {key} ids {dupes}")


@dataclass(frozen=True)
class ModuleDossier:
    module_id: str
    checklist: tuple[dict[str, Any], ...]
    questions: tuple[dict[str, Any], ...]
    cues: tuple[ChronologyCue, ...]
    goldset_path: Path | None
    gate: dict[str, float] = field(default_factory=dict)


@lru_cache(maxsize=32)
def module_dossier(module_id: str) -> ModuleDossier | None:
    """The validated dossier content of *module_id*; ``None`` if undeclared."""
    manifest = get_manifest(module_id)
    data = load_section(manifest, "dossier")
    if data is None:
        return None
    validate_module_dossier(data, context=f"module {module_id!r}")
    goldset = data.get("goldset")
    goldset_path = module_path(manifest, goldset["path"]) if goldset else None
    if goldset_path is not None and not goldset_path.is_file():
        raise ModuleManifestError(
            f"module {module_id!r}: dossier goldset {goldset['path']!r} does not exist"
        )
    return ModuleDossier(
        module_id=module_id,
        checklist=tuple(data["checklist"]),
        questions=tuple(data["questions"]),
        cues=tuple(
            ChronologyCue(
                kind=cue["kind"],
                label_de=cue["label_de"],
                before_any=tuple(cue["before_any"]),
                module_id=module_id,
            )
            for cue in data.get("chronology_cues", [])
        ),
        goldset_path=goldset_path,
        gate={k: float(v) for k, v in ((goldset or {}).get("gate") or {}).items()},
    )


def fold(text: str) -> str:
    """Matching form: NFC (OCR/PDF text may carry decomposed umlauts), casefolded."""
    return unicodedata.normalize("NFC", text).casefold()


def _applies(item: dict[str, Any], haystack: str) -> bool:
    when = item.get("when")
    if not when:
        return True
    return any(fold(keyword) in haystack for keyword in when.get("any_keyword", []))


def _merge(
    contents: Sequence[ModuleDossier], key: str, haystack: str
) -> list[tuple[dict[str, Any], list[str]]]:
    merged: list[tuple[dict[str, Any], list[str]]] = []
    by_merge_key: dict[str, list[str]] = {}
    for content in contents:
        for item in getattr(content, key):
            if not _applies(item, haystack):
                continue
            merge_key = item.get("merge_key")
            if merge_key and merge_key in by_merge_key:
                if content.module_id not in by_merge_key[merge_key]:
                    by_merge_key[merge_key].append(content.module_id)
                continue
            modules = [content.module_id]
            if merge_key:
                by_merge_key[merge_key] = modules
            merged.append((item, modules))
    return merged


def select_checklist(
    contents: Sequence[ModuleDossier], texts: Sequence[str]
) -> list[dict[str, Any]]:
    """Applicable checklist items of all *contents*, merged (schema shape)."""
    haystack = fold("\n".join(texts))
    return [
        {
            "id": item["id"],
            "module_id": modules[0],
            "modules": modules,
            "label_de": item["label_de"],
            "why_de": item.get("why_de"),
            "topic": item.get("topic"),
            "required": bool(item["required"]),
        }
        for item, modules in _merge(contents, "checklist", haystack)
    ]


def select_questions(
    contents: Sequence[ModuleDossier], texts: Sequence[str]
) -> list[dict[str, Any]]:
    """Applicable module questions of all *contents*, merged (schema shape)."""
    haystack = fold("\n".join(texts))
    return [
        {
            "id": item["id"],
            "module_id": modules[0],
            "modules": modules,
            "text_de": item["text_de"],
            "topic": item.get("topic"),
            "origin": "module",
        }
        for item, modules in _merge(contents, "questions", haystack)
    ]


def all_cues(contents: Sequence[ModuleDossier]) -> list[ChronologyCue]:
    return [cue for content in contents for cue in content.cues]


def public_dossier_checklist(module_id: str) -> dict[str, Any] | None:
    """``dossier_checklist`` for ``GET /api/v1/modules/{module_id}``."""
    content = module_dossier(module_id)
    if content is None:
        return None
    return {
        "format": MODULE_DOSSIER_FORMAT,
        "checklist": [dict(item) for item in content.checklist],
        "questions": [dict(item) for item in content.questions],
    }
