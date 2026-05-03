"""Unit tests for the 7-stage pipeline orchestrator (WP-010).

All stages beyond normalization depend on ``app.services.reasoning`` and
``app.services.retrieval`` which are implemented in WP-011 / WP-012.  Tests
patch those functions with lightweight async stubs so the orchestrator loop
can be exercised in isolation.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import is_dataclass
from typing import Any

import pytest

from app.core.pipeline import (
    PipelineState,
    PipelineTimeoutError,
    StageExecutionError,
    _sse_event,
    _stage_payload,
    execute_stage,
    run_pipeline,
)

SAMPLE_INPUT = """
  Ich habe einen Bescheid vom Jobcenter bekommen.
  Die Leistung wurde nach § 31 SGB II gekürzt.

  Ich bin der Meinung, dass das nicht korrekt ist.
"""

SAMPLE_NORMALIZED = (
    "Ich habe einen Bescheid vom Jobcenter bekommen.\n"
    "Die Leistung wurde nach § 31 SGB II gekürzt.\n"
    "Ich bin der Meinung, dass das nicht korrekt ist."
)

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_reasoning(monkeypatch: pytest.MonkeyPatch) -> None:
    """Create dummy ``app.services.reasoning`` module with async stubs."""

    async def classify_issues(text: str) -> list[str]:
        return ["SGB II § 31 — Kürzung der Leistung"]

    async def decompose_questions(text: str) -> list[str]:
        return [
            "War die Kürzung nach § 31 SGB II rechtmäßig?",
            "Welche Mitwirkungspflichten wurden verletzt?",
            "Kann die Kürzung angefochten werden?",
        ]

    async def construct_claims(
        chunks: list[dict[str, Any]], questions: list[str]
    ) -> list[dict[str, Any]]:
        return [
            {
                "claim_text": "Die Kürzung war unverhältnismäßig.",
                "confidence_score": 0.78,
                "claim_type": "interpretation",
            }
        ]

    async def verify_claims(
        claims: list[dict[str, Any]], chunks: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        return [
            {
                "claim_text": claims[0]["claim_text"],
                "confidence_score": 0.72,
                "claim_type": claims[0]["claim_type"],
                "verified": True,
            }
        ]

    async def generate_output(verified_claims: list[dict[str, Any]]) -> dict[str, str]:
        return {
            "sachverhalt": "Der Antragsteller erhielt einen Kürzungsbescheid.",
            "rechtliche_wuerdigung": "§ 31 SGB II erfordert Prüfung.",
            "ergebnis": "Kürzung kann anfechtbar sein.",
            "handlungsempfehlung": "Widerspruch einlegen.",
            "entwurf": "Sehr geehrte Damen und Herren, ...",
            "unsicherheiten": "Fehlende Unterlagen.",
        }

    import sys
    import types

    mod = types.ModuleType("app.services.reasoning")
    mod.classify_issues = classify_issues  # type: ignore[attr-defined]
    mod.decompose_questions = decompose_questions  # type: ignore[attr-defined]
    mod.construct_claims = construct_claims  # type: ignore[attr-defined]
    mod.verify_claims = verify_claims  # type: ignore[attr-defined]
    mod.generate_output = generate_output  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "app.services.reasoning", mod)


@pytest.fixture
def mock_retrieval(monkeypatch: pytest.MonkeyPatch) -> None:
    """Create dummy ``app.services.retrieval`` module with async stub."""

    async def retrieve_chunks(questions: list[str]) -> list[dict[str, Any]]:
        return [
            {
                "id": "chunk-1",
                "text": "§ 31 Abs. 1 SGB II: …",
                "hierarchy_path": "SGB II > § 31 > Abs. 1",
            }
        ]

    import sys
    import types

    mod = types.ModuleType("app.services.retrieval")
    mod.retrieve_chunks = retrieve_chunks  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "app.services.retrieval", mod)


# ---------------------------------------------------------------------------
# PipelineState
# ---------------------------------------------------------------------------


class TestPipelineState:
    def test_is_dataclass(self) -> None:
        assert is_dataclass(PipelineState)

    def test_default_values(self) -> None:
        state = PipelineState(input_text=SAMPLE_INPUT)
        assert state.normalized_text == ""
        assert state.issues == []
        assert state.questions == []
        assert state.retrieved_chunks == []
        assert state.claims == []
        assert state.verified_claims == []
        assert state.final_output == {}
        assert state.errors == []
        assert state.input_text == SAMPLE_INPUT


# ---------------------------------------------------------------------------
# SSE formatting
# ---------------------------------------------------------------------------


class TestSSEFormatting:
    def test_sse_event_format(self) -> None:
        result = _sse_event("normalization", "complete", {"text_length": 50})
        assert result.startswith("data: ")
        assert result.endswith("\n\n")

        data = json.loads(result[len("data: ") :].strip())
        assert data["stage"] == "normalization"
        assert data["status"] == "complete"
        assert data["payload"]["text_length"] == 50

    def test_sse_event_is_valid_json(self) -> None:
        """Ensure every SSE line is parseable JSON after 'data: ' prefix."""
        result = _sse_event(
            "classification",
            "complete",
            {"issues": ["test"], "issue_count": 1},
        )
        payload_str = result[len("data: ") :].strip()
        parsed = json.loads(payload_str)
        assert parsed == {
            "stage": "classification",
            "status": "complete",
            "payload": {"issues": ["test"], "issue_count": 1},
        }


# ---------------------------------------------------------------------------
# Stage payloads
# ---------------------------------------------------------------------------


class TestStagePayloads:
    def test_normalization_payload(self) -> None:
        state = PipelineState(input_text=SAMPLE_INPUT, normalized_text=SAMPLE_NORMALIZED)
        payload = _stage_payload(state, stage_name="normalization", duration_ms=5)
        assert payload["text_length"] == len(SAMPLE_NORMALIZED)
        assert payload["duration_ms"] == 5

    def test_classification_payload(self) -> None:
        state = PipelineState(input_text="", issues=["SGB II"])
        payload = _stage_payload(state, stage_name="classification", duration_ms=10)
        assert payload["issues"] == ["SGB II"]
        assert payload["issue_count"] == 1

    def test_decomposition_payload(self) -> None:
        state = PipelineState(input_text="", questions=["Q1", "Q2"])
        payload = _stage_payload(state, stage_name="decomposition", duration_ms=15)
        assert payload["questions"] == ["Q1", "Q2"]
        assert payload["question_count"] == 2

    def test_retrieval_payload(self) -> None:
        state = PipelineState(input_text="", retrieved_chunks=[{"id": "c1"}])
        payload = _stage_payload(state, stage_name="retrieval", duration_ms=20)
        assert payload["chunk_count"] == 1

    def test_construction_payload(self) -> None:
        state = PipelineState(input_text="", claims=[{"claim_text": "X"}])
        payload = _stage_payload(state, stage_name="construction", duration_ms=25)
        assert payload["claim_count"] == 1

    def test_verification_payload(self) -> None:
        state = PipelineState(input_text="", verified_claims=[{"verified": True}])
        payload = _stage_payload(state, stage_name="verification", duration_ms=30)
        assert payload["verified_claim_count"] == 1

    def test_generation_payload(self) -> None:
        state = PipelineState(
            input_text="",
            final_output={"sachverhalt": "...", "ergebnis": "..."},
        )
        payload = _stage_payload(state, stage_name="generation", duration_ms=35)
        assert payload["sections"] == ["sachverhalt", "ergebnis"]


# ---------------------------------------------------------------------------
# Single-stage execution
# ---------------------------------------------------------------------------


class TestSingleStageExecution:
    @pytest.mark.asyncio
    async def test_normalization_stage(self) -> None:
        """Stage 1 should normalize input text without mocks."""
        state = PipelineState(input_text="   Hallo\n\n\nWelt   ")
        events = [e async for e in execute_stage("normalization", state)]
        assert len(events) == 1
        data = json.loads(events[0][len("data: ") :].strip())
        assert data["stage"] == "normalization"
        assert data["status"] == "complete"
        assert state.normalized_text == "Hallo\nWelt"

    @pytest.mark.asyncio
    async def test_unknown_stage_raises(self) -> None:
        state = PipelineState(input_text="")
        with pytest.raises(StageExecutionError, match="Unknown stage"):
            async for _ in execute_stage("nonexistent", state):
                pass


# ---------------------------------------------------------------------------
# Full pipeline — stage order and SSE format
# ---------------------------------------------------------------------------


class TestPipelineSequence:
    @pytest.mark.asyncio
    async def test_stage_sequence(self, mock_reasoning: None, mock_retrieval: None) -> None:
        """Verifies the 7 stages execute in order and produce correct SSE."""
        state = PipelineState(input_text=SAMPLE_INPUT)
        events: list[str] = []
        async for event in run_pipeline(state):
            events.append(event)

        stage_names = [json.loads(e[len("data: ") :].strip())["stage"] for e in events]
        expected = [
            "normalization",
            "classification",
            "decomposition",
            "retrieval",
            "construction",
            "verification",
            "generation",
        ]
        assert stage_names == expected

        # All stages report "complete".
        statuses = [json.loads(e[len("data: ") :].strip())["status"] for e in events]
        assert all(s == "complete" for s in statuses)

    @pytest.mark.asyncio
    async def test_pipeline_mutates_state(self, mock_reasoning: None, mock_retrieval: None) -> None:
        """After the pipeline runs, each state field should be populated."""
        state = PipelineState(input_text=SAMPLE_INPUT)
        async for _ in run_pipeline(state):
            pass

        assert state.normalized_text != ""
        assert len(state.issues) > 0
        assert len(state.questions) > 0
        assert len(state.retrieved_chunks) > 0
        assert len(state.claims) > 0
        assert len(state.verified_claims) > 0
        assert len(state.final_output) > 0
        assert state.final_output.get("sachverhalt") is not None
        assert state.final_output.get("rechtliche_wuerdigung") is not None
        assert state.final_output.get("ergebnis") is not None
        assert state.final_output.get("handlungsempfehlung") is not None
        assert state.final_output.get("entwurf") is not None
        assert state.final_output.get("unsicherheiten") is not None


# ---------------------------------------------------------------------------
# Timeout enforcement
# ---------------------------------------------------------------------------


class TestPipelineTimeout:
    @pytest.mark.asyncio
    async def test_timeout_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A pipeline that takes longer than the timeout should raise
        PipelineTimeoutError.
        """

        async def _slow_collect(state: PipelineState) -> list[str]:
            await asyncio.sleep(10)  # far exceeds the timeout
            return []

        monkeypatch.setattr("app.core.pipeline._collect_events", _slow_collect)
        monkeypatch.setattr(
            "app.core.pipeline.cfg._get_settings",
            lambda: type("Settings", (), {"PIPELINE_TIMEOUT_SEC": 1})(),
        )

        state = PipelineState(input_text=SAMPLE_INPUT)
        with pytest.raises(PipelineTimeoutError, match="exceeded 1s timeout"):
            async for _ in run_pipeline(state):
                pass

    @pytest.mark.asyncio
    async def test_asyncio_wait_for_timeout(self) -> None:
        """Direct asyncio.wait_for should raise TimeoutError which the
        pipeline translates to PipelineTimeoutError.
        """
        with pytest.raises(TimeoutError):

            async def _slow() -> list[str]:
                await asyncio.sleep(10)
                return []

            await asyncio.wait_for(_slow(), timeout=0.01)


# ---------------------------------------------------------------------------
# Stage error propagation
# ---------------------------------------------------------------------------


class TestStageErrors:
    @pytest.mark.asyncio
    async def test_stage_error_recorded_in_state(self) -> None:
        """If a stage fails, the error should be appended to state.errors."""
        state = PipelineState(input_text=SAMPLE_INPUT)
        with pytest.raises(StageExecutionError):
            async for _ in execute_stage("classification", state):
                pass

        # classification depends on app.services.reasoning which doesn't
        # exist yet (no mock applied here) — expect ImportError.
        assert any("classification" in e for e in state.errors)
