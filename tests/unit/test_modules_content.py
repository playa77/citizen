"""Module content layer (WP-93): loader, area tables, runtime, parameters, exit criterion.

Behaviour identity with v2.0.0 is pinned by ``test_wp93_golden.py``; this
file covers the contracts and invariants of the new layer itself.
"""

# Semantic Version: 1.0.0

from __future__ import annotations

import ast
import re
from datetime import date
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
import yaml

from app.db.models import LEGAL_AREA_ALLOWED
from app.modules.areas import PROCEDURAL_OWNER, area_tables
from app.modules.content import (
    assert_declared_files_exist,
    import_module_file,
    load_code_ref,
    module_path,
)
from app.modules.parameters import load_parameter_rows
from app.modules.registry import (
    ModuleManifestError,
    default_modules_root,
    discover_modules,
    load_registry,
)
from app.modules.runtime import (
    calculators_for,
    compute_deadline,
    get_manifest,
    regime_banner_for,
    request_modules,
)

_REPO = Path(__file__).resolve().parents[2]
_STUBS = (
    "erbrecht",
    "familienrecht",
    "mietrecht",
    "arbeitsrecht",
    "vertragsrecht",
    "strafrecht",
    "andere",
)


def _module(tmp_path: Path, module_id: str, extra: dict[str, Any]) -> Path:
    module_dir = tmp_path / module_id
    module_dir.mkdir(parents=True)
    manifest = {
        "id": module_id,
        "version": "0.1.0",
        "core_api": ">=3.0,<4.0",
        "title": {"de": "T", "en": "T"},
        "tier": "experimental",
        **extra,
    }
    (module_dir / "module.yaml").write_text(yaml.safe_dump(manifest), encoding="utf-8")
    return module_dir


# ---------------------------------------------------------------------------
# Installed modules (D-038 legacy areas)
# ---------------------------------------------------------------------------


class TestInstalledModules:
    def test_sozialrecht_plus_seven_stubs(self) -> None:
        modules = discover_modules(default_modules_root())
        assert set(modules) == {"sozialrecht", *_STUBS}
        assert modules["sozialrecht"].tier == "verified"

    @pytest.mark.parametrize("module_id", _STUBS)
    def test_stub_is_experimental_and_engine_less(self, module_id: str) -> None:
        raw = get_manifest(module_id).raw
        assert raw["tier"] == "experimental"
        for engine in ("calculators", "regimes", "fristen", "document_templates", "goldset"):
            assert engine not in raw, f"stub {module_id} must not ship {engine}"

    def test_every_declared_file_exists(self) -> None:
        for manifest in discover_modules(default_modules_root()).values():
            assert_declared_files_exist(manifest)

    def test_provider_mode_enables_only_verified(self) -> None:
        registry = load_registry(default_modules_root(), "provider", None, "sozialrecht")
        assert registry.enabled == frozenset({"sozialrecht"})

    def test_dev_mode_enables_stubs(self) -> None:
        registry = load_registry(default_modules_root(), "dev", None, "sozialrecht")
        assert registry.enabled == frozenset({"sozialrecht", *_STUBS})

    def test_schenkungsrecht_alias_declared_by_erbrecht(self) -> None:
        registry = load_registry(default_modules_root(), "dev", None, "sozialrecht")
        resolution = registry.resolve("schenkungsrecht")
        assert resolution.module_id == "erbrecht"
        assert resolution.installed and resolution.enabled


# ---------------------------------------------------------------------------
# Area tables
# ---------------------------------------------------------------------------


class TestAreaTables:
    def test_keys_follow_db_enum(self) -> None:
        assert area_tables().keys == tuple(LEGAL_AREA_ALLOWED)

    def test_every_key_has_one_owner(self) -> None:
        owner = area_tables().owner
        assert set(owner) == set(LEGAL_AREA_ALLOWED)
        assert owner["schenkungsrecht"] == "erbrecht"
        assert owner["verwaltungsrecht"] == PROCEDURAL_OWNER
        assert owner["sozialrecht"] == "sozialrecht"

    def test_catch_all_and_fallback_preset(self) -> None:
        tables = area_tables()
        assert tables.catch_all == "andere"
        assert tables.fallback_preset == "sozialrecht-allgemein"
        # default module's keyword fallback is evaluated last (v2.0.0 tie-break)
        assert tables.preset_fallback[-1].preset_id == "sozialrecht-allgemein"

    def test_familienrecht_inherits_erbrecht_profile(self) -> None:
        profiles = area_tables().prompt_profiles
        assert profiles["familienrecht"] == profiles["erbrecht"]
        assert profiles["familienrecht"]["key"] == "erbrecht"
        assert "mietrecht" not in profiles

    def test_duplicate_owner_is_rejected(self, tmp_path: Path) -> None:
        # a module claiming a key the procedural library already serves
        import shutil

        for mid in ("sozialrecht", *_STUBS):
            shutil.copytree(default_modules_root() / mid, tmp_path / mid)
        raw = yaml.safe_load((tmp_path / "andere" / "module.yaml").read_text(encoding="utf-8"))
        raw["legacy_aliases"] = ["verwaltungsrecht"]
        (tmp_path / "andere" / "module.yaml").write_text(yaml.safe_dump(raw), encoding="utf-8")
        from app.modules.areas import build_area_tables

        with pytest.raises(ModuleManifestError, match="exactly one owner"):
            build_area_tables(tmp_path, "sozialrecht")


# ---------------------------------------------------------------------------
# Content loader safety
# ---------------------------------------------------------------------------


class TestContentLoader:
    def test_missing_declared_file_refuses_discovery(self, tmp_path: Path) -> None:
        _module(tmp_path, "demo", {"corpus": "corpus.yaml"})
        with pytest.raises(ModuleManifestError, match="missing file"):
            discover_modules(tmp_path)

    def test_path_escape_is_rejected(self, tmp_path: Path) -> None:
        (tmp_path / "outside.yaml").write_text("{}", encoding="utf-8")
        _module(tmp_path, "demo", {"corpus": "../outside.yaml"})
        with pytest.raises(ModuleManifestError, match="leaves the module directory"):
            discover_modules(tmp_path)

    def test_code_is_imported_under_synthetic_package(self, tmp_path: Path) -> None:
        module_dir = _module(tmp_path, "demo_code", {"calculators": "calc:CALCULATORS"})
        (module_dir / "helper.py").write_text("VALUE = 41\n", encoding="utf-8")
        (module_dir / "calc.py").write_text(
            "from .helper import VALUE\nCALCULATORS = (VALUE + 1,)\n", encoding="utf-8"
        )
        manifest = discover_modules(tmp_path)["demo_code"]
        assert load_code_ref(manifest, "calc:CALCULATORS") == (42,)
        assert import_module_file(manifest, "calc").__name__ == "citizen_modules.demo_code.calc"

    def test_malformed_code_ref(self, tmp_path: Path) -> None:
        module_dir = _module(tmp_path, "demo_ref", {})
        (module_dir / "calc.py").write_text("X = 1\n", encoding="utf-8")
        manifest = discover_modules(tmp_path)["demo_ref"]
        with pytest.raises(ModuleManifestError, match="file:ATTRIBUTE"):
            load_code_ref(manifest, "calc")
        with pytest.raises(ModuleManifestError, match="no attribute"):
            load_code_ref(manifest, "calc:MISSING")

    def test_module_path_stays_inside(self) -> None:
        manifest = get_manifest("sozialrecht")
        with pytest.raises(ModuleManifestError):
            module_path(manifest, "../../app/main.py")


# ---------------------------------------------------------------------------
# Runtime resolution
# ---------------------------------------------------------------------------


class TestRuntime:
    def test_request_modules(self) -> None:
        assert request_modules(None) == ["sozialrecht"]
        assert request_modules([]) == ["sozialrecht"]
        assert request_modules(["schenkungsrecht", "erbrecht"]) == ["erbrecht"]
        assert request_modules(["verwaltungsrecht"]) == []
        assert request_modules(["mietrecht", "sozialrecht", "nope"]) == ["mietrecht", "sozialrecht"]

    def test_only_sozialrecht_ships_engines(self) -> None:
        assert [mid for mid, _ in calculators_for(["sozialrecht", *_STUBS])] == ["sozialrecht"]

    def test_regime_banner(self) -> None:
        from citizen_modules.sozialrecht.regime import legal_regime, regime_banner

        day = date(2026, 7, 1)
        regime, banner = regime_banner_for(["sozialrecht"], day)
        assert regime == legal_regime(day)
        assert banner == regime_banner(regime)
        assert regime_banner_for(["erbrecht"], day) == (None, "")

    def test_compute_deadline(self) -> None:
        from app.fristen.evaluator import FristInput

        result = compute_deadline(
            "sozialrecht", "widerspruch_sgg_84", FristInput(bescheid_datum=date(2025, 5, 14))
        )
        assert result.module_id == "sozialrecht"
        assert result.spec_id == "widerspruch_sgg_84"

    @pytest.mark.parametrize("areas", [["erbrecht"], ["verwaltungsrecht"], ["andere"]])
    async def test_no_calculator_means_no_llm_call(self, areas: list[str]) -> None:
        from app.services.calculation import check_calculations

        with patch("app.services.calculation._llm_extract", new=AsyncMock()) as extract:
            result = await check_calculations("Text", module_ids=request_modules(areas))
        extract.assert_not_called()
        assert result["calculations_found"] == []
        assert "keine deterministische" in result["overall_assessment"]["summary"]


# ---------------------------------------------------------------------------
# Parameters
# ---------------------------------------------------------------------------


class TestParameters:
    def test_sozialrecht_rows(self) -> None:
        rows = load_parameter_rows(get_manifest("sozialrecht"))
        assert len(rows) == 27
        assert {row.domain for row in rows} == {"sgb2"}
        top = next(r for r in rows if r.key == "sgb2.par11b.income_bracket_4_pct")
        assert top.value_json is not None and top.value_json["max_income"] == 10_000_000.0

    def test_stubs_have_no_parameters(self) -> None:
        for module_id in _STUBS:
            assert load_parameter_rows(get_manifest(module_id)) == []

    @pytest.mark.parametrize(
        ("entry", "message"),
        [
            ({"key": "k", "valid_from": "2025-01-01", "review_status": "verified"}, "ISO dates"),
            ({"key": "k", "valid_from": date(2025, 1, 1), "review_status": "draft"}, "review_status"),
            ({"key": "k", "valid_from": date(2025, 1, 1), "review_status": "verified", "x": 1}, "unknown"),
        ],
    )
    def test_invalid_rows(self, tmp_path: Path, entry: dict[str, Any], message: str) -> None:
        module_dir = _module(
            tmp_path, "demo_params", {"parameters": {"domain": "demo", "files": ["p/*.yaml"]}}
        )
        (module_dir / "p").mkdir()
        (module_dir / "p" / "a.yaml").write_text(
            yaml.safe_dump({"parameters": [entry]}), encoding="utf-8"
        )
        with pytest.raises(ModuleManifestError, match=message):
            load_parameter_rows(discover_modules(tmp_path)["demo_params"])

    def test_seed_dry_run(self) -> None:
        from scripts.seed_module_parameters import main

        assert main(["--dry-run"]) == 0
        assert main(["--dry-run", "--module", "nope"]) == 1


# ---------------------------------------------------------------------------
# WP-93 exit criterion
# ---------------------------------------------------------------------------

#: Files allowed to name area ids in code: registry/alias tables only.
_ALLOWED = {
    "app/db/models.py",  # LEGAL_AREA_ALLOWED/TIER + CHECK — removed by WP-94
    "app/modules/registry.py",  # built-in legacy alias table (D-038)
    "app/core/config.py",  # DEFAULT_MODULE default; goldset API alias path
}


def test_core_code_names_no_area_ids_outside_registry_tables() -> None:
    """Roadmap WP-93 exit: area ids appear in core code only in registry/alias
    tables. String literals in ``app/**/*.py`` are checked (docstrings and
    comments are documentation, not coupling)."""
    # "andere" is also an ordinary German word ("other") used in generic
    # prompt text, so the catch-all id counts only as an exact literal.
    words = [a for a in LEGAL_AREA_ALLOWED if a != "andere"]
    pattern = re.compile(r"\b(" + "|".join(words) + r")\b")
    offenders: list[str] = []
    for path in sorted((_REPO / "app").rglob("*.py")):
        rel = str(path.relative_to(_REPO))
        if rel in _ALLOWED:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        docstrings = {
            id(node.body[0].value)
            for node in ast.walk(tree)
            if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef)
            and node.body
            and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
        }
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and id(node) not in docstrings
                and (pattern.search(node.value) or node.value == "andere")
            ):
                offenders.append(f"{rel}:{node.lineno}: {node.value[:60]!r}")
    assert offenders == []
