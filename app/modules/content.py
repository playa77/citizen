"""Module content loader (WP-93; ARCHITECTURE.md § 2.1).

Reads the files a manifest declares — YAML data (corpus scope, intake
tables, prompt profile, document templates, parameters, deadline specs,
goldset) and, for the two typed code extension points, Python attributes
(``calculators: "calculators:CALCULATORS"``, ``regimes.provider``).

Module directories are *not* Python packages on ``sys.path``. Module code is
imported under the synthetic package ``citizen_modules.<module_id>`` so that
relative imports inside a module work and module files never shadow core or
third-party names. The import-lint (``app.modules.lint``) bounds what that
code may import from the core.

Every path a manifest declares is resolved relative to the module directory
and must stay inside it (no ``..`` escapes, no absolute paths); a declared
file that does not exist is a manifest error. This closes the structural
validation D-042 deferred to WP-93.
"""

# Semantic Version: 0.3.0 | 2026-11-17 — WP-122: `plain_language` copy files and
# goldset are declared files.
# 0.2.0 | 2026-11-17 — WP-110: `errata` is a declared file.
# 0.1.0

from __future__ import annotations

import importlib.util
import sys
import types
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from app.modules.registry import ModuleManifest, ModuleManifestError

#: Synthetic parent package for imported module code.
MODULE_PACKAGE_ROOT = "citizen_modules"


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------


def module_path(manifest: ModuleManifest, relative: str) -> Path:
    """Resolve *relative* inside the module directory; refuse escapes."""
    candidate = (manifest.path / relative).resolve()
    root = manifest.path.resolve()
    if candidate != root and root not in candidate.parents:
        raise ModuleManifestError(
            f"module {manifest.id!r}: declared path {relative!r} leaves the module directory"
        )
    return candidate


def declared_files(manifest: ModuleManifest) -> list[str]:
    """Every file path the manifest declares (relative to the module dir).

    Glob patterns in ``parameters.files`` are reported as declared; they are
    checked for at least one match by :func:`missing_declared_files`.
    """
    raw = manifest.raw
    paths: list[str] = []
    for key in (
        "corpus",
        "fristen",
        "intake",
        "dossier",
        "prompts",
        "document_templates",
        "errata",
    ):
        value = raw.get(key)
        if isinstance(value, str):
            paths.append(value)
    goldset = raw.get("goldset")
    if isinstance(goldset, dict) and isinstance(goldset.get("path"), str):
        paths.append(goldset["path"])
    plain = raw.get("plain_language")
    if isinstance(plain, dict):
        files = plain.get("files")
        if isinstance(files, dict):
            paths.extend(str(p) for p in files.values())
        if isinstance(plain.get("goldset"), str):
            paths.append(plain["goldset"])
    parameters = raw.get("parameters")
    if isinstance(parameters, dict):
        paths.extend(str(p) for p in parameters.get("files", []))
    compliance = raw.get("compliance")
    if isinstance(compliance, dict):
        for key in ("purpose_drift_deny_file", "disclaimer_addendum"):
            if isinstance(compliance.get(key), str):
                paths.append(compliance[key])
    for key in ("calculators",):
        ref = raw.get(key)
        if isinstance(ref, str):
            paths.append(_code_ref_file(ref))
    regimes = raw.get("regimes")
    if isinstance(regimes, dict) and isinstance(regimes.get("provider"), str):
        paths.append(_code_ref_file(regimes["provider"]))
    return paths


def missing_declared_files(manifest: ModuleManifest) -> list[str]:
    """Return declared paths that do not exist (globs: no match)."""
    missing: list[str] = []
    for rel in declared_files(manifest):
        if any(ch in rel for ch in "*?["):
            if Path(rel).is_absolute() or ".." in Path(rel).parts:
                raise ModuleManifestError(
                    f"module {manifest.id!r}: declared pattern {rel!r} leaves the module directory"
                )
            if not any(manifest.path.glob(rel)):
                missing.append(rel)
            continue
        if not module_path(manifest, rel).is_file():
            missing.append(rel)
    return missing


def assert_declared_files_exist(manifest: ModuleManifest) -> None:
    """Raise ``ModuleManifestError`` if the manifest declares a missing file."""
    missing = missing_declared_files(manifest)
    if missing:
        raise ModuleManifestError(
            f"module {manifest.id!r} declares missing file(s): {', '.join(sorted(missing))}"
        )


# ---------------------------------------------------------------------------
# YAML data
# ---------------------------------------------------------------------------


@lru_cache(maxsize=256)
def _load_yaml_file(path: Path, mtime_ns: int) -> Any:
    # mtime in the cache key: an edited module file is re-read (dev loop);
    # the parsed value must be treated as read-only by callers.
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ModuleManifestError(f"unreadable module data file {path}: {exc}") from exc


def load_yaml(manifest: ModuleManifest, relative: str) -> Any:
    """Load a module YAML file (cached; callers must not mutate the result)."""
    path = module_path(manifest, relative)
    if not path.is_file():
        raise ModuleManifestError(f"module {manifest.id!r}: data file {relative!r} not found")
    return _load_yaml_file(path, path.stat().st_mtime_ns)


def load_section(manifest: ModuleManifest, key: str) -> Any:
    """Load the YAML file declared under manifest *key*, or ``None`` if undeclared."""
    relative = manifest.raw.get(key)
    if not isinstance(relative, str):
        return None
    return load_yaml(manifest, relative)


# ---------------------------------------------------------------------------
# Code extension points
# ---------------------------------------------------------------------------


def _code_ref_file(ref: str) -> str:
    module_file, _, _attr = ref.partition(":")
    return module_file.replace(".", "/") + ".py"


def _ensure_package(name: str, path: Path | None) -> None:
    if name in sys.modules:
        return
    package = types.ModuleType(name)
    package.__path__ = [str(path)] if path is not None else []
    package.__package__ = name
    sys.modules[name] = package


def import_module_file(manifest: ModuleManifest, module_file: str) -> types.ModuleType:
    """Import ``<module_dir>/<module_file>.py`` as ``citizen_modules.<id>.<file>``."""
    dotted = f"{MODULE_PACKAGE_ROOT}.{manifest.id}.{module_file}"
    cached = sys.modules.get(dotted)
    if cached is not None:
        return cached
    path = module_path(manifest, module_file.replace(".", "/") + ".py")
    if not path.is_file():
        raise ModuleManifestError(f"module {manifest.id!r}: code file {path.name!r} not found")
    _ensure_package(MODULE_PACKAGE_ROOT, None)
    _ensure_package(f"{MODULE_PACKAGE_ROOT}.{manifest.id}", manifest.path)
    spec = importlib.util.spec_from_file_location(dotted, path)
    if spec is None or spec.loader is None:
        raise ModuleManifestError(f"module {manifest.id!r}: cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[dotted] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(dotted, None)
        raise
    return module


def load_code_ref(manifest: ModuleManifest, ref: str) -> Any:
    """Resolve a manifest code reference ``"file:ATTRIBUTE"``."""
    module_file, sep, attr = ref.partition(":")
    if not sep or not module_file or not attr:
        raise ModuleManifestError(
            f"module {manifest.id!r}: code reference {ref!r} must be 'file:ATTRIBUTE'"
        )
    module = import_module_file(manifest, module_file)
    try:
        return getattr(module, attr)
    except AttributeError as exc:
        raise ModuleManifestError(
            f"module {manifest.id!r}: {module_file}.py has no attribute {attr!r}"
        ) from exc


__all__ = [
    "MODULE_PACKAGE_ROOT",
    "assert_declared_files_exist",
    "declared_files",
    "import_module_file",
    "load_code_ref",
    "load_section",
    "load_yaml",
    "missing_declared_files",
    "module_path",
]
