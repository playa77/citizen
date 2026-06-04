"""Unit tests for app.services.presets — flat case-type preset catalog."""

# Semantic Version: 0.3.0

from __future__ import annotations

import pytest

from app.services.presets import get_preset, list_presets


class TestPresetsCatalog:
    def test_presets_is_a_list(self) -> None:
        assert isinstance(list_presets(), list)

    def test_exactly_5_presets(self) -> None:
        assert len(list_presets()) == 5, (
            "Plan locks in exactly 5 presets; got "
            f"{len(list_presets())}"
        )

    def test_all_presets_have_required_fields(self) -> None:
        for p in list_presets():
            for key in ("id", "name", "description", "legal_areas", "typical_scenarios"):
                assert key in p, f"preset {p.get('id')} missing {key!r}"

    def test_ids_are_unique(self) -> None:
        ids = [p["id"] for p in list_presets()]
        assert len(ids) == len(set(ids))

    def test_each_preset_has_at_least_one_area(self) -> None:
        for p in list_presets():
            assert len(p["legal_areas"]) >= 1

    def test_legal_areas_are_strings(self) -> None:
        for p in list_presets():
            for a in p["legal_areas"]:
                assert isinstance(a, str)
                assert a  # non-empty

    def test_typical_scenarios_is_list_of_strings(self) -> None:
        for p in list_presets():
            assert isinstance(p["typical_scenarios"], list)
            assert all(isinstance(s, str) for s in p["typical_scenarios"])
            assert all(s.strip() for s in p["typical_scenarios"])


class TestGetPreset:
    @pytest.mark.parametrize(
        "preset_id",
        [
            "sozialrecht-allgemein",
            "erbe-mit-testament",
            "erbe-mit-familie",
            "schenkung-zu-lebzeiten",
            "hofesuebergabe",
        ],
    )
    def test_lookup_each_preset(self, preset_id: str) -> None:
        p = get_preset(preset_id)
        assert p is not None
        assert p["id"] == preset_id

    def test_unknown_id_returns_none(self) -> None:
        assert get_preset("does-not-exist") is None
        assert get_preset("") is None


class TestPresetContent:
    """The preset catalog encodes the plan's expected composites."""

    def test_sozialrecht_preset_is_single_area(self) -> None:
        p = get_preset("sozialrecht-allgemein")
        assert p["legal_areas"] == ["sozialrecht"]

    def test_erbe_mit_familie_is_composite(self) -> None:
        p = get_preset("erbe-mit-familie")
        assert "erbrecht" in p["legal_areas"]
        assert "familienrecht" in p["legal_areas"]
        assert len(p["legal_areas"]) >= 2

    def test_schenkung_composite_includes_erbrecht(self) -> None:
        p = get_preset("schenkung-zu-lebzeiten")
        assert "schenkungsrecht" in p["legal_areas"]
        assert "erbrecht" in p["legal_areas"]

    def test_hofesuebergabe_composite(self) -> None:
        p = get_preset("hofesuebergabe")
        assert "erbrecht" in p["legal_areas"]
        assert len(p["legal_areas"]) >= 2
