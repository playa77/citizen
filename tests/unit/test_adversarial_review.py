"""Stage 7 review (CR-01, CR-02; F-01, F-17) and grounded-answer plumbing.

Before prompt set 3.0.0 the review was sent by the grounded-answer function,
which parsed only ``claims``/``sections``: every review was discarded, and
the claims under review never reached the model.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from app.services import reasoning
from app.services.reasoning import (
    _claims_block,
    _validate_review,
    adversarial_review,
    generate_grounded_answer,
    generate_grounded_answer_stream,
)
from app.utils.tokens import DOCUMENT_TRUNCATION_MARKER, trim_document, trim_text

CLAIMS = [
    {
        "claim_text": "Die Anhörung fehlt.",
        "confidence_score": 0.7,
        "claim_type": "interpretation",
        "evidence_chunk_id": "c-24",
        "evidence_hierarchy": "SGB X > § 24",
        "evidence_quote": "Bevor ein Verwaltungsakt erlassen wird …",
        "verification_status": "exakt",
    },
    {"claim_text": "Mit den bereitgestellten Quellen nicht belegbar: X", "confidence_score": 0.2},
]

REVIEW = {
    "reviews": [
        {
            "claim_index": 1,
            "defense_argument": "d1",
            "authority_argument": "a1",
            "judicial_assessment": "j1",
            "procedural_issues": "p1",
            "risk_level": "HOCH",
            "recommended_strategy": "s1",
        },
        {"claim_index": 0, "risk_level": "niedrig", "defense_argument": "d0"},
        {"claim_index": 0, "risk_level": "mittel"},  # duplicate index → dropped
        {"claim_index": 7, "risk_level": "mittel"},  # out of range → dropped
        {"claim_index": True, "risk_level": "mittel"},  # bool is not an index
        {"claim_index": 1, "risk_level": "riesig"},  # duplicate → dropped
    ],
    "overall_assessment": {
        "summary": "Zusammenfassung",
        "key_risks": ["r1", " ", "r2"],
        "recommended_next_steps": "kein Array",
        "confidence_in_defense": 1.7,
        "procedural_errors_found": [],
    },
}


class _FakeClient:
    """Records calls; returns queued responses."""

    models = ["m1"]

    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.calls: list[dict[str, Any]] = []

    async def chat_completion(self, messages: list[dict[str, str]], **kw: Any) -> str:
        self.calls.append({"messages": messages, **kw})
        return self.responses.pop(0)

    async def chat_completion_stream(self, messages: list[dict[str, str]], **kw: Any) -> Any:
        self.calls.append({"messages": messages, "stream": True, **kw})
        for token in self.responses.pop(0):
            yield token


def test_validate_review_normalises() -> None:
    out = _validate_review(REVIEW, n_claims=2)
    assert [r["claim_index"] for r in out["reviews"]] == [0, 1]
    assert out["reviews"][1]["risk_level"] == "hoch"
    assert out["reviews"][0]["authority_argument"] == ""
    oa = out["overall_assessment"]
    assert oa["confidence_in_defense"] == 1.0
    assert oa["key_risks"] == ["r1", "r2"]
    assert oa["recommended_next_steps"] == []


def test_validate_review_unknown_risk_fails_towards_caution() -> None:
    out = _validate_review({"reviews": [{"claim_index": 0, "risk_level": "egal"}]}, n_claims=1)
    assert out["reviews"][0]["risk_level"] == "hoch"


def test_claims_block_numbers_and_evidence() -> None:
    block = _claims_block(CLAIMS, 10_000)
    assert block.startswith("[0] (interpretation, 0.70, exakt) Die Anhörung fehlt.")
    assert "Beleg: CHUNK [c-24] SGB X > § 24:" in block
    assert "[1] (?, 0.20, ungeprüft)" in block


async def test_review_sends_claims_and_parses_review(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeClient([json.dumps(REVIEW)])
    monkeypatch.setattr(reasoning, "get_shared_client", lambda: fake)
    out = await adversarial_review("Bescheid", ["T"], ["F?"], CLAIMS, [], system_prompt="SYS")
    user = fake.calls[0]["messages"][1]["content"]
    assert "## CLAIMS\n[0] (interpretation" in user
    assert fake.calls[0]["temperature"] == reasoning.stage_temperature("adversarial_review")
    assert len(out["reviews"]) == 2
    assert out["overall_assessment"]["summary"] == "Zusammenfassung"
    assert "claims" not in out  # the F-17 shape is gone


async def test_grounded_answer_unchanged_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeClient([json.dumps({"claims": [{"claim_text": "a", "claim_type": "x"}]})])
    monkeypatch.setattr(reasoning, "get_shared_client", lambda: fake)
    out = await generate_grounded_answer("Bescheid", [], [], [], [], system_prompt="SYS")
    assert out["claims"][0]["claim_type"] == "fact"
    assert set(out["sections"]) >= {"ergebnis", "adversarial_pruefung"}
    assert "## CLAIMS" not in fake.calls[0]["messages"][1]["content"]


async def test_stream_fallback_keeps_system_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeClient(["not json", json.dumps({"claims": [], "sections": {}})])
    monkeypatch.setattr(reasoning, "get_shared_client", lambda: fake)
    items = [
        item
        async for item in generate_grounded_answer_stream(
            "Bescheid", [], [], [], system_prompt="AREA-SYS"
        )
    ]
    assert items[-1]["type"] == "done"
    assert fake.calls[1]["messages"][0]["content"].startswith("AREA-SYS")


def test_trim_document_marks_cut() -> None:
    assert trim_document("abc", 5) == "abc"
    assert trim_document("abcdef", 3) == "abc" + DOCUMENT_TRUNCATION_MARKER
    assert trim_text("abcdef", 3) == "abc"  # unmarked default unchanged
