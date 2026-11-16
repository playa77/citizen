"""Unit tests for the module registry (WP-91).

Covers discovery of ``modules/*/module.yaml``, manifest validation, the
enablement rule of D-037 for each ``DEPLOYMENT_MODE``, legacy alias
resolution (D-038) and the missing-default-module startup refusal.

All fixtures are built in temporary directories so the tests never depend
on the state of the repository's own ``modules/`` tree (except the lint
test, which scans the real tree).

No mocking required — the registry is pure filesystem + data logic.
"""

# Semantic Version: 0.1.0

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from app.modules.registry import (
    LEGACY_ALIASES,
    MissingDefaultModuleError,
    ModuleManifestError,
    UnknownEnabledModuleError,
    discover_modules,
    load_registry,
    load_registry_from_settings,
)

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

_VALID_MANIFEST: dict[str, Any] = {
    "id": "sozialrecht",
    "version": "1.0.0",
    "core_api": ">=3.0,<4.0",
    "title": {"de": "Sozialrecht", "en": "Social-benefits law"},
    "tier": "verified",
}


def _write_module(
    root: Path,
    module_id: str,
    overrides: dict[str, Any] | None = None,
) -> Path:
    """Write a valid module manifest (optionally overridden) into ``root``."""
    module_dir = root / module_id
    module_dir.mkdir(parents=True, exist_ok=True)
    manifest = {**_VALID_MANIFEST, "id": module_id, **(overrides or {})}
    # Invalid-manifest fixtures may deliberately drop required fields or add
    # unknown ones — dict merge above keeps that possible.
    (module_dir / "module.yaml").write_text(
        yaml.safe_dump(manifest, allow_unicode=True), encoding="utf-8"
    )
    return module_dir


def _write_raw_module(root: Path, module_id: str, raw: str) -> Path:
    """Write a manifest from raw YAML text (for malformed-file fixtures)."""
    module_dir = root / module_id
    module_dir.mkdir(parents=True, exist_ok=True)
    (module_dir / "module.yaml").write_text(raw, encoding="utf-8")
    return module_dir


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


class TestDiscovery:
    def test_discovers_installed_manifests(self, tmp_path: Path) -> None:
        _write_module(tmp_path, "sozialrecht")
        _write_module(
            tmp_path,
            "erbrecht",
            {"tier": "experimental", "legacy_aliases": ["schenkungsrecht"]},
        )
        dirs_without_manifest = tmp_path / "_scratch"
        dirs_without_manifest.mkdir()

        modules = discover_modules(tmp_path)

        assert set(modules) == {"sozialrecht", "erbrecht"}
        assert modules["sozialrecht"].tier == "verified"
        assert modules["sozialrecht"].version == "1.0.0"
        assert modules["erbrecht"].legacy_aliases == ("schenkungsrecht",)

    def test_empty_modules_dir_discovers_nothing(self, tmp_path: Path) -> None:
        assert discover_modules(tmp_path) == {}

    def test_missing_modules_dir_discovers_nothing(self, tmp_path: Path) -> None:
        assert discover_modules(tmp_path / "does-not-exist") == {}


# ---------------------------------------------------------------------------
# Manifest validation
# ---------------------------------------------------------------------------


class TestManifestValidation:
    def test_invalid_tier_raises(self, tmp_path: Path) -> None:
        _write_module(tmp_path, "sozialrecht", {"tier": "gold"})
        with pytest.raises(ModuleManifestError):
            discover_modules(tmp_path)

    def test_missing_required_field_raises(self, tmp_path: Path) -> None:
        broken = {k: v for k, v in _VALID_MANIFEST.items() if k != "version"}
        # Write directly: _write_module's dict-merge would re-add defaults.
        _write_raw_module(tmp_path, "sozialrecht", yaml.safe_dump(broken))
        with pytest.raises(ModuleManifestError):
            discover_modules(tmp_path)

    def test_unknown_field_raises(self, tmp_path: Path) -> None:
        _write_module(tmp_path, "sozialrecht", {"unknown_extra": 1})
        with pytest.raises(ModuleManifestError):
            discover_modules(tmp_path)

    def test_bad_semver_raises(self, tmp_path: Path) -> None:
        _write_module(tmp_path, "sozialrecht", {"version": "1.0"})
        with pytest.raises(ModuleManifestError):
            discover_modules(tmp_path)

    def test_malformed_yaml_raises(self, tmp_path: Path) -> None:
        _write_raw_module(tmp_path, "sozialrecht", "id: [unclosed\n  - oops")
        with pytest.raises(ModuleManifestError):
            discover_modules(tmp_path)

    def test_error_message_names_the_module(self, tmp_path: Path) -> None:
        _write_module(tmp_path, "sozialrecht", {"tier": "gold"})
        with pytest.raises(ModuleManifestError) as excinfo:
            discover_modules(tmp_path)
        assert "sozialrecht" in str(excinfo.value)


# ---------------------------------------------------------------------------
# Enablement (D-037 tier rule per DEPLOYMENT_MODE)
# ---------------------------------------------------------------------------


class TestEnablement:
    @pytest.fixture()
    def mixed_modules(self, tmp_path: Path) -> dict[str, Path]:
        _write_module(tmp_path, "verified_mod", {"id": "verified_mod", "tier": "verified"})
        _write_module(
            tmp_path, "experimental_mod", {"id": "experimental_mod", "tier": "experimental"}
        )
        _write_module(tmp_path, "planned_mod", {"id": "planned_mod", "tier": "planned"})
        _write_module(tmp_path, "community_mod", {"id": "community_mod", "tier": "community"})
        return {"root": tmp_path}

    def test_dev_enables_experimental_and_verified(self, mixed_modules: dict[str, Path]) -> None:
        registry = load_registry(
            modules_dir=mixed_modules["root"],
            deployment_mode="dev",
            enabled_modules=None,
            default_module="verified_mod",
        )
        assert registry.is_enabled("verified_mod")
        assert registry.is_enabled("experimental_mod")
        assert not registry.is_enabled("planned_mod")
        assert not registry.is_enabled("community_mod")

    def test_self_enables_experimental_and_verified(self, mixed_modules: dict[str, Path]) -> None:
        registry = load_registry(
            modules_dir=mixed_modules["root"],
            deployment_mode="self",
            enabled_modules=None,
            default_module="verified_mod",
        )
        assert registry.is_enabled("verified_mod")
        assert registry.is_enabled("experimental_mod")
        assert not registry.is_enabled("planned_mod")
        assert not registry.is_enabled("community_mod")

    def test_provider_enables_only_verified(self, mixed_modules: dict[str, Path]) -> None:
        registry = load_registry(
            modules_dir=mixed_modules["root"],
            deployment_mode="provider",
            enabled_modules=None,
            default_module="verified_mod",
        )
        assert registry.is_enabled("verified_mod")
        assert not registry.is_enabled("experimental_mod")
        assert not registry.is_enabled("planned_mod")
        assert not registry.is_enabled("community_mod")

    def test_explicit_enabled_modules_override_tier_rule(
        self, mixed_modules: dict[str, Path]
    ) -> None:
        registry = load_registry(
            modules_dir=mixed_modules["root"],
            deployment_mode="provider",
            enabled_modules=["experimental_mod", "verified_mod"],
            default_module="verified_mod",
        )
        assert registry.is_enabled("experimental_mod")
        assert registry.is_enabled("verified_mod")
        assert not registry.is_enabled("planned_mod")

    def test_enabled_module_must_be_installed(self, mixed_modules: dict[str, Path]) -> None:
        with pytest.raises(UnknownEnabledModuleError):
            load_registry(
                modules_dir=mixed_modules["root"],
                deployment_mode="dev",
                enabled_modules=["nicht_installiert"],
                default_module="verified_mod",
            )


# ---------------------------------------------------------------------------
# Default module
# ---------------------------------------------------------------------------


class TestDefaultModule:
    def test_default_module_not_enabled_refuses_startup(self, tmp_path: Path) -> None:
        _write_module(tmp_path, "sozialrecht", {"tier": "experimental"})
        with pytest.raises(MissingDefaultModuleError):
            load_registry(
                modules_dir=tmp_path,
                deployment_mode="provider",  # experimental is not enabled here
                enabled_modules=None,
                default_module="sozialrecht",
            )

    def test_default_module_missing_entirely_refuses_startup(self, tmp_path: Path) -> None:
        _write_module(tmp_path, "anderes_recht", {"id": "anderes_recht", "tier": "verified"})
        with pytest.raises(MissingDefaultModuleError):
            load_registry(
                modules_dir=tmp_path,
                deployment_mode="dev",
                enabled_modules=None,
                default_module="sozialrecht",
            )

    def test_default_module_enabled_passes(self, tmp_path: Path) -> None:
        _write_module(tmp_path, "sozialrecht")
        registry = load_registry(
            modules_dir=tmp_path,
            deployment_mode="provider",
            enabled_modules=None,
            default_module="sozialrecht",
        )
        assert registry.default_module == "sozialrecht"


# ---------------------------------------------------------------------------
# Legacy alias resolution (D-038)
# ---------------------------------------------------------------------------


class TestAliasResolution:
    def test_builtin_alias_schenkungsrecht_to_erbrecht(self) -> None:
        assert LEGACY_ALIASES["schenkungsrecht"] == "erbrecht"

    def test_resolve_alias_to_canonical_id(self, tmp_path: Path) -> None:
        # erbrecht is installed and declares the legacy alias itself.
        _write_module(
            tmp_path, "erbrecht", {"tier": "verified", "legacy_aliases": ["schenkungsrecht"]}
        )
        registry = load_registry(
            modules_dir=tmp_path,
            deployment_mode="dev",
            enabled_modules=None,
            default_module="erbrecht",
        )
        resolution = registry.resolve("schenkungsrecht")
        assert resolution.module_id == "erbrecht"
        assert resolution.alias_of == "schenkungsrecht"
        assert resolution.installed
        assert resolution.enabled

    def test_builtin_alias_resolves_even_when_target_not_installed(
        self, tmp_path: Path
    ) -> None:
        _write_module(tmp_path, "sozialrecht")
        registry = load_registry(
            modules_dir=tmp_path,
            deployment_mode="dev",
            enabled_modules=None,
            default_module="sozialrecht",
        )
        # erbrecht is queued (WP-138) but not installed; the alias still
        # maps to the canonical id and reports it as not installed.
        resolution = registry.resolve("schenkungsrecht")
        assert resolution.module_id == "erbrecht"
        assert resolution.alias_of == "schenkungsrecht"
        assert not resolution.installed

    def test_direct_id_resolves_to_itself(self, tmp_path: Path) -> None:
        _write_module(tmp_path, "sozialrecht")
        registry = load_registry(
            modules_dir=tmp_path,
            deployment_mode="dev",
            enabled_modules=None,
            default_module="sozialrecht",
        )
        resolution = registry.resolve("sozialrecht")
        assert resolution.module_id == "sozialrecht"
        assert resolution.alias_of is None
        assert resolution.installed
        assert resolution.enabled

    def test_unknown_id_resolves_not_installed(self, tmp_path: Path) -> None:
        _write_module(tmp_path, "sozialrecht")
        registry = load_registry(
            modules_dir=tmp_path,
            deployment_mode="dev",
            enabled_modules=None,
            default_module="sozialrecht",
        )
        resolution = registry.resolve("quantenrecht")
        assert resolution.module_id == "quantenrecht"
        assert resolution.alias_of is None
        assert not resolution.installed
        assert not resolution.enabled


class TestCoreApiCompatibility:
    """An enabled module whose core_api range excludes the running SDK
    version must refuse startup (ARCHITECTURE.md § 6.1) — the contract
    field exists to prevent exactly this breach."""

    def _load(self, tmp_path: Path, core_api: str) -> object:
        _write_module(tmp_path, "sozialrecht", {"core_api": core_api})
        return load_registry(
            modules_dir=tmp_path,
            deployment_mode="dev",
            enabled_modules=None,
            default_module="sozialrecht",
        )

    def test_compatible_range_loads(self, tmp_path: Path) -> None:
        registry = self._load(tmp_path, ">=3.0,<4.0")
        assert registry.is_enabled("sozialrecht")

    def test_open_ended_compatible_range_loads(self, tmp_path: Path) -> None:
        registry = self._load(tmp_path, ">=3.0")
        assert registry.is_enabled("sozialrecht")

    def test_incompatible_major_refuses(self, tmp_path: Path) -> None:
        from app.modules.registry import ModuleContractError

        with pytest.raises(ModuleContractError):
            self._load(tmp_path, ">=4.0,<5.0")

    def test_incompatible_exact_pin_refuses(self, tmp_path: Path) -> None:
        from app.modules.registry import ModuleContractError

        with pytest.raises(ModuleContractError):
            self._load(tmp_path, "=2.0")

    def test_upper_bound_below_sdk_refuses(self, tmp_path: Path) -> None:
        from app.modules.registry import ModuleContractError

        with pytest.raises(ModuleContractError):
            self._load(tmp_path, ">=2.0,<3.0")


class TestDuplicateModuleId:
    def test_duplicate_ids_refuse(self, tmp_path: Path) -> None:
        _write_module(tmp_path, "sozialrecht")
        _write_module(tmp_path, "sozialrecht_kopie", {"id": "sozialrecht"})
        with pytest.raises(ModuleManifestError):
            discover_modules(tmp_path)


# ---------------------------------------------------------------------------
# Settings-based loading (startup path)
# ---------------------------------------------------------------------------


class TestLoadFromSettings:
    def test_loads_from_current_settings(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.core.config import settings

        _write_module(tmp_path, "sozialrecht")
        monkeypatch.setattr(settings, "DEPLOYMENT_MODE", "dev")
        monkeypatch.setattr(settings, "ENABLED_MODULES", None)
        monkeypatch.setattr(settings, "DEFAULT_MODULE", "sozialrecht")

        registry = load_registry_from_settings(modules_dir=tmp_path)
        assert registry.is_enabled("sozialrecht")
        assert registry.default_module == "sozialrecht"

    def test_startup_refuses_unknown_enabled_module(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.core.config import settings

        _write_module(tmp_path, "sozialrecht")
        monkeypatch.setattr(settings, "DEPLOYMENT_MODE", "dev")
        monkeypatch.setattr(settings, "ENABLED_MODULES", ["nichtda"])
        monkeypatch.setattr(settings, "DEFAULT_MODULE", "sozialrecht")

        with pytest.raises(UnknownEnabledModuleError):
            load_registry_from_settings(modules_dir=tmp_path)


# ---------------------------------------------------------------------------
# Module lint: module code may import only app.modules.sdk
# ---------------------------------------------------------------------------


class TestModuleImportLint:
    def _lint(self, modules_dir: Path) -> list[str]:
        from app.modules.lint import lint_module_imports

        return lint_module_imports(modules_dir)

    def test_rejects_non_sdk_app_import(self, tmp_path: Path) -> None:
        module_dir = _write_module(tmp_path, "sozialrecht")
        (module_dir / "calculators.py").write_text(
            "from app.services.rules_engine import Regelbedarf\n", encoding="utf-8"
        )
        violations = self._lint(tmp_path)
        assert any("sozialrecht" in v and "calculators.py" in v for v in violations)

    def test_rejects_relative_app_import(self, tmp_path: Path) -> None:
        module_dir = _write_module(tmp_path, "sozialrecht")
        (module_dir / "calc.py").write_text("import app.core.config\n", encoding="utf-8")
        violations = self._lint(tmp_path)
        assert violations

    def test_allows_sdk_import_and_stdlib(self, tmp_path: Path) -> None:
        module_dir = _write_module(tmp_path, "sozialrecht")
        (module_dir / "calculators.py").write_text(
            "import calendar\nfrom datetime import date\n\n"
            "from app.modules.sdk import SDK_VERSION\n\n"
            "def f() -> int:\n    return SDK_VERSION.count('.')\n",
            encoding="utf-8",
        )
        assert self._lint(tmp_path) == []

    def test_modules_without_code_pass(self, tmp_path: Path) -> None:
        _write_module(tmp_path, "sozialrecht")
        assert self._lint(tmp_path) == []

    def test_repository_module_tree_passes_lint(self) -> None:
        from app.modules.registry import default_modules_root

        violations = self._lint(default_modules_root())
        assert violations == [], f"module import violations: {violations}"


# ---------------------------------------------------------------------------
# Manifest schema artefact
# ---------------------------------------------------------------------------


class TestManifestSchema:
    def test_schema_is_valid_json_and_versioned_with_core_api_3(self) -> None:
        from app.modules import SCHEMA_PATH

        data = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        assert data.get("x-core-api") == "3.0"
        assert "id" in data["properties"]
