"""WP-112 (out-of-tree modules) and WP-115 (authoring kit).

WP-112: ``citizen.modules`` entry points are discovered, clamped to tier
``community``, never enabled implicitly, rejected (not fatal) when broken
or shadowing an in-tree id, and refused at startup when enabled with code
that imports core internals. One test discovers a real ``*.dist-info``
entry point through ``importlib.metadata``.

WP-115: the scaffold writes modules that pass the validator as generated
(in-tree and out-of-tree layouts); the validator reports the defects an
author is likely to make; the CLIs exit with their documented codes.
"""

# Semantic Version: 1.0.0 | 2026-11-17 — WP-112, WP-115

from __future__ import annotations

import shutil
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

from app.modules.registry import (
    EntryPointModule,
    ModuleContractError,
    UnknownEnabledModuleError,
    default_modules_root,
    discover_entry_point_modules,
    discover_installed_modules,
    load_registry,
)
from app.modules.scaffold import (
    LAYOUT_OUT_OF_TREE,
    ScaffoldError,
    next_free_order,
    scaffold_module,
    used_area_orders,
)
from app.modules.validate import validate_module_dir

SOZIALRECHT = "sozialrecht"


def _ep_module(tmp_path: Path, module_id: str, **manifest: Any) -> Path:
    """A minimal out-of-tree module directory (scaffolded, then patched)."""
    result = scaffold_module(
        module_id,
        title_de="Extern",
        title_en="External",
        dest=tmp_path,
        layout=LAYOUT_OUT_OF_TREE,
    )
    if manifest:
        path = result.module_dir / "module.yaml"
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        data.update(manifest)
        path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return result.module_dir


def _ep(name: str, target: Any) -> EntryPointModule:
    return EntryPointModule(name=name, distribution=f"dist-{name}", load=lambda: target)


# ---------------------------------------------------------------------------
# WP-112
# ---------------------------------------------------------------------------


class TestEntryPointDiscovery:
    def test_tier_clamped_to_community(self, tmp_path: Path) -> None:
        module_dir = _ep_module(tmp_path, "ext_demo", tier="verified")
        modules, rejected = discover_entry_point_modules([_ep("ext_demo", str(module_dir))])
        manifest = modules["ext_demo"]
        assert rejected == {}
        assert (manifest.tier, manifest.declared_tier) == ("community", "verified")
        assert manifest.origin == "entry_point" and manifest.distribution == "dist-ext_demo"

    def test_planned_stays_planned(self, tmp_path: Path) -> None:
        module_dir = _ep_module(tmp_path, "ext_plan", tier="planned")
        modules, _ = discover_entry_point_modules([_ep("ext_plan", module_dir)])
        assert modules["ext_plan"].tier == "planned"

    def test_target_forms(self, tmp_path: Path) -> None:
        module_dir = _ep_module(tmp_path, "ext_forms")
        package = type(sys)("fake_pkg")
        package.__file__ = str(module_dir / "__init__.py")
        for target in (str(module_dir), module_dir, lambda: module_dir, package):
            modules, rejected = discover_entry_point_modules([_ep("ext_forms", target)])
            assert "ext_forms" in modules, rejected

    def test_broken_package_is_rejected_not_fatal(self, tmp_path: Path) -> None:
        def boom() -> Path:
            raise ImportError("missing dependency")

        good = _ep_module(tmp_path, "ext_good")
        modules, rejected = discover_entry_point_modules(
            [_ep("broken", boom), _ep("nodir", tmp_path / "nothing"), _ep("ext_good", good)]
        )
        assert set(modules) == {"ext_good"}
        assert set(rejected) == {"broken", "nodir"}

    def test_in_tree_id_cannot_be_shadowed(self, tmp_path: Path) -> None:
        module_dir = _ep_module(tmp_path, "ext_shadow", id=SOZIALRECHT)
        modules, rejected = discover_installed_modules(
            default_modules_root(), [_ep("shadow", module_dir)]
        )
        assert modules[SOZIALRECHT].origin == "in_tree"
        assert any("already used by an in-tree module" in r for r in rejected.values())


class TestEnablement:
    def _registry(self, tmp_path: Path, mode: str, enabled: list[str] | None) -> Any:
        module_dir = _ep_module(tmp_path, "ext_enable", tier="verified")
        return load_registry(
            default_modules_root(), mode, enabled, [_ep("ext_enable", module_dir)]
        )

    @pytest.mark.parametrize("mode", ["dev", "self", "provider"])
    def test_never_enabled_implicitly(self, tmp_path: Path, mode: str) -> None:
        registry = self._registry(tmp_path, mode, None)
        assert "ext_enable" in registry.modules and not registry.is_enabled("ext_enable")

    def test_enabled_when_listed_even_in_provider(self, tmp_path: Path) -> None:
        registry = self._registry(tmp_path, "provider", [SOZIALRECHT, "ext_enable"])
        assert registry.is_enabled("ext_enable")

    def test_rejected_module_cannot_be_enabled(self) -> None:
        def boom() -> Path:
            raise ImportError("x")

        with pytest.raises(UnknownEnabledModuleError):
            load_registry(
                default_modules_root(),
                "dev",
                [SOZIALRECHT, "ext_broken"],
                [_ep("ext_broken", boom)],
            )

    def test_enabled_code_must_pass_import_lint(self, tmp_path: Path) -> None:
        module_dir = _ep_module(tmp_path, "ext_lint")
        (module_dir / "helper.py").write_text("from app.core.config import settings\n")
        eps = [_ep("ext_lint", module_dir)]
        # Installed but disabled: tolerated (never imported).
        load_registry(default_modules_root(), "dev", None, eps)
        with pytest.raises(ModuleContractError, match="import lint"):
            load_registry(default_modules_root(), "dev", [SOZIALRECHT, "ext_lint"], eps)


def test_real_entry_point_via_dist_info(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Discovery through importlib.metadata, as for a pip-installed package."""
    result = scaffold_module(
        "ext_dist",
        title_de="Extern",
        title_en="External",
        dest=tmp_path,
        layout=LAYOUT_OUT_OF_TREE,
    )
    assert result.package_dir is not None
    dist_info = result.package_dir / "citizen_module_ext_dist-0.1.0.dist-info"
    dist_info.mkdir()
    (dist_info / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: citizen-module-ext-dist\nVersion: 0.1.0\n"
    )
    (dist_info / "entry_points.txt").write_text(
        "[citizen.modules]\next_dist = citizen_module_ext_dist\n"
    )
    monkeypatch.syspath_prepend(str(result.package_dir))
    modules, rejected = discover_entry_point_modules()
    assert "ext_dist" in modules, rejected
    assert modules["ext_dist"].distribution == "citizen-module-ext-dist"
    assert modules["ext_dist"].path == result.module_dir.resolve()


# ---------------------------------------------------------------------------
# WP-115
# ---------------------------------------------------------------------------


@pytest.fixture
def modules_copy(tmp_path: Path) -> Path:
    root = tmp_path / "modules"
    shutil.copytree(default_modules_root(), root)
    return root


class TestScaffold:
    def test_in_tree_scaffold_validates(self, modules_copy: Path) -> None:
        result = scaffold_module(
            "demo_neu",
            title_de="Demo",
            title_en="Demo",
            dest=modules_copy,
            modules_root=modules_copy,
        )
        report = validate_module_dir(result.module_dir, modules_copy)
        assert report.ok, report.errors
        assert (report.tier, report.version) == ("experimental", "0.1.0")
        manifest = yaml.safe_load((result.module_dir / "module.yaml").read_text())
        intake = yaml.safe_load((result.module_dir / "intake.yaml").read_text())
        assert intake["areas"]["demo_neu"]["order"] == next_free_order(
            used_area_orders(modules_copy) - {intake["areas"]["demo_neu"]["order"]}
        )
        assert manifest["scope"]["own_matter_only"] is True

    def test_out_of_tree_scaffold_validates(self, tmp_path: Path) -> None:
        result = scaffold_module(
            "demo_ext", title_de="E", title_en="E", dest=tmp_path, layout=LAYOUT_OUT_OF_TREE
        )
        assert result.package_dir is not None
        assert (result.package_dir / "pyproject.toml").is_file()
        report = validate_module_dir(result.module_dir)
        assert report.ok, report.errors
        assert report.tier == "community"

    def test_refusals(self, tmp_path: Path) -> None:
        with pytest.raises(ScaffoldError, match="invalid module id"):
            scaffold_module("Bad-Id", title_de="x", title_en="x", dest=tmp_path)
        scaffold_module("demo_once", title_de="x", title_en="x", dest=tmp_path)
        with pytest.raises(ScaffoldError, match="already exists"):
            scaffold_module("demo_once", title_de="x", title_en="x", dest=tmp_path)

    def test_next_free_order(self) -> None:
        assert next_free_order(set()) == 10
        assert next_free_order({10, 35, 80}) == 90


class TestValidator:
    def _scaffold(self, root: Path, module_id: str = "demo_val") -> Path:
        return scaffold_module(
            module_id, title_de="D", title_en="D", dest=root, modules_root=root
        ).module_dir

    def _patch(self, module_dir: Path, **changes: Any) -> None:
        path = module_dir / "module.yaml"
        data = yaml.safe_load(path.read_text())
        data.update(changes)
        path.write_text(yaml.safe_dump(data, allow_unicode=True))

    def _errors(self, module_dir: Path, root: Path) -> str:
        report = validate_module_dir(module_dir, root)
        assert not report.ok
        return " | ".join(report.errors)

    def test_own_matter_only_required(self, modules_copy: Path) -> None:
        module_dir = self._scaffold(modules_copy)
        self._patch(module_dir, scope={"summary_de": "x", "own_matter_only": False})
        assert "own_matter_only" in self._errors(module_dir, modules_copy)

    def test_verified_requires_goldset(self, modules_copy: Path) -> None:
        module_dir = self._scaffold(modules_copy)
        data = yaml.safe_load((module_dir / "module.yaml").read_text())
        data.pop("goldset")
        data["tier"] = "verified"
        (module_dir / "module.yaml").write_text(yaml.safe_dump(data))
        assert "requires a goldset" in self._errors(module_dir, modules_copy)

    def test_core_import_and_changelog_and_order(self, modules_copy: Path) -> None:
        module_dir = self._scaffold(modules_copy)
        (module_dir / "x.py").write_text("import app.services.corpus\n")
        self._patch(module_dir, version="0.2.0")
        intake = module_dir / "intake.yaml"
        text = intake.read_text()
        current = yaml.safe_load(text)["areas"]["demo_val"]["order"]
        intake.write_text(text.replace(f"order: {current}", "order: 10"))
        errors = self._errors(module_dir, modules_copy)
        assert "only app.modules.sdk is allowed" in errors
        assert "newest CHANGELOG.md entry is 0.1.0" in errors
        assert "duplicate area-key `order`" in errors

    def test_bad_deadline_spec_and_parameters(self, modules_copy: Path) -> None:
        module_dir = self._scaffold(modules_copy)
        (module_dir / "fristen.yaml").write_text("- id: x\n")
        params = next((module_dir / "parameters").glob("*.yaml"))
        params.write_text(
            params.read_text().replace("review_status: proposed", "review_status: maybe")
        )
        errors = self._errors(module_dir, modules_copy)
        assert errors.count("fristen") and "review_status" in errors

    def test_invalid_manifest_stops_early(self, tmp_path: Path) -> None:
        (tmp_path / "broken").mkdir()
        (tmp_path / "broken" / "module.yaml").write_text("id: Broken\n")
        report = validate_module_dir(tmp_path / "broken")
        assert report.module_id is None and report.errors[0].startswith("manifest:")


@pytest.mark.parametrize("module_dir", sorted(p for p in default_modules_root().iterdir()))
def test_in_tree_modules_validate(module_dir: Path) -> None:
    """Guard: every shipped module passes the authoring-kit validator."""
    report = validate_module_dir(module_dir)
    assert report.ok, report.errors


def test_cli_exit_codes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from scripts.new_module import main as new_module
    from scripts.validate_module import main as validate

    assert validate(["--module", SOZIALRECHT]) == 0
    assert validate(["--module", "nope_mod"]) == 2
    assert validate([]) == 2
    assert (
        new_module(
            ["demo_cli", "--title-de", "D", "--title-en", "D", "--out-of-tree", str(tmp_path)]
        )
        == 0
    )
    assert (
        new_module(
            ["demo_cli", "--title-de", "D", "--title-en", "D", "--out-of-tree", str(tmp_path)]
        )
        == 2
    )
    package = tmp_path / "citizen-module-demo-cli" / "citizen_module_demo_cli"
    assert validate([str(package), "--json"]) == 0
    assert '"ok": true' in capsys.readouterr().out
