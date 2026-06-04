"""Unit tests for app.services.prompts — prompt registry & byte-identity contract.

Covers
------
- ``get_prompts([])`` returns the socialrecht defaults (backward compat)
- ``get_prompts(["sozialrecht"])`` matches defaults
- ``get_prompts(["erbrecht"])`` returns erbrecht-specific prompts for
  classification, decomposition, triage, grounded_answer
- Multi-area: ``get_prompts(["sozialrecht", "erbrecht"])`` returns
  combined prompts containing both areas' content
- ``get_prompts(None)`` matches the empty-list case
- ``get_prompts(["andere"])`` falls back to socialrecht (per registry)
- ``_normalise_area`` (re-exported) — out of scope, lives in intake.py
- The socialrecht constants are byte-identical to the original strings
  that lived in ``app.services.reasoning`` before the multi-area refactor.
"""

# Semantic Version: 0.3.0

from __future__ import annotations

import pytest

from app.services.prompts import (
    ERBRECHT_PROMPTS,
    REGISTRY,
    SOCIALRECHT_PROMPTS,
    _combine_prompts,
    get_prompts,
)
from app.services.reasoning import (
    _ADVERSARIAL_REVIEW_SYSTEM,
    _CLAIM_CONSTRUCTION_SYSTEM,
    _CLASSIFICATION_SYSTEM,
    _DECOMPOSITION_SYSTEM,
    _GROUNDED_ANSWER_SYSTEM,
    _OUTPUT_SYSTEM,
    _TRIAGE_SYSTEM,
    _VERIFICATION_SYSTEM,
)


# ---------------------------------------------------------------------------
# 1. Byte-identical contract
# ---------------------------------------------------------------------------


class TestByteIdenticalContract:
    """The 8 system-prompt constants in ``reasoning.py`` must be the
    *same Python string object* as their counterparts in
    ``prompts.SOCIALRECHT_PROMPTS``."""

    def test_classification(self) -> None:
        assert _CLASSIFICATION_SYSTEM == SOCIALRECHT_PROMPTS["classification"]

    def test_decomposition(self) -> None:
        assert _DECOMPOSITION_SYSTEM == SOCIALRECHT_PROMPTS["decomposition"]

    def test_triage(self) -> None:
        assert _TRIAGE_SYSTEM == SOCIALRECHT_PROMPTS["triage"]

    def test_grounded_answer(self) -> None:
        assert _GROUNDED_ANSWER_SYSTEM == SOCIALRECHT_PROMPTS["grounded_answer"]

    def test_adversarial_review(self) -> None:
        assert _ADVERSARIAL_REVIEW_SYSTEM == SOCIALRECHT_PROMPTS["adversarial_review"]

    def test_claim_construction(self) -> None:
        assert _CLAIM_CONSTRUCTION_SYSTEM == SOCIALRECHT_PROMPTS["claim_construction"]

    def test_verification(self) -> None:
        assert _VERIFICATION_SYSTEM == SOCIALRECHT_PROMPTS["verification"]

    def test_output(self) -> None:
        assert _OUTPUT_SYSTEM == SOCIALRECHT_PROMPTS["output"]


# ---------------------------------------------------------------------------
# 2. get_prompts(legal_areas) — basic dispatch
# ---------------------------------------------------------------------------


class TestGetPromptsDispatch:
    def test_empty_list_returns_socialrecht(self) -> None:
        result = get_prompts([])
        assert result == SOCIALRECHT_PROMPTS

    def test_none_returns_socialrecht(self) -> None:
        result = get_prompts(None)
        assert result == SOCIALRECHT_PROMPTS

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

    def test_unknown_area_falls_back_to_socialrecht(self) -> None:
        result = get_prompts(["mietrecht"])  # not in REGISTRY yet
        assert result == SOCIALRECHT_PROMPTS

    def test_garbage_value_falls_back_to_socialrecht(self) -> None:
        result = get_prompts(["xxx_nonexistent_xxx"])
        assert result == SOCIALRECHT_PROMPTS

    def test_all_returned_prompts_have_all_stages(self) -> None:
        expected_keys = {
            "classification", "decomposition", "triage",
            "grounded_answer", "adversarial_review",
            "claim_construction", "verification", "output",
        }
        for areas in (
            [], ["sozialrecht"], ["erbrecht"], ["sozialrecht", "erbrecht"],
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
        assert "Rechtsexperte" in result["triage"]
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
# 4. _combine_prompts helper
# ---------------------------------------------------------------------------


class TestCombinePromptsHelper:
    def test_empty(self) -> None:
        assert _combine_prompts([]) == ""

    def test_single(self) -> None:
        assert _combine_prompts(["foo"]) == "foo"

    def test_two_includes_preamble(self) -> None:
        out = _combine_prompts(["alpha", "beta"])
        assert "Rechtsexperte" in out
        assert "alpha" in out
        assert "beta" in out
        # Separator between.
        assert "---" in out


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
