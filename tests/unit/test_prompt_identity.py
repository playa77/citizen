"""Prompt identity, triage cache key and eval re-scoring (CR-08, CR-09, CR-13)."""

from __future__ import annotations

import json
from pathlib import Path

from app.services.prompts import (
    DEFAULT_PROMPTS,
    PROMPT_SET_VERSION,
    get_prompts,
    prompt_digest,
    prompt_identity,
)
from app.services.reasoning import _triage_cache_text
from eval.pipeline_adapter import PipelineOutput
from eval.runner import _output_to_json, _prompt_set_identity, run_eval

GOLDSET = "modules/sozialrecht/goldset/goldset-v0.2.0.yaml"


def test_prompt_identity_shape() -> None:
    ident = prompt_identity("triage", "abc")
    assert ident == {"id": "triage", "version": PROMPT_SET_VERSION, "sha256": prompt_digest("abc")}
    assert len(ident["sha256"]) == 64


def test_triage_cache_text_depends_on_prompt_and_version() -> None:
    soz = get_prompts(["sozialrecht"])["triage"]
    erb = get_prompts(["erbrecht"])["triage"]
    doc = "Bescheid vom 01.03.2026"
    assert _triage_cache_text(soz, doc) != _triage_cache_text(erb, doc)
    assert _triage_cache_text(soz, doc) == _triage_cache_text(soz, doc)
    assert PROMPT_SET_VERSION in _triage_cache_text(soz, doc)


def test_eval_report_records_prompt_set() -> None:
    ident = _prompt_set_identity()
    assert ident["version"] == PROMPT_SET_VERSION
    assert set(ident["stages"]) == set(DEFAULT_PROMPTS)


async def test_rescore_uses_saved_outputs_without_pipeline(tmp_path: Path) -> None:
    output = PipelineOutput(
        issues=["Anhörung (§ 24 SGB X)"],
        retrieved_chunks=[{"chunk_id": "c1", "text_content": "long", "hierarchy_path": "SGB X"}],
    )
    saved = tmp_path / "run.outputs.json"
    saved.write_text(json.dumps({"GS-001": _output_to_json(output)}), "utf-8")
    assert "text_content" not in json.loads(saved.read_text("utf-8"))["GS-001"]["retrieved_chunks"][0]

    report = await run_eval(GOLDSET, case_filter="GS-001", rescore_path=str(saved))

    assert [c.case_id for c in report.cases] == ["GS-001"]
    assert report.prompt_set["version"] == PROMPT_SET_VERSION
    assert report.cases[0].quote_verification_rate_sourced is None  # no claims at all
