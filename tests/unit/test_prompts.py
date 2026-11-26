"""Explicit module prompt dispatch and preserved area-specific composition (D-070)."""

# Semantic Version: 0.4.0 | 2026-11-16 — WP-93: profiles are module data; the
# former core constants are derived here from the public API (byte-identity
# with v2.0.0 is pinned separately in test_wp93_golden.py).

from __future__ import annotations

import pytest

from app.modules.areas import area_tables
from app.services.prompts import ModuleSelectionRequired, get_chat_prompt, get_prompts

# WP-93: area profiles live in modules/*/prompts/profile.yaml. The names the
# v1.x tests used are derived from the public API.
SOCIALRECHT_PROMPTS = get_prompts(["sozialrecht"])
ERBRECHT_PROMPTS = get_prompts(["erbrecht"])
REGISTRY = {area: get_prompts([area]) for area in area_tables().prompt_profiles}


# ---------------------------------------------------------------------------
# 1. Explicit inference scope
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "areas", [None, [], ["mietrecht"], ["xxx_nonexistent_xxx"], ["verwaltungsrecht"],
              ["sozialrecht", "mietrecht"]],
)
def test_unusable_scope_requires_explicit_selection(areas: list[str] | None) -> None:
    with pytest.raises(ModuleSelectionRequired):
        get_prompts(areas)
    for surface in ("chat", "case_chat"):
        with pytest.raises(ModuleSelectionRequired):
            get_chat_prompt(surface, areas)


def test_procedural_key_does_not_replace_explicit_profile() -> None:
    assert get_prompts(["verwaltungsrecht", "sozialrecht"]) == SOCIALRECHT_PROMPTS
    assert get_chat_prompt("chat", ["verwaltungsrecht", "sozialrecht"]) == get_chat_prompt(
        "chat", ["sozialrecht"]
    )


# ---------------------------------------------------------------------------
# 2. get_prompts(legal_areas) — basic dispatch
# ---------------------------------------------------------------------------


class TestGetPromptsDispatch:
    def test_socialrecht_returns_socialrecht(self) -> None:
        result = get_prompts(["sozialrecht"])
        assert result == SOCIALRECHT_PROMPTS

    def test_erbrecht_returns_erbrecht(self) -> None:
        result = get_prompts(["erbrecht"])
        assert result == ERBRECHT_PROMPTS
        assert result["classification"] != SOCIALRECHT_PROMPTS["classification"]

    def test_schenkungsrecht_uses_erbrecht_prompts(self) -> None:
        """Schenkungsrecht currently shares Erbrecht's prompt set
        because both deal with §§ 516ff BGB and ErbStG."""
        result = get_prompts(["schenkungsrecht"])
        assert result == ERBRECHT_PROMPTS

    def test_all_returned_prompts_have_all_stages(self) -> None:
        expected_keys = {
            "classification", "decomposition", "triage",
            "grounded_answer", "adversarial_review",
            "claim_construction", "verification", "output",
        }
        for areas in (
            ["sozialrecht"], ["erbrecht"], ["sozialrecht", "erbrecht"],
        ):
            keys = set(get_prompts(areas).keys())
            assert keys == expected_keys, f"areas={areas} missing={expected_keys - keys}"


# ---------------------------------------------------------------------------
# 3. Multi-area prompt composition
# ---------------------------------------------------------------------------


class TestMultiAreaCombine:
    def test_combined_includes_both_area_specialisations(self) -> None:
        result = get_prompts(["sozialrecht", "erbrecht"])
        cls = result["classification"]
        # SGB-specific phrase from sozialrecht prompt.
        assert "SGB" in cls
        # Erbrecht-specific phrase from erbrecht prompt.
        assert "Erbrecht" in cls or "BGB" in cls or "ErbStG" in cls

    def test_combined_triage_includes_preamble(self) -> None:
        result = get_prompts(["sozialrecht", "erbrecht"])
        assert "Experte für deutsches Sozialrecht sowie deutsches Erbrecht" in result["triage"]
        # The preamble explicitly mentions multi-area.
        assert "mehrere Rechtsgebiete" in result["triage"]

    def test_single_area_no_preamble(self) -> None:
        result = get_prompts(["erbrecht"])
        # Single area should NOT add the multi-area preamble.
        assert "mehrere Rechtsgebiete" not in result["classification"]

    def test_dedup_when_same_area_prompt_dict(self) -> None:
        # ["erbrecht", "schenkungsrecht"] should not double-combine.
        result = get_prompts(["erbrecht", "schenkungsrecht"])
        # Should equal ERBRECHT_PROMPTS (no combine needed).
        assert result == ERBRECHT_PROMPTS


# ---------------------------------------------------------------------------
# 5. Registry hygiene
# ---------------------------------------------------------------------------


class TestRegistry:
    def test_all_known_areas_have_all_stages(self) -> None:
        expected_keys = set(SOCIALRECHT_PROMPTS)
        for area, prompts in REGISTRY.items():
            assert set(prompts) == expected_keys, (
                f"area={area} missing stages"
            )

    def test_erbrecht_classification_mentions_erbrecht(self) -> None:
        assert "Erbrecht" in ERBRECHT_PROMPTS["classification"]

    def test_erbrecht_triage_mentions_erbrecht(self) -> None:
        assert "Erbrecht" in ERBRECHT_PROMPTS["triage"]
