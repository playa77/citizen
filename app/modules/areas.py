"""Area tables assembled from installed modules (WP-93; ARCHITECTURE.md § 3.1).

The v2.0.0 core carried one hard-coded table per concern, keyed by legal
area (intake keywords, synonyms, presets, corpus source types, BGB § range
tags, prompt profiles). WP-93 moved every row into the module that owns the
area key; this layer reassembles the same tables — in the same order — for
the core services that consume them.

Area keys and ownership
-----------------------
An *area key* is a value of ``legal_areas`` / ``case_run_area.legal_area``.
Since WP-94 the key set is data: every ``areas`` row of an installed
module's ``intake.yaml`` (and of the core procedural library) declares one
key and its ``order``; keys are served in ascending ``order`` (replaces the
former ``LEGAL_AREA_ALLOWED`` tuple and its DB CHECK, D-057). Each key has
exactly one owner, and only the owner may declare it:

* the installed module whose ``id`` equals the key, or
* the installed module that lists the key in ``legacy_aliases`` (D-038:
  ``schenkungsrecht`` → ``erbrecht``; the key stays a distinct stored value
  in ``case_run_area.legal_area``, its module is recorded in ``module_id``,
  D-057), or
* the core procedural library (``app/modules/procedural/``; D-038 folds
  ``verwaltungsrecht`` into the core instead of making it a module).

Tables are built from *installed* modules regardless of enablement: request
gating by enablement (``MODULE_NOT_ENABLED``) is WP-95, and v2.0.0 served
every area key in every deployment mode.

Ordering rules (behaviour-preserving, pinned by tests):

* per-area tables follow the declared ``order`` (v2.0.0 order preserved);
* modules are ordered by the first area key they own;
* preset keyword candidates follow declared area order; tied matches are all
  suggested and no-match results suggest none (D-070).
"""

# Semantic Version: 0.3.0 | 2026-11-17 — WP-112: tables include out-of-tree modules.
# 0.2.0 | 2026-11-16 — WP-94: area-key set and order read from
# module/procedural intake data (`order`); LEGAL_AREA_ALLOWED removed.

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
    discover_installed_modules,
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
    # area key → raw prompt profile mapping (inheritance resolved)
    prompt_profiles: dict[str, dict[str, Any]] = field(default_factory=dict)
    # module id → raw prompt profile mapping, including explicit inheritance
    module_profiles: dict[str, dict[str, Any]] = field(default_factory=dict)


def _procedural_section(name: str) -> dict[str, Any]:
    path = PROCEDURAL_DIR / f"{name}.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ModuleManifestError(f"procedural library file {path} is not a mapping")
    return data


def _declared_area_keys(
    modules: dict[str, ModuleManifest], procedural_intake: dict[str, Any]
) -> tuple[tuple[str, ...], dict[str, str]]:
    """Area keys declared by the intake files, sorted by ``order``.

    Returns the ordered keys and key → declaring owner id. A key declared
    twice, a missing/non-integer ``order`` or a duplicate ``order`` value is a
    content error (the order is behaviour: it drives table and prompt order).
    """
    declared: dict[str, tuple[int, str]] = {}
    sources: list[tuple[str, dict[str, Any]]] = [(PROCEDURAL_OWNER, procedural_intake)]
    for module_id, manifest in modules.items():
        data = load_section(manifest, "intake")
        if data is None:
            continue
        if not isinstance(data, dict):
            raise ModuleManifestError(f"module {module_id!r}: intake file is not a mapping")
        sources.append((module_id, data))
    for owner_id, data in sources:
        for key, entry in (data.get("areas") or {}).items():
            if key in declared:
                raise ModuleManifestError(
                    f"area key {key!r} declared by both {declared[key][1]!r} and {owner_id!r}"
                )
            rank = (entry or {}).get("order")
            if not isinstance(rank, int) or isinstance(rank, bool):
                raise ModuleManifestError(
                    f"{owner_id}: area key {key!r} needs an integer `order` in its intake row"
                )
            declared[key] = (rank, owner_id)
    ranks = [rank for rank, _ in declared.values()]
    if len(set(ranks)) != len(ranks):
        raise ModuleManifestError("duplicate area-key `order` values across intake files")
    keys = tuple(sorted(declared, key=lambda k: declared[k][0]))
    return keys, {key: owner_id for key, (_, owner_id) in declared.items()}


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


def build_area_tables(modules_dir: Path) -> AreaTables:
    """Assemble the area tables from the modules installed under *modules_dir*."""
    # WP-112: out-of-tree modules contribute area keys too (installed ≠ enabled).
    modules, _rejected = discover_installed_modules(modules_dir)
    return build_area_tables_from(modules)


def build_area_tables_from(modules: dict[str, ModuleManifest]) -> AreaTables:
    """Assemble the area tables from an explicit module set (WP-115 validator:
    the installed set plus a candidate module)."""
    procedural_intake = _procedural_section("intake")
    keys, declared_by = _declared_area_keys(modules, procedural_intake)
    procedural_keys = set((procedural_intake.get("areas") or {}).keys())
    owner = _resolve_owners(keys, modules, procedural_keys)
    for key in keys:
        if declared_by[key] != owner[key]:
            raise ModuleManifestError(
                f"area key {key!r} is declared by {declared_by[key]!r} "
                f"but owned by {owner[key]!r}"
            )

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
        for fb in intake_section.get("preset_keyword_fallback") or ():
            preset_fallback.append(
                PresetFallback(fb["preset"], fb["primary_area"], tuple(fb.get("keywords") or ()))
            )

    if len(catch_all) != 1:
        raise ModuleManifestError(
            f"exactly one area key must be the intake catch-all; found {catch_all or 'none'}"
        )
    preset_ids = [p["id"] for p in presets]
    if len(set(preset_ids)) != len(preset_ids):
        raise ModuleManifestError("duplicate preset ids across modules")
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
        prompt_profiles=prompt_profiles,
        module_profiles=module_profiles,
    )


@lru_cache(maxsize=1)
def area_tables() -> AreaTables:
    """Area tables for all installed peer modules; listing is not selection."""
    return build_area_tables(default_modules_root())


__all__ = [
    "PROCEDURAL_DIR",
    "PROCEDURAL_OWNER",
    "AreaTables",
    "PresetFallback",
    "area_tables",
    "build_area_tables",
    "build_area_tables_from",
]
