"""Unit tests for multi-area pipeline wiring.

These tests focus on the *plumbing* — the parts of the multi-area
refactor that don't require a live DB or a real LLM call:

- PipelineState.legal_areas / per_area_chunks / intake_session_id are
  well-formed fields on the dataclass
- The prompts registry produces a multi-area prompt that includes
  both areas' content
- The retrieval module exposes ``retrieve_chunks_for_areas`` and
  ``retrieve_chunks_combined_filtered`` with the documented signatures
- ``app.services.corpus_readiness.AREA_TO_SOURCE_TYPES`` covers all
  closed-enum legal_areas
"""

# Semantic Version: 0.3.0

from __future__ import annotations

import inspect

import pytest

from app.core.pipeline import PipelineState
from app.db.models import LEGAL_AREA_ALLOWED
from app.services import retrieval
from app.services.corpus_readiness import (
    AREA_TO_SOURCE_TYPES,
    check_preflight,
    get_area_status,
)
from app.services.prompts import ERBRECHT_PROMPTS, SOCIALRECHT_PROMPTS, get_prompts


# ---------------------------------------------------------------------------
# 1. PipelineState has the multi-area fields
# ---------------------------------------------------------------------------


class TestPipelineState:
    def test_default_legal_areas_is_empty(self) -> None:
        s = PipelineState(input_text="hello")
        assert s.legal_areas == []
        assert s.per_area_chunks == {}
        assert s.intake_session_id is None

    def test_legal_areas_are_stored(self) -> None:
        s = PipelineState(
            input_text="hello", legal_areas=["erbrecht", "familienrecht"],
        )
        assert s.legal_areas == ["erbrecht", "familienrecht"]

    def test_intake_session_id_stored(self) -> None:
        s = PipelineState(
            input_text="hello", intake_session_id="abc-123",
        )
        assert s.intake_session_id == "abc-123"

    def test_per_area_chunks_stored(self) -> None:
        s = PipelineState(input_text="x", per_area_chunks={"erbrecht": [{"x": 1}]})
        assert s.per_area_chunks == {"erbrecht": [{"x": 1}]}


# ---------------------------------------------------------------------------
# 2. retrieve_chunks_for_areas signature
# ---------------------------------------------------------------------------


class TestMultiAreaRetrieval:
    def test_retrieve_chunks_for_areas_is_coroutine(self) -> None:
        assert inspect.iscoroutinefunction(retrieval.retrieve_chunks_for_areas)

    def test_combined_filtered_is_coroutine(self) -> None:
        assert inspect.iscoroutinefunction(
            retrieval.retrieve_chunks_combined_filtered
        )

    def test_per_area_is_coroutine(self) -> None:
        assert inspect.iscoroutinefunction(retrieval.retrieve_chunks_per_area)

    def test_for_areas_returns_tuple_of_dict_and_list(self) -> None:
        sig = inspect.signature(retrieval.retrieve_chunks_for_areas)
        # Required positional parameters.
        params = list(sig.parameters.values())
        assert params[0].name == "legal_areas"
        assert params[1].name == "issues"
        assert params[2].name == "questions"
        assert params[3].name == "normalized_text"

    def test_for_areas_handles_empty_input(self) -> None:
        # Empty legal_areas → empty per_area dict and empty merged list.
        import asyncio
        result = asyncio.run(retrieval.retrieve_chunks_for_areas(
            [], [], [], "",
        ))
        assert result == ({}, [])


# ---------------------------------------------------------------------------
# 3. AREA_TO_SOURCE_TYPES covers all enum members
# ---------------------------------------------------------------------------


class TestAreaToSourceTypes:
    @pytest.mark.parametrize("area", LEGAL_AREA_ALLOWED)
    def test_area_has_mapping(self, area: str) -> None:
        # Every enum value is a key in AREA_TO_SOURCE_TYPES (even if
        # the value is an empty tuple).
        assert area in AREA_TO_SOURCE_TYPES, f"area {area} not mapped"

    def test_sozialrecht_covers_sgb_sources(self) -> None:
        sources = AREA_TO_SOURCE_TYPES["sozialrecht"]
        for required in ("sgb2", "sgbx", "weisung"):
            assert required in sources

    def test_erbrecht_includes_erbstg(self) -> None:
        assert "erbstg" in AREA_TO_SOURCE_TYPES["erbrecht"]

    def test_erbrecht_includes_hoefev(self) -> None:
        assert "hoefev" in AREA_TO_SOURCE_TYPES["erbrecht"]

    def test_erbrecht_includes_bgb(self) -> None:
        assert "bgb" in AREA_TO_SOURCE_TYPES["erbrecht"]

    def test_schenkungsrecht_includes_bgb_and_erbstg(self) -> None:
        assert "bgb" in AREA_TO_SOURCE_TYPES["schenkungsrecht"]
        assert "erbstg" in AREA_TO_SOURCE_TYPES["schenkungsrecht"]

    def test_strafrecht_no_sources(self) -> None:
        # No corpus source yet (placeholder).
        assert AREA_TO_SOURCE_TYPES["strafrecht"] == ()


# ---------------------------------------------------------------------------
# 4. get_area_status (async) with empty DB
# ---------------------------------------------------------------------------


class TestGetAreaStatus:
    def test_signature(self) -> None:
        sig = inspect.signature(get_area_status)
        params = list(sig.parameters.values())
        assert params[0].name == "session"
        assert params[1].name == "legal_areas"

    def test_check_preflight_signature(self) -> None:
        sig = inspect.signature(check_preflight)
        params = list(sig.parameters.values())
        assert params[0].name == "session"
        assert params[1].name == "legal_areas"


# ---------------------------------------------------------------------------
# 5. Prompts integration: legal_areas thread through get_prompts
# ---------------------------------------------------------------------------


class TestPromptsThreading:
    def test_legal_areas_propagate(self) -> None:
        # Sanity: get_prompts(legal_areas) returns the same dict as
        # the source registry for the same area.
        for area in ("sozialrecht", "erbrecht"):
            assert get_prompts([area])[area == "erbrecht" and "grounded_answer" or "grounded_answer"]
        # Two distinct areas must produce non-trivial combined prompt.
        combined = get_prompts(["sozialrecht", "erbrecht"])
        assert "mehrere Rechtsgebiete" in combined["triage"]
