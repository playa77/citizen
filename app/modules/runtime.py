"""Request-time module resolution for the core services (WP-93; ARCHITECTURE.md § 3.2).

The pipeline, the calculation harness, the document renderer and the
deadline helpers ask this layer which module(s) a request runs with and
fetch the module's typed extension points and data through it — never by
importing module files directly.

Resolution rule (D-036/D-039): the request's area keys map to their owning
modules (legacy aliases to the module that owns them, D-038); keys served by
the core procedural library contribute no module; an empty ``legal_areas``
resolves to ``DEFAULT_MODULE``.

Request validation (WP-95, D-039): ``resolve_request_areas`` checks every
requested area key against the area tables and the running registry's
enabled set. An area key no installed module (or the procedural library)
serves → ``MODULE_UNKNOWN``; a key whose owning module is installed but not
enabled → ``MODULE_NOT_ENABLED``. ``request_modules`` itself stays lenient
(unknown keys ignored) because it also serves internal callers that pass
already-validated keys.
"""

# Semantic Version: 0.5.0 | 2026-11-16 — CR-06: regime_block_for() anchors the
# legal regime to the document's reference period and renders <rechtsstand>.
# 0.4.0 | 2026-11-16 — WP-96: module_provenance() /
# provenance_modules() for the citizen-provenance-v1.1 `modules` list.
# 0.3.0 | 2026-11-16 — WP-95: module_registry() (process-wide
# running registry), resolve_request_areas() with MODULE_UNKNOWN /
# MODULE_NOT_ENABLED, ResolvedArea for the `resolved_modules` response key.
# 0.2.0 | 2026-11-16 — WP-94: area_module_binding() for the
# case_run_area module_id/module_version columns.

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
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
    ModuleRegistry,
    default_modules_root,
    discover_modules,
    load_registry_from_settings,
)
from app.modules.sdk import Calculator, RegimeProvider


@lru_cache(maxsize=1)
def installed_modules() -> dict[str, ModuleManifest]:
    """Installed in-tree modules (discovery is validated once per process)."""
    return discover_modules(default_modules_root())


@lru_cache(maxsize=1)
def module_registry() -> ModuleRegistry:
    """The running registry (installed set, enabled set, default module).

    Built once per process from the live settings; startup calls it first,
    so a configuration error refuses startup before any request sees it.
    Tests that change ``ENABLED_MODULES``/``DEPLOYMENT_MODE`` call
    ``module_registry.cache_clear()``.
    """
    return load_registry_from_settings()


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
# Request validation + `resolved_modules` (WP-95)
# ---------------------------------------------------------------------------

#: Error codes of the module request contract (ARCHITECTURE.md § 5, D-039).
MODULE_UNKNOWN = "MODULE_UNKNOWN"
MODULE_NOT_ENABLED = "MODULE_NOT_ENABLED"


@dataclass(frozen=True)
class ResolvedArea:
    """How one requested area key resolved (one ``resolved_modules`` entry)."""

    legal_area: str
    module_id: str | None  # None: served by the core procedural library
    module_version: str | None
    legacy_alias: bool  # the key is a legacy alias of module_id (D-038)
    enabled: bool  # core procedural keys are always available

    def as_dict(self) -> dict[str, Any]:
        return {
            "legal_area": self.legal_area,
            "module_id": self.module_id,
            "module_version": self.module_version,
            "legacy_alias": self.legacy_alias,
            "enabled": self.enabled,
        }


class ModuleRequestError(ValueError):
    """A request names area keys that cannot run (unknown or not enabled)."""

    def __init__(self, code: str, legal_areas: list[str]) -> None:
        self.code = code
        self.legal_areas = legal_areas
        super().__init__(f"{code}: {', '.join(legal_areas)}")


def resolve_area(area_key: str) -> ResolvedArea | None:
    """Resolve one area key against the area tables and the running registry.

    Returns ``None`` for a key that no installed module (or the core
    procedural library) serves.
    """
    owner = area_tables().owner.get(area_key)
    if owner is None:
        return None
    if owner == PROCEDURAL_OWNER:
        return ResolvedArea(area_key, None, None, legacy_alias=False, enabled=True)
    return ResolvedArea(
        legal_area=area_key,
        module_id=owner,
        module_version=get_manifest(owner).version,
        legacy_alias=area_key != owner,
        enabled=module_registry().is_enabled(owner),
    )


def resolved_modules(area_keys: Iterable[str]) -> list[dict[str, Any]]:
    """``resolved_modules`` response entries for *area_keys* (lenient).

    For responses that *report* area keys (intake, presets): unknown keys are
    skipped instead of raising — they come from module data or a validated
    session, not from the caller.
    """
    entries: list[dict[str, Any]] = []
    for key in area_keys:
        resolved = resolve_area(key)
        if resolved is not None:
            entries.append(resolved.as_dict())
    return entries


def resolve_request_areas(legal_areas: list[str]) -> list[ResolvedArea]:
    """Validate a request's ``legal_areas`` (D-039) and resolve each key.

    Raises ``ModuleRequestError`` with code ``MODULE_UNKNOWN`` listing every
    unknown key, else with ``MODULE_NOT_ENABLED`` listing every key whose
    module is installed but not enabled. An empty list resolves to ``[]``
    (the caller runs ``DEFAULT_MODULE``, which is always enabled).
    """
    resolved: list[ResolvedArea] = []
    unknown: list[str] = []
    disabled: list[str] = []
    for key in legal_areas:
        entry = resolve_area(key)
        if entry is None:
            unknown.append(key)
            continue
        if not entry.enabled:
            disabled.append(key)
        resolved.append(entry)
    if unknown:
        raise ModuleRequestError(MODULE_UNKNOWN, unknown)
    if disabled:
        raise ModuleRequestError(MODULE_NOT_ENABLED, disabled)
    return resolved


# ---------------------------------------------------------------------------
# Provenance (WP-96; citizen-provenance-v1.1, ARCHITECTURE.md § 6.3)
# ---------------------------------------------------------------------------


@lru_cache(maxsize=64)
def module_provenance(module_id: str) -> tuple[str, str, str | None]:
    """``(id, version, parameter_set)`` of an installed module, computed once.

    ``parameter_set`` is the pinned-artefact id of ARCHITECTURE.md § 6.3:
    module version plus the latest ``valid_from`` of the module's parameter
    files, written as semver build metadata (``"1.0.0+2026-07-01"``). A
    module that declares no parameters has no parameter set (``None``).

    Reads the module's parameter files on the first call per module only
    (cached for the process lifetime; module files do not change under a
    running process). Raises on an unknown module or unreadable parameters —
    the provenance builder wraps it in its never-raise fallback.
    """
    manifest = get_manifest(module_id)
    from app.modules.parameters import load_parameter_rows

    rows = load_parameter_rows(manifest)
    parameter_set = None
    if rows:
        latest = max(row.valid_from for row in rows)
        parameter_set = f"{manifest.version}+{latest.isoformat()}"
    return manifest.id, manifest.version, parameter_set


def provenance_modules(legal_areas: Iterable[str] | None) -> list[str]:
    """Module ids a provenance marker names for a request's area keys.

    Same resolution as the engines use (``request_modules``): empty/absent
    → ``DEFAULT_MODULE``; keys served by the core procedural library add no
    module, so a procedural-only request yields ``[]``.
    """
    return request_modules(list(legal_areas) if legal_areas else None)


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


#: Constraint sentence of the <rechtsstand> block (P-16 wrapper, prompt set
#: 3.0.0): phrased as a rule for choosing the version of the law, never as a
#: statement about the case. Domain-neutral; the module supplies the segment.
_REGIME_CONSTRAINT = (
    "Wende Vorschriften nur in der am Stichtag geltenden Fassung an. Gibt ein Chunk "
    "erkennbar eine andere Fassung wieder oder ist das unklar, kennzeichne das als "
    "Unsicherheit. Dieser Hinweis bestimmt die anzuwendende Fassung; er ist keine "
    "Tatsache des Falls."
)
_SPAN_NOTE = (
    "Der Zeitraum reicht über eine Rechtsstandgrenze; wende für jeden Teilzeitraum "
    "die dort geltende Fassung an."
)
#: Source label when no provider finds a date in the document (F-06 fallback).
NO_REFERENCE_DATE_SOURCE = "kein Datum im Dokument erkannt – heutiges Datum"


def regime_block_for(
    module_ids: list[str], document_text: str, today: date
) -> tuple[dict[str, Any], str]:
    """Regime info and the ``<rechtsstand>`` prompt block (CR-06, F-06).

    The reference date comes from the first provider whose
    ``reference_period`` finds one in *document_text*; otherwise *today*,
    labelled as such. When the document states a period whose end falls in
    another regime, every regime from start to end is named (start and end
    are sampled: one boundary per period, which holds for SGB II's ≤ 12-month
    benefit periods against ≥ 18-month regime segments).

    Returns ``(info, block)``; no provider → ``({}, "")``. *info* is
    ``{"regimes", "as_of", "end", "source"}`` for the audit payload.
    """
    providers = regime_providers_for(module_ids)
    if not providers:
        return {}, ""
    start: date | None = None
    end: date | None = None
    source = NO_REFERENCE_DATE_SOURCE
    for _, provider in providers:
        if provider.reference_period is None:
            continue
        found_start, found_end, found_source = provider.reference_period(document_text)
        if found_start is not None:
            start, end, source = found_start, found_end, found_source
            break
    as_of = start or today
    dates = [as_of, end] if end is not None and end > as_of else [as_of]

    regimes: list[str] = []
    banners: list[str] = []
    for _, provider in providers:
        for day in dates:
            key = provider.regime_for(day)
            banner = provider.banner(key)
            if key not in regimes:
                regimes.append(key)
            if banner and banner not in banners:
                banners.append(banner)
    lines = [f"Stichtag: {as_of:%d.%m.%Y} ({source}).", *banners]
    if len(banners) > len(providers):
        lines.append(_SPAN_NOTE)
    lines.append(_REGIME_CONSTRAINT)
    block = "<rechtsstand>\n" + "\n".join(lines) + "\n</rechtsstand>"
    info = {
        "regimes": regimes,
        "as_of": as_of.isoformat(),
        "end": end.isoformat() if end else None,
        "source": source,
    }
    return info, block


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
    "MODULE_NOT_ENABLED",
    "MODULE_UNKNOWN",
    "ModuleRequestError",
    "ResolvedArea",
    "UnknownAreaKeyError",
    "area_module_binding",
    "calculators_for",
    "compute_deadline",
    "deadline_specs",
    "document_templates",
    "get_manifest",
    "installed_modules",
    "module_provenance",
    "module_registry",
    "parameter_domain",
    "provenance_modules",
    "regime_banner_for",
    "regime_block_for",
    "regime_providers_for",
    "request_modules",
    "resolve_area",
    "resolve_request_areas",
    "resolved_modules",
]
