"""Module registry (WP-91; ARCHITECTURE.md § 3.1).

Discovers ``modules/*/module.yaml``, validates each manifest against
``app/modules/manifest.schema.json`` (core_api 3.2), computes the enabled
set and resolves requested module ids, including legacy aliases (D-038).

Enablement defaults follow D-037: an explicit ``ENABLED_MODULES`` setting
wins; otherwise the tier rule for the current ``DEPLOYMENT_MODE`` applies
(``dev``/``self``: experimental + verified; ``provider``: verified only;
``planned`` and ``community`` are never enabled implicitly).

The registry is pure filesystem + data logic: no DB, no pipeline wiring.
``load_registry_from_settings`` is the startup entry point — an invalid
enabled manifest or a ``DEFAULT_MODULE`` outside the enabled set raises and
therefore refuses startup.
"""

# Semantic Version: 0.3.1 | 2026-11-17 — WP-122: schema core_api 3.2 (`plain_language`).
# 0.3.0 | 2026-11-17 — WP-112: out-of-tree modules from the
# `citizen.modules` entry-point group, clamped to tier `community`; enabled
# out-of-tree code must pass the import lint. Schema core_api 3.1 (WP-110).
# 0.2.0 | 2026-11-16 — WP-93: discovery also refuses manifests
# declaring missing or out-of-directory files (D-042 deferral closed).

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field, replace
from importlib import metadata
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError as _JsonSchemaError

from app.modules import SCHEMA_PATH
from app.modules.sdk import SDK_VERSION

logger = logging.getLogger(__name__)

#: Entry-point group for out-of-tree modules (WP-112, ARCHITECTURE.md § 2.1).
ENTRY_POINT_GROUP = "citizen.modules"

#: Module origins: shipped in this repository vs. installed as a package.
ORIGIN_IN_TREE = "in_tree"
ORIGIN_ENTRY_POINT = "entry_point"

#: Legacy v2.0.0 area keys for modules that are queued but not yet installed
#: (D-038). Once a module ships, its manifest declares the alias itself and
#: that declaration takes precedence; the built-in map only covers the gap.
LEGACY_ALIASES: dict[str, str] = {
    "schenkungsrecht": "erbrecht",
}


class ModuleManifestError(Exception):
    """A discovered ``module.yaml`` is missing, unreadable or schema-invalid."""


class ModuleContractError(Exception):
    """An enabled module's ``core_api`` range excludes the running SDK
    version — the module contract is incompatible with this core."""


class UnknownEnabledModuleError(Exception):
    """``ENABLED_MODULES`` names a module that is not installed."""


class MissingDefaultModuleError(Exception):
    """``DEFAULT_MODULE`` is not in the enabled set (D-037) — startup refuses."""


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ModuleManifest:
    """A validated ``module.yaml``.

    Typed fields cover what the core already consumes; ``raw`` keeps the
    full parsed manifest so later work packages (dossier, goldset,
    compliance) can read their sections without a schema change.
    """

    id: str
    version: str
    core_api: str
    tier: str
    title: dict[str, str]
    legacy_aliases: tuple[str, ...]
    raw: dict[str, Any]
    path: Path  # the module directory
    # WP-112: where the module came from. Out-of-tree modules are loaded at
    # tier `community` at most; `declared_tier` keeps what the manifest said.
    origin: str = ORIGIN_IN_TREE
    distribution: str | None = None  # installing package (entry-point modules)
    declared_tier: str | None = None  # None: equals `tier`


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

_schema_cache: dict[str, Draft202012Validator] = {}


def _schema_validator(core_api: str) -> Draft202012Validator:
    """Return (cached) validator for the manifest schema.

    The shipped schema is core_api 3.2 (a superset of 3.0 and 3.1); the ``core_api``
    argument exists so a future schema set can select by contract version without an API change.
    """
    validator = _schema_cache.get(core_api)
    if validator is None:
        try:
            schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
            Draft202012Validator.check_schema(schema)
            validator = Draft202012Validator(schema)
        except (OSError, json.JSONDecodeError, _JsonSchemaError) as exc:
            raise ModuleManifestError(f"manifest.schema.json is unusable: {exc}") from exc
        _schema_cache[core_api] = validator
    return validator


def _validate_manifest(raw: dict[str, Any], manifest_path: Path) -> None:
    errors = sorted(_schema_validator(SDK_VERSION).iter_errors(raw), key=lambda e: list(e.path))
    if errors:
        details = "; ".join(
            f"{'/'.join(str(p) for p in err.path) or '<root>'}: {err.message}" for err in errors
        )
        raise ModuleManifestError(f"invalid manifest {manifest_path}: {details}")


def _parse_manifest(module_dir: Path, modules_dir: Path) -> ModuleManifest:
    manifest_path = module_dir / "module.yaml"
    if not manifest_path.is_file():
        raise ModuleManifestError(f"missing module.yaml in {module_dir}")
    try:
        raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ModuleManifestError(f"unreadable YAML in {manifest_path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ModuleManifestError(f"manifest {manifest_path} is not a YAML mapping")
    _validate_manifest(raw, manifest_path)

    title = raw["title"]
    manifest = ModuleManifest(
        id=raw["id"],
        version=raw["version"],
        core_api=raw["core_api"],
        tier=raw["tier"],
        title=dict(title),
        legacy_aliases=tuple(raw.get("legacy_aliases", [])),
        raw=raw,
        path=module_dir,
    )
    # WP-93: every file the manifest declares must exist inside the module
    # directory (structural validation deferred from WP-91, D-042).
    from app.modules.content import assert_declared_files_exist

    assert_declared_files_exist(manifest)
    return manifest


# ---------------------------------------------------------------------------
# Discovery + enablement
# ---------------------------------------------------------------------------

# D-037 tier rule: default enablement keyed to DEPLOYMENT_MODE.
_TIER_RULE: dict[str, frozenset[str]] = {
    "dev": frozenset({"experimental", "verified"}),
    "self": frozenset({"experimental", "verified"}),
    "provider": frozenset({"verified"}),
}


def default_modules_root() -> Path:
    """Return the repository's ``modules/`` directory (in-tree modules, § 2.1)."""
    return Path(__file__).resolve().parents[2] / "modules"


def discover_modules(modules_dir: Path) -> dict[str, ModuleManifest]:
    """Discover and validate every installed module.

    Returns a mapping id → manifest. Directories without a ``module.yaml``
    are ignored (staging/scratch). The first invalid manifest aborts
    discovery: the caller (startup) must refuse a partially-known module set.
    Duplicate module ids (two directories declaring the same id) abort too —
    a silent last-one-wins overwrite would make the served module ambiguous.
    """
    modules: dict[str, ModuleManifest] = {}
    if not modules_dir.is_dir():
        return modules
    for module_dir in sorted(modules_dir.iterdir()):
        if not module_dir.is_dir():
            continue
        if not (module_dir / "module.yaml").is_file():
            # Not a module (staging/scratch directory) — skip, don't fail.
            continue
        manifest = _parse_manifest(module_dir, modules_dir)
        if manifest.id in modules:
            raise ModuleManifestError(
                f"duplicate module id {manifest.id!r}: "
                f"{modules[manifest.id].path} and {module_dir}"
            )
        modules[manifest.id] = manifest
    return modules


# ---------------------------------------------------------------------------
# Out-of-tree modules (WP-112)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EntryPointModule:
    """One ``citizen.modules`` entry point: its name, package and loader."""

    name: str
    distribution: str | None
    load: Callable[[], Any]


def _iter_entry_points() -> list[EntryPointModule]:
    """Entry points of the ``citizen.modules`` group (seam for tests)."""
    found: list[EntryPointModule] = []
    for ep in metadata.entry_points(group=ENTRY_POINT_GROUP):
        dist = getattr(ep, "dist", None)
        found.append(EntryPointModule(ep.name, dist.name if dist is not None else None, ep.load))
    return found


def _entry_point_dir(target: Any) -> Path:
    """Module directory an entry point designates.

    Accepted targets: a path (``str``/``PathLike``), an imported Python
    package/module (its directory), or a zero-argument callable returning a
    path. The directory must contain ``module.yaml``.
    """
    if callable(target) and not isinstance(target, type):
        target = target()
    if isinstance(target, str | Path):
        directory = Path(target)
    elif getattr(target, "__file__", None):
        directory = Path(str(target.__file__)).parent
    else:
        raise ModuleManifestError(f"entry point target {target!r} is not a module directory")
    if directory.is_file():
        directory = directory.parent
    if not (directory / "module.yaml").is_file():
        raise ModuleManifestError(f"entry point directory {directory} has no module.yaml")
    return directory.resolve()


def _clamp_tier(tier: str) -> str:
    """Out-of-tree modules are `community` at most (`planned` stays unloadable)."""
    return "planned" if tier == "planned" else "community"


def discover_entry_point_modules(
    entry_points: Iterable[EntryPointModule] | None = None,
) -> tuple[dict[str, ModuleManifest], dict[str, str]]:
    """Discover out-of-tree modules; return ``(modules, rejected)``.

    Unlike in-tree discovery, a broken out-of-tree package does not abort:
    it is rejected (name → reason, logged) because it can never be enabled
    implicitly (tier `community`, D-037). Naming a rejected module in
    ``ENABLED_MODULES`` fails startup as an uninstalled module.
    """
    modules: dict[str, ModuleManifest] = {}
    rejected: dict[str, str] = {}
    for ep in _iter_entry_points() if entry_points is None else entry_points:
        try:
            directory = _entry_point_dir(ep.load())
            manifest = _parse_manifest(directory, directory.parent)
        except Exception as exc:  # any package defect → rejected, never fatal
            rejected[ep.name] = str(exc)
            logger.warning("out-of-tree module %r rejected: %s", ep.name, exc)
            continue
        if manifest.id in modules:
            rejected[ep.name] = f"duplicate module id {manifest.id!r}"
            logger.warning("out-of-tree module %r rejected: duplicate id", ep.name)
            continue
        modules[manifest.id] = replace(
            manifest,
            tier=_clamp_tier(manifest.tier),
            origin=ORIGIN_ENTRY_POINT,
            distribution=ep.distribution,
            declared_tier=manifest.tier,
        )
    return modules, rejected


def discover_installed_modules(
    modules_dir: Path,
    entry_points: Iterable[EntryPointModule] | None = None,
) -> tuple[dict[str, ModuleManifest], dict[str, str]]:
    """In-tree modules plus out-of-tree modules; ``(modules, rejected)``.

    In-tree discovery stays strict (first invalid manifest raises). An
    out-of-tree module whose id an in-tree module already uses is rejected —
    a package must never shadow a reviewed first-party module.
    """
    modules = discover_modules(modules_dir)
    external, rejected = discover_entry_point_modules(entry_points)
    for module_id, manifest in external.items():
        if module_id in modules:
            reason = f"module id {module_id!r} is already used by an in-tree module"
            rejected[manifest.distribution or module_id] = reason
            logger.warning("out-of-tree module rejected: %s", reason)
            continue
        modules[module_id] = manifest
    return modules, rejected


def assert_out_of_tree_code_clean(manifest: ModuleManifest) -> None:
    """Refuse an enabled out-of-tree module whose code imports core internals."""
    if manifest.origin != ORIGIN_ENTRY_POINT:
        return
    from app.modules.lint import lint_module_dir

    violations = lint_module_dir(manifest.path)
    if violations:
        raise ModuleContractError(
            f"out-of-tree module {manifest.id!r} fails the import lint: " + "; ".join(violations)
        )


# ---------------------------------------------------------------------------
# core_api contract compatibility (ARCHITECTURE.md § 6.1)
# ---------------------------------------------------------------------------

_RANGE_TERM = re.compile(r"^(>=|<=|>|<|==|=|~)?(\d+)\.(\d+)(?:\.(\d+))?$")


def _sdk_version_tuple() -> tuple[int, int, int]:
    parts = SDK_VERSION.split(".")
    return (int(parts[0]), int(parts[1]), int(parts[2]) if len(parts) > 2 else 0)


def _satisfies(sdk: tuple[int, int, int], op: str, bound: tuple[int, int, int]) -> bool:
    if op in (">=", "~"):
        return sdk >= bound
    if op == ">":
        return sdk > bound
    if op == "<=":
        return sdk <= bound
    if op == "<":
        return sdk < bound
    return sdk == bound  # "==", "=" or an omitted operator (exact pin)


def assert_core_api_compatible(manifest: ModuleManifest) -> None:
    """Raise ``ModuleContractError`` unless *manifest*'s ``core_api`` range
    admits the running SDK version.

    Range syntax (mirrors the schema pattern): comma-separated comparators
    such as ``">=3.0,<4.0"``, ``">=3.0"`` or an exact pin ``"=3.0"``. An
    unparsable range is a manifest error, never silently compatible.
    """
    sdk = _sdk_version_tuple()
    for term in manifest.core_api.split(","):
        match = _RANGE_TERM.match(term.strip())
        if match is None:
            raise ModuleManifestError(
                f"module {manifest.id!r}: unparsable core_api range {manifest.core_api!r}"
            )
        op = match.group(1) or "="
        bound = (int(match.group(2)), int(match.group(3)), int(match.group(4) or 0))
        if not _satisfies(sdk, op, bound):
            raise ModuleContractError(
                f"module {manifest.id!r} requires core_api {manifest.core_api!r}, "
                f"but this core's module contract is {SDK_VERSION}"
            )


def compute_enabled_set(
    modules: dict[str, ModuleManifest],
    deployment_mode: str,
    enabled_modules: list[str] | None,
) -> frozenset[str]:
    """Compute the enabled set (D-037).

    An explicit ``ENABLED_MODULES`` list wins over the tier rule; ids that
    are not installed raise — an unknown id in the audit-relevant enablement
    list is a configuration error, not a silent no-op.
    """
    if enabled_modules is not None:
        unknown = [mid for mid in enabled_modules if mid not in modules]
        if unknown:
            raise UnknownEnabledModuleError(
                f"ENABLED_MODULES names uninstalled module(s): {', '.join(sorted(unknown))}"
            )
        return frozenset(enabled_modules)

    allowed_tiers = _TIER_RULE.get(deployment_mode)
    if allowed_tiers is None:
        raise UnknownEnabledModuleError(f"unknown DEPLOYMENT_MODE: {deployment_mode!r}")
    return frozenset(mid for mid, manifest in modules.items() if manifest.tier in allowed_tiers)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ModuleResolution:
    """Outcome of resolving a requested module id (explicit or legacy)."""

    requested: str
    module_id: str  # canonical id after alias mapping
    alias_of: str | None  # set when the requested name was a legacy alias
    installed: bool
    enabled: bool


@dataclass(frozen=True)
class ModuleRegistry:
    modules: dict[str, ModuleManifest]
    enabled: frozenset[str]
    default_module: str
    # Alias → canonical id; manifest-declared aliases first, built-ins second.
    aliases: dict[str, str] = field(default_factory=dict)
    # WP-112: out-of-tree entry points that were not loaded (name → reason).
    rejected: dict[str, str] = field(default_factory=dict)

    def is_enabled(self, module_id: str) -> bool:
        return module_id in self.enabled

    def get(self, module_id: str) -> ModuleManifest | None:
        return self.modules.get(module_id)

    def resolve(self, requested: str) -> ModuleResolution:
        """Resolve a requested module id, mapping legacy aliases (D-038)."""
        canonical = self.aliases.get(requested, requested)
        alias_of = requested if canonical != requested else None
        manifest = self.modules.get(canonical)
        return ModuleResolution(
            requested=requested,
            module_id=canonical,
            alias_of=alias_of,
            installed=manifest is not None,
            enabled=canonical in self.enabled,
        )


def load_registry(
    modules_dir: Path,
    deployment_mode: str,
    enabled_modules: list[str] | None,
    default_module: str,
    entry_points: Iterable[EntryPointModule] | None = None,
) -> ModuleRegistry:
    """Discover → validate → enable → resolve (one startup-ready registry)."""
    modules, rejected = discover_installed_modules(modules_dir, entry_points)
    enabled = compute_enabled_set(modules, deployment_mode, enabled_modules)
    for module_id in sorted(enabled):
        assert_core_api_compatible(modules[module_id])
        assert_out_of_tree_code_clean(modules[module_id])
    if default_module not in enabled:
        raise MissingDefaultModuleError(
            f"DEFAULT_MODULE {default_module!r} is not in the enabled set "
            f"(mode={deployment_mode!r}, enabled={sorted(enabled)})"
        )

    aliases: dict[str, str] = {}
    for manifest in modules.values():
        for alias in manifest.legacy_aliases:
            aliases[alias] = manifest.id
    # Built-ins never shadow a manifest-declared alias (D-038).
    for alias, target in LEGACY_ALIASES.items():
        aliases.setdefault(alias, target)

    return ModuleRegistry(
        modules=modules,
        enabled=enabled,
        default_module=default_module,
        aliases=aliases,
        rejected=rejected,
    )


def load_registry_from_settings(modules_dir: Path | None = None) -> ModuleRegistry:
    """Startup entry point: build the registry from the live settings.

    Imported lazily so importing the registry never instantiates Settings
    (tests and the lint import it before configuration exists).
    """
    from app.core.config import settings

    return load_registry(
        modules_dir=modules_dir if modules_dir is not None else default_modules_root(),
        deployment_mode=settings.DEPLOYMENT_MODE,
        enabled_modules=settings.ENABLED_MODULES,
        default_module=settings.DEFAULT_MODULE,
    )
