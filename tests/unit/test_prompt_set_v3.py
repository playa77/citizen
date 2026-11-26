"""Invariants of prompt set 3.0.0 (docs/prompt-upgrade-proposal.md).

Contract-level checks, not text snapshots (those are the golden digests):
valid JSON examples, one format block that comes last, no escape hatch,
explicit multi-area flag, result vocabulary, size budget.
"""

from __future__ import annotations

import json
import re
from dataclasses import replace

import pytest

from app.services.prompts import (
    _OPEN_CATEGORY,
    PROMPT_SET_VERSION,
    STRICT_SUFFIX,
    _merge_profiles,
    _profile_registry,
    _render_triage,
    _slots,
    get_prompts,
    profile_from_mapping,
)
from citizen_modules.sozialrecht.calculators import (
    _EXPLANATION_SYSTEM,
    _EXTRACTION_SYSTEM,
    ExtractionValues,
)

AREA_SETS = [["sozialrecht"], ["erbrecht"], ["sozialrecht", "erbrecht"], ["familienrecht"]]
JSON_STAGES = list(get_prompts(["sozialrecht"]))  # every stage prompt is a JSON stage


def _format_example(prompt: str) -> str:
    block = prompt.split("<ausgabeformat>\n", 1)[1]
    return block.split("\n\n", 1)[0]


@pytest.mark.parametrize("areas", AREA_SETS, ids=lambda a: "+".join(a) or "default")
def test_examples_are_valid_json_and_format_block_is_last(areas: list[str]) -> None:
    for stage, prompt in get_prompts(areas).items():
        assert prompt.count("<ausgabeformat>") == 1, stage
        assert prompt.rstrip().endswith("</ausgabeformat>"), stage
        json.loads(_format_example(prompt))  # raises on invalid JSON (F-10 class)


def test_calculator_prompts_have_valid_examples() -> None:
    extraction = json.loads(_format_example(_EXTRACTION_SYSTEM))
    assert list(extraction["extracted_values"]) == list(ExtractionValues.model_fields)
    json.loads(_format_example(_EXPLANATION_SYSTEM))


def test_extraction_field_list_comes_from_schema() -> None:
    for name, info in ExtractionValues.model_fields.items():
        assert f"- {name}: {info.description}\n" in _EXTRACTION_SYSTEM


def test_strict_suffix_has_no_escape_hatch() -> None:
    assert "[]" not in STRICT_SUFFIX and "{}" not in STRICT_SUFFIX
    assert "<ausgabeformat>" in STRICT_SUFFIX


@pytest.mark.parametrize("stage", ["classification", "triage", "grounded_answer", "output"])
def test_single_area_prompts_fit_budget(stage: str) -> None:
    for areas in (["sozialrecht"], ["erbrecht"]):
        assert len(get_prompts(areas)[stage]) <= 6000


def test_multi_area_rules_follow_the_flag_not_the_name() -> None:
    soz = _profile_registry()["sozialrecht"]
    tricky = replace(soz, display_name="deutsches Sozialrecht sowie Verwaltungsverfahren")
    assert "mehrere Rechtsgebiete" not in _render_triage(_slots(tricky))
    merged = _merge_profiles([soz, _profile_registry()["erbrecht"]])
    assert merged.is_multi_area
    assert "mehrere Rechtsgebiete" in _render_triage(_slots(merged))


def test_conflict_targets_per_stage() -> None:
    prompts = get_prompts(["sozialrecht", "erbrecht"])
    assert "beschreibe den Konflikt in sections.unsicherheiten" in prompts["grounded_answer"]
    assert "beschreibe den Konflikt in overall_assessment.key_risks" in prompts[
        "adversarial_review"
    ]


def test_result_categories_render_and_merge() -> None:
    soz_answer = get_prompts(["sozialrecht"])["grounded_answer"]
    assert "• teilweise rechtswidrig – " in soz_answer
    assert f"• {_OPEN_CATEGORY}" in soz_answer
    merged = get_prompts(["sozialrecht", "erbrecht"])["grounded_answer"]
    assert "• Position teilweise tragfähig" in merged and "• rechtswidrig" in merged
    assert merged.count(_OPEN_CATEGORY) == 1


def test_profile_requires_result_categories() -> None:
    data = {
        "key": "x",
        "display_name": "d",
        "statutes": "s",
        "document_examples": "e",
        "issue_terms": [],
        "formal_examples": "f",
        "material_examples": "m",
        "answerable_with": "a",
        "hierarchy_example": "h",
        "adversary_examples": "g",
    }
    with pytest.raises(TypeError, match="result_categories"):
        profile_from_mapping(data)


def test_issue_term_anchors_parse_as_norms() -> None:
    from eval.extractors import extract_norm_references

    for profile in {id(p): p for p in _profile_registry().values()}.values():
        for term in profile.issue_terms:
            if "§" in term:
                assert extract_norm_references(term), term


def test_no_lawyer_persona_or_advice_promise() -> None:
    for stage, prompt in get_prompts(["sozialrecht"]).items():
        assert "Erstberater" not in prompt, stage
        assert "Anwalt der Nutzerseite" not in prompt, stage
    assert re.search(r"keine Rechtsberatung", get_prompts(["sozialrecht"])["grounded_answer"])


def test_cross_check_searches_document_only() -> None:
    from app.services.calculation import _document_part

    content = "## DOKUMENT\nRegelbedarf 563,00\n\n## KONTEXT: CLAIMS (aus der Analyse)\n999,99"
    assert _document_part(content) == "Regelbedarf 563,00"


async def test_legacy_messages_use_german_headings(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services import reasoning

    sent: list[str] = []

    class _Fake:
        models = ["m"]

        async def chat_completion(self, messages: list[dict[str, str]], **_: object) -> str:
            sent.append(messages[1]["content"])
            return "[]" if "Rechtsfragen" in messages[1]["content"] else '{"sachverhalt": ""}'

    monkeypatch.setattr(reasoning, "get_shared_client", lambda: _Fake())
    await reasoning.construct_claims(
        [{"hierarchy_path": "SGB X", "text_content": "t"}], ["F?"],
        system_prompt=get_prompts(["sozialrecht"])["claim_construction"],
    )
    await reasoning.generate_output(
        [{"claim_text": "c", "claim_type": "interpretation"}],
        system_prompt=get_prompts(["sozialrecht"])["output"],
    )
    assert sent[0].startswith("Rechtsfragen:\n") and "\n\nRechtsquellen:\n" in sent[0]
    assert sent[1].startswith("Geprüfte Claims:\n")


def test_regime_block_reaches_answer_and_review_not_triage() -> None:
    from app.core.pipeline import PipelineState, _stage_prompt

    state = PipelineState(
        input_text="x",
        normalized_text="Musterstadt, 03.05.2024\nBescheid",
        legal_areas=["sozialrecht"],
    )
    # No triage ran (re-evaluation path): the block is computed lazily.
    answer = _stage_prompt(state, "grounded_answer")
    review = _stage_prompt(state, "adversarial_review")
    triage = _stage_prompt(state, "triage")
    assert answer.startswith("<rechtsstand>\nStichtag: 03.05.2024")
    assert review.startswith("<rechtsstand>")
    assert not triage.startswith("<rechtsstand>")
    assert state.legal_regime_info["regimes"] == ["a.F._2023"]
    assert state.prompt_ids["adversarial_review"]["version"] == PROMPT_SET_VERSION


def test_no_regime_block_for_modules_without_provider() -> None:
    from app.core.pipeline import PipelineState, _stage_prompt

    state = PipelineState(input_text="x", normalized_text="Testament", legal_areas=["erbrecht"])
    assert _stage_prompt(state, "grounded_answer").startswith("<rolle>")
