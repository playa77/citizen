"""Area tables assembled from installed modules (WP-93; ARCHITECTURE.md § 3.1).

The v2.0.0 core carried one hard-coded table per concern, keyed by legal
area (intake keywords, synonyms, presets, corpus source types, BGB § range
tags, prompt profiles). WP-93 moved every row into the module that owns the
area key; this layer reassembles the same tables — in the same order — for
the core services that consume them.

Area keys and ownership
-----------------------
An *area key* is a value of ``legal_areas`` / ``case_run_area.legal_area``.
Until WP-94 replaces the CHECK constraint with a ``legal_module`` FK, the
ordered key set is ``app.db.models.LEGAL_AREA_ALLOWED`` — the DB still
enforces exactly that set, so the area tables must offer exactly it. Each
key has exactly one owner:

* the installed module whose ``id`` equals the key, or
* the installed module that lists the key in ``legacy_aliases`` (D-038:
  ``schenkungsrecht`` → ``erbrecht``; the key stays a distinct stored value
  until WP-94), or
* the core procedural library (``app/modules/procedural/``; D-038 folds
  ``verwaltungsrecht`` into the core instead of making it a module).

Tables are built from *installed* modules regardless of enablement: request
gating by enablement (``MODULE_NOT_ENABLED``) is WP-95, and v2.0.0 served
every area key in every deployment mode.

Ordering rules (behaviour-preserving, pinned by tests):

* per-area tables follow ``LEGAL_AREA_ALLOWED`` order;
* modules are ordered by the first area key they own;
* the preset keyword fallback lists the default module's entries **last**
  (the default preset is the fallback and wins only on a strictly higher
  score — the v2.0.0 tie-break).
"""

# Semantic Version: 0.1.0

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from app.modules.content import load_section
from app.modules.registry import (
    ModuleManifest,
    ModuleManifestError,
    default_modules_root,
    discover_modules,
)

#: Owner id used for keys served by the core procedural library.
PROCEDURAL_OWNER = "core:procedural"

#: Location of the core procedural library's data files (D-038).
PROCEDURAL_DIR = Path(__file__).with_name("procedural")


@dataclass(frozen=True)
class PresetFallback:
    preset_id: str
    primary_area: str
    keywords: tuple[str, ...]


@dataclass(frozen=True)
class AreaTables:
    """Every area-keyed table the core consumes, in v2.0.0 order."""

    keys: tuple[str, ...]
    owner: dict[str, str]
    source_types: dict[str, tuple[str, ...]]
    keywords: dict[str, tuple[str, ...]]
    synonyms: dict[str, str]
    catch_all: str
    chunk_tags: tuple[tuple[str, int, int, str], ...]
    presets: tuple[dict[str, Any], ...]
    preset_fallback: tuple[PresetFallback, ...]
    fallback_preset: str
    default_module: str
    norm_reference_source_types: tuple[str, ...]
    # area key → raw prompt profile mapping (inheritance resolved)
    prompt_profiles: dict[str, dict[str, Any]] = field(default_factory=dict)
    # module id → raw prompt profile mapping, for the default fallback
    module_profiles: dict[str, dict[str, Any]] = field(default_factory=dict)


def _legal_area_keys() -> tuple[str, ...]:
    # WP-94 replaces this DB-bound table with the registry/legal_module rows.
    from app.db.models import LEGAL_AREA_ALLOWED

    return tuple(LEGAL_AREA_ALLOWED)


def _procedural_section(name: str) -> dict[str, Any]:
    path = PROCEDURAL_DIR / f"{name}.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ModuleManifestError(f"procedural library file {path} is not a mapping")
    return data


def _resolve_owners(
    keys: tuple[str, ...], modules: dict[str, ModuleManifest], procedural_keys: set[str]
) -> dict[str, str]:
    alias_owner: dict[str, str] = {}
    for manifest in modules.values():
        for alias in manifest.legacy_aliases:
            alias_owner[alias] = manifest.id
    owner: dict[str, str] = {}
    for key in keys:
        candidates = []
        if key in modules:
            candidates.append(key)
        if key in alias_owner:
            candidates.append(alias_owner[key])
        if key in procedural_keys:
            candidates.append(PROCEDURAL_OWNER)
        if len(candidates) != 1:
            raise ModuleManifestError(
                f"area key {key!r} must have exactly one owner (module id, legacy alias "
                f"or core procedural library); found {candidates or 'none'}"
            )
        owner[key] = candidates[0]
    return owner


def _section_for(owner_id: str, modules: dict[str, ModuleManifest], name: str) -> dict[str, Any]:
    if owner_id == PROCEDURAL_OWNER:
        return _procedural_section(name)
    data = load_section(modules[owner_id], name)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ModuleManifestError(f"module {owner_id!r}: {name} file is not a mapping")
    return data


def _area_entry(section: dict[str, Any], key: str, owner_id: str, name: str) -> dict[str, Any]:
    entry = (section.get("areas") or {}).get(key)
    if entry is None:
        raise ModuleManifestError(f"{owner_id}: {name} file has no row for area key {key!r}")
    return dict(entry)


def build_area_tables(modules_dir: Path, default_module: str) -> AreaTables:
    """Assemble the area tables from the modules installed under *modules_dir*."""
    modules = discover_modules(modules_dir)
    keys = _legal_area_keys()
    procedural_keys = set((_procedural_section("intake").get("areas") or {}).keys())
    owner = _resolve_owners(keys, modules, procedural_keys)
    if default_module not in modules:
        raise ModuleManifestError(f"DEFAULT_MODULE {default_module!r} is not installed")

    # Owners in order of their first area key.
    owners_in_order: list[str] = []
    for key in keys:
        if owner[key] not in owners_in_order:
            owners_in_order.append(owner[key])

    source_types: dict[str, tuple[str, ...]] = {}
    keywords: dict[str, tuple[str, ...]] = {}
    synonyms: dict[str, str] = {}
    catch_all: list[str] = []
    for key in keys:
        corpus = _area_entry(_section_for(owner[key], modules, "corpus"), key, owner[key], "corpus")
        source_types[key] = tuple(corpus.get("source_types") or ())
        intake = _area_entry(_section_for(owner[key], modules, "intake"), key, owner[key], "intake")
        if intake.get("keywords"):
            keywords[key] = tuple(intake["keywords"])
        for synonym in intake.get("synonyms") or ():
            if synonym in synonyms:
                raise ModuleManifestError(f"synonym {synonym!r} claimed by two area keys")
            synonyms[synonym] = key

    chunk_tags: list[tuple[str, int, int, str]] = []
    presets: list[dict[str, Any]] = []
    preset_fallback: list[PresetFallback] = []
    default_fallback: list[PresetFallback] = []
    fallback_preset: str | None = None
    for owner_id in owners_in_order:
        corpus_section = _section_for(owner_id, modules, "corpus")
        intake_section = _section_for(owner_id, modules, "intake")
        owned = {k for k in keys if owner[k] == owner_id}
        if intake_section.get("catch_all"):
            catch_all.extend(k for k in keys if owner[k] == owner_id)
        for tag in corpus_section.get("chunk_tags") or ():
            if tag["area"] not in owned:
                raise ModuleManifestError(
                    f"{owner_id}: chunk tag for area {tag['area']!r} it does not own"
                )
            chunk_tags.append((tag["source_type"], int(tag["from"]), int(tag["to"]), tag["area"]))
        for preset in intake_section.get("presets") or ():
            presets.append(dict(preset))
        target = default_fallback if owner_id == default_module else preset_fallback
        for fb in intake_section.get("preset_keyword_fallback") or ():
            target.append(
                PresetFallback(fb["preset"], fb["primary_area"], tuple(fb.get("keywords") or ()))
            )
        if owner_id == default_module:
            fallback_preset = intake_section.get("fallback_preset")
    preset_fallback.extend(default_fallback)

    if len(catch_all) != 1:
        raise ModuleManifestError(
            f"exactly one area key must be the intake catch-all; found {catch_all or 'none'}"
        )
    preset_ids = [p["id"] for p in presets]
    if len(set(preset_ids)) != len(preset_ids):
        raise ModuleManifestError("duplicate preset ids across modules")
    if fallback_preset is None or fallback_preset not in preset_ids:
        raise ModuleManifestError(
            f"default module {default_module!r} must declare a fallback_preset it ships"
        )

    default_corpus = _section_for(default_module, modules, "corpus")

    # Prompt profiles: one per module (inheritance resolved), mapped onto
    # every area key the module owns.
    module_profiles: dict[str, dict[str, Any]] = {}

    def _profile(module_id: str, seen: tuple[str, ...] = ()) -> dict[str, Any] | None:
        if module_id in seen:
            raise ModuleManifestError(f"prompt profile inheritance cycle: {(*seen, module_id)}")
        if module_id not in modules:
            raise ModuleManifestError(f"prompt profile inherits unknown module {module_id!r}")
        data = load_section(modules[module_id], "prompts")
        if data is None:
            return None
        if not isinstance(data, dict):
            raise ModuleManifestError(f"module {module_id!r}: prompt profile is not a mapping")
        if "inherit" in data:
            return _profile(str(data["inherit"]), (*seen, module_id))
        return {"key": module_id, **data}

    for module_id in modules:
        resolved = _profile(module_id)
        if resolved is not None:
            module_profiles[module_id] = resolved
    prompt_profiles = {
        key: module_profiles[owner[key]] for key in keys if owner[key] in module_profiles
    }
    if default_module not in module_profiles:
        raise ModuleManifestError(f"default module {default_module!r} has no prompt profile")

    return AreaTables(
        keys=keys,
        owner=owner,
        source_types=source_types,
        keywords=keywords,
        synonyms=synonyms,
        catch_all=catch_all[0],
        chunk_tags=tuple(chunk_tags),
        presets=tuple(presets),
        preset_fallback=tuple(preset_fallback),
        fallback_preset=fallback_preset,
        default_module=default_module,
        norm_reference_source_types=tuple(default_corpus.get("norm_reference_source_types") or ()),
        prompt_profiles=prompt_profiles,
        module_profiles=module_profiles,
    )


@lru_cache(maxsize=1)
def area_tables() -> AreaTables:
    """Area tables for the configured ``DEFAULT_MODULE`` and the in-tree modules."""
    from app.core.config import settings

    return build_area_tables(default_modules_root(), settings.DEFAULT_MODULE)


__all__ = [
    "PROCEDURAL_DIR",
    "PROCEDURAL_OWNER",
    "AreaTables",
    "PresetFallback",
    "area_tables",
    "build_area_tables",
]
