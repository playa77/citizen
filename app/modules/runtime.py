"""Request-time module resolution for the core services (WP-93; ARCHITECTURE.md § 3.2).

The pipeline, the calculation harness, the document renderer and the
deadline helpers ask this layer which module(s) a request runs with and
fetch the module's typed extension points and data through it — never by
importing module files directly.

Resolution rule (D-036/D-039): the request's area keys map to their owning
modules (legacy aliases to the module that owns them, D-038); keys served by
the core procedural library contribute no module; an empty ``legal_areas``
resolves to ``DEFAULT_MODULE``. Enablement gating (``MODULE_NOT_ENABLED``)
is WP-95 and deliberately absent here.
"""

# Semantic Version: 0.2.0 | 2026-11-16 — WP-94: area_module_binding() for the
# case_run_area module_id/module_version columns.

from __future__ import annotations

from datetime import date
from functools import lru_cache
from typing import Any

from app.fristen.evaluator import FristInput, evaluate_spec
from app.fristen.results import FristResult
from app.fristen.specs import DeadlineSpec, find_spec, load_specs
from app.modules.areas import PROCEDURAL_OWNER, area_tables
from app.modules.content import load_code_ref, load_section, module_path
from app.modules.registry import (
    ModuleManifest,
    ModuleManifestError,
    default_modules_root,
    discover_modules,
)
from app.modules.sdk import Calculator, RegimeProvider


@lru_cache(maxsize=1)
def installed_modules() -> dict[str, ModuleManifest]:
    """Installed in-tree modules (discovery is validated once per process)."""
    return discover_modules(default_modules_root())


def get_manifest(module_id: str) -> ModuleManifest:
    manifest = installed_modules().get(module_id)
    if manifest is None:
        raise ModuleManifestError(f"module {module_id!r} is not installed")
    return manifest


def request_modules(legal_areas: list[str] | None) -> list[str]:
    """Module ids a request runs with, in request order, de-duplicated.

    Unknown area keys are ignored here (request validation is the caller's
    job); an empty list resolves to the default module.
    """
    tables = area_tables()
    if not legal_areas:
        return [tables.default_module]
    modules: list[str] = []
    for key in legal_areas:
        owner = tables.owner.get(key)
        if owner is None or owner == PROCEDURAL_OWNER or owner in modules:
            continue
        modules.append(owner)
    return modules


class UnknownAreaKeyError(KeyError):
    """An area key that no installed module or the procedural library owns."""


def area_module_binding(area_key: str) -> tuple[str | None, str | None]:
    """``(module_id, module_version)`` to record for a stored area key.

    Legacy aliases bind to the module that declares them; keys served by the
    core procedural library bind to ``(None, None)``. An unknown key raises
    ``UnknownAreaKeyError`` — since WP-94 no DB CHECK rejects it, so the
    writer must (D-057).
    """
    owner = area_tables().owner.get(area_key)
    if owner is None:
        raise UnknownAreaKeyError(area_key)
    if owner == PROCEDURAL_OWNER:
        return None, None
    return owner, get_manifest(owner).version


# ---------------------------------------------------------------------------
# Typed code extension points
# ---------------------------------------------------------------------------


def calculators_for(module_ids: list[str]) -> list[tuple[str, Calculator]]:
    """``(module_id, Calculator)`` pairs of *module_ids*, in order."""
    result: list[tuple[str, Calculator]] = []
    for module_id in module_ids:
        ref = get_manifest(module_id).raw.get("calculators")
        if not isinstance(ref, str):
            continue
        calculators = load_code_ref(get_manifest(module_id), ref)
        for calculator in calculators:
            if not isinstance(calculator, Calculator):
                raise ModuleManifestError(
                    f"module {module_id!r}: {ref} must contain sdk.Calculator instances"
                )
            result.append((module_id, calculator))
    return result


def regime_providers_for(module_ids: list[str]) -> list[tuple[str, RegimeProvider]]:
    """``(module_id, RegimeProvider)`` pairs of *module_ids*, in order."""
    result: list[tuple[str, RegimeProvider]] = []
    for module_id in module_ids:
        regimes = get_manifest(module_id).raw.get("regimes")
        if not isinstance(regimes, dict):
            continue
        provider = load_code_ref(get_manifest(module_id), str(regimes["provider"]))
        if not isinstance(provider, RegimeProvider):
            raise ModuleManifestError(
                f"module {module_id!r}: {regimes['provider']} must be an sdk.RegimeProvider"
            )
        result.append((module_id, provider))
    return result


def regime_banner_for(module_ids: list[str], as_of: date) -> tuple[str | None, str]:
    """Regime key and banner text for the request's modules on *as_of*.

    Returns ``(regime_key, banner)``; with several providers the banners are
    joined by a blank line and the first provider's key is reported. No
    provider → ``(None, "")``.
    """
    providers = regime_providers_for(module_ids)
    if not providers:
        return None, ""
    keys = [provider.regime_for(as_of) for _, provider in providers]
    banners = [provider.banner(key) for (_, provider), key in zip(providers, keys, strict=True)]
    return keys[0], "\n\n".join(b for b in banners if b)


# ---------------------------------------------------------------------------
# Data sections
# ---------------------------------------------------------------------------


def parameter_domain(module_id: str) -> str | None:
    """The module's parameter-store namespace (manifest ``parameters.domain``)."""
    parameters = get_manifest(module_id).raw.get("parameters")
    if isinstance(parameters, dict):
        return str(parameters["domain"])
    return None


def document_templates(module_id: str) -> dict[str, Any] | None:
    """Parsed ``document_templates`` file of *module_id*, or ``None``."""
    data = load_section(get_manifest(module_id), "document_templates")
    if data is not None and not isinstance(data, dict):
        raise ModuleManifestError(f"module {module_id!r}: document_templates is not a mapping")
    return data


@lru_cache(maxsize=32)
def deadline_specs(module_id: str) -> tuple[DeadlineSpec, ...]:
    """The module's deadline specs (``fristen.yaml``), loaded once."""
    manifest = get_manifest(module_id)
    relative = manifest.raw.get("fristen")
    if not isinstance(relative, str):
        return ()
    return tuple(load_specs(module_path(manifest, relative)))


def compute_deadline(module_id: str, spec_id: str, frist_input: FristInput) -> FristResult:
    """Evaluate one module deadline spec through the Fristen core (§ 2.3)."""
    spec = find_spec(list(deadline_specs(module_id)), spec_id)
    return evaluate_spec(spec, frist_input, module_id=module_id)


__all__ = [
    "UnknownAreaKeyError",
    "area_module_binding",
    "calculators_for",
    "compute_deadline",
    "deadline_specs",
    "document_templates",
    "get_manifest",
    "installed_modules",
    "parameter_domain",
    "regime_banner_for",
    "regime_providers_for",
    "request_modules",
]
