"""Unit tests for app.services.intake — LLM-driven multi-turn intake interview.

These tests cover the *deterministic* parts of the intake service:
- prompt message construction
- area normalisation
- keyword fallback area detection
- closed-enum validation
- JSON parsing tolerance

LLM-driven paths (start_intake, continue_intake, finalize_intake) are
covered by test_intake_api.py which uses the FastAPI test client with
a stubbed LLM client.
"""

# Semantic Version: 0.3.0

from __future__ import annotations

import pytest

from app.services.intake import (
    _AREA_KEYWORDS,
    _LEGAL_AREAS_ENUM,
    build_intake_messages,
    _normalise_area,
    _fallback_areas_from_text,
    _parse_intake_response,
    IntakeError,
)


# ---------------------------------------------------------------------------
# 1. Closed enum
# ---------------------------------------------------------------------------


class TestLegalAreasEnum:
    def test_enum_is_tuple(self) -> None:
        assert isinstance(_LEGAL_AREAS_ENUM, tuple)
        assert len(_LEGAL_AREAS_ENUM) >= 5

    def test_enum_includes_key_areas(self) -> None:
        for required in ("sozialrecht", "erbrecht", "schenkungsrecht",
                         "familienrecht", "andere"):
            assert required in _LEGAL_AREAS_ENUM


# ---------------------------------------------------------------------------
# 2. _normalise_area
# ---------------------------------------------------------------------------


class TestNormaliseArea:
    @pytest.mark.parametrize("area", [
        "sozialrecht", "erbrecht", "schenkungsrecht",
        "familienrecht", "mietrecht", "arbeitsrecht",
        "vertragsrecht", "verwaltungsrecht", "strafrecht", "andere",
    ])
    def test_canonical_values_pass_through(self, area: str) -> None:
        assert _normalise_area(area) == area

    def test_uppercase_normalises(self) -> None:
        assert _normalise_area("ERBRECHT") == "erbrecht"
        assert _normalise_area("Sozialrecht") == "sozialrecht"

    def test_whitespace_stripped(self) -> None:
        assert _normalise_area("  erbrecht  ") == "erbrecht"

    def test_synonym_erbschaft(self) -> None:
        assert _normalise_area("Erbschaft") == "erbrecht"

    def test_synonym_schenken(self) -> None:
        assert _normalise_area("schenken") == "schenkungsrecht"

    def test_synonym_scheidungsrecht(self) -> None:
        assert _normalise_area("Scheidungsrecht") == "familienrecht"

    def test_synonym_substring(self) -> None:
        # "Erbschaftsteuer" contains "Erbschaft" → erbrecht
        assert _normalise_area("Erbschaftsteuer") == "erbrecht"

    def test_none_returns_none(self) -> None:
        assert _normalise_area(None) is None

    def test_empty_returns_none(self) -> None:
        assert _normalise_area("") is None

    def test_garbage_returns_none(self) -> None:
        assert _normalise_area("xyzzy_unknown") is None


# ---------------------------------------------------------------------------
# 3. _fallback_areas_from_text
# ---------------------------------------------------------------------------


class TestFallbackAreas:
    def test_empty_text_falls_back_to_andere(self) -> None:
        primary, secondary = _fallback_areas_from_text("")
        assert primary == "andere"
        assert secondary == []

    def test_erbrecht_keywords(self) -> None:
        primary, _ = _fallback_areas_from_text(
            "Mein Vater ist verstorben und ich brauche einen Erbschein."
        )
        assert primary == "erbrecht"

    def test_sozialrecht_keywords(self) -> None:
        primary, _ = _fallback_areas_from_text(
            "Mein Jobcenter hat mir das Bürgergeld gestrichen."
        )
        assert primary == "sozialrecht"

    def test_familienrecht_keywords(self) -> None:
        primary, _ = _fallback_areas_from_text(
            "Meine Scheidung ist eingereicht und es geht um Unterhalt."
        )
        assert primary == "familienrecht"

    def test_mietrecht_keywords(self) -> None:
        primary, _ = _fallback_areas_from_text(
            "Mein Vermieter hat mir die Wohnung gekündigt."
        )
        assert primary == "mietrecht"

    def test_arbeitsrecht_keywords(self) -> None:
        primary, _ = _fallback_areas_from_text(
            "Mein Arbeitgeber hat mir fristlos gekündigt. Abfindung?"
        )
        assert primary == "arbeitsrecht"

    def test_schenkungsrecht_keywords(self) -> None:
        primary, _ = _fallback_areas_from_text(
            "Ich will meinem Kind das Haus schenken — welche Steuern fallen an?"
        )
        assert primary == "schenkungsrecht"

    def test_secondary_areas_present(self) -> None:
        # Combined case: Erbe + Scheidung → erbrecht + familienrecht
        primary, secondary = _fallback_areas_from_text(
            "Mein geschiedener Mann ist verstorben — steht mir ein Pflichtteil zu?"
        )
        assert primary == "erbrecht"
        assert "familienrecht" in secondary

    def test_no_keywords_returns_andere(self) -> None:
        primary, _ = _fallback_areas_from_text(
            "Lorem ipsum dolor sit amet, consectetur adipiscing elit."
        )
        assert primary == "andere"

    def test_case_insensitive(self) -> None:
        primary, _ = _fallback_areas_from_text(
            "Mein VERMIETER hat MIR GEKÜNDIGT."
        )
        assert primary == "mietrecht"


# ---------------------------------------------------------------------------
# 4. build_intake_messages
# ---------------------------------------------------------------------------


class TestBuildMessages:
    def test_basic_structure(self) -> None:
        msgs = build_intake_messages("Mein Fall ist X.")
        assert len(msgs) == 2
        assert msgs[0]["role"] == "system"
        assert msgs[1]["role"] == "user"
        # System prompt includes the closed enum.
        for area in _LEGAL_AREAS_ENUM:
            assert area in msgs[0]["content"]
        # User prompt contains the initial text.
        assert "Mein Fall ist X." in msgs[1]["content"]

    def test_user_prompt_includes_history(self) -> None:
        msgs = build_intake_messages(
            "Initial",
            history=[
                {"role": "assistant", "content": "Sind Sie verheiratet?"},
                {"role": "user", "content": "Ja, seit 10 Jahren."},
            ],
        )
        user = msgs[1]["content"]
        assert "Sind Sie verheiratet?" in user
        assert "Ja, seit 10 Jahren." in user

    def test_initial_text_truncation(self) -> None:
        big = "A" * 10_000
        msgs = build_intake_messages(big)
        # The user content must be smaller than 10_000 (trimmed).
        assert len(msgs[1]["content"]) < 10_000


# ---------------------------------------------------------------------------
# 5. _parse_intake_response
# ---------------------------------------------------------------------------


class TestParseIntakeResponse:
    def test_clean_json(self) -> None:
        raw = '{"done": false, "question": "Was ist passiert?"}'
        result = _parse_intake_response(raw)
        assert result["done"] is False
        assert result["question"] == "Was ist passiert?"

    def test_json_in_prose(self) -> None:
        raw = 'Hier ist die Antwort: {"done": true, "primary_area": "erbrecht"}'
        result = _parse_intake_response(raw)
        assert result["done"] is True
        assert result["primary_area"] == "erbrecht"

    def test_markdown_fenced(self) -> None:
        raw = '```json\n{"done": false, "question": "X"}\n```'
        result = _parse_intake_response(raw)
        assert result["done"] is False

    def test_no_json_raises(self) -> None:
        with pytest.raises(IntakeError):
            _parse_intake_response("This response contains no JSON object at all")

    def test_unbalanced_braces_raises(self) -> None:
        with pytest.raises(IntakeError):
            _parse_intake_response('{"done": false, "question": "X"')

    def test_array_at_root(self) -> None:
        # Arrays are not supported, but the parser will at least
        # return a non-dict without raising (the caller validates).
        raw = '[{"x": 1}]'
        result = _parse_intake_response(raw)
        # json.loads accepts arrays too.
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# 6. AREA_KEYWORDS sanity
# ---------------------------------------------------------------------------


class TestAreaKeywords:
    def test_keywords_cover_all_enum(self) -> None:
        # "andere" is the explicit fallback and intentionally has no
        # keywords (the LLM picks it when nothing else fits).
        for area in _LEGAL_AREAS_ENUM:
            if area == "andere":
                continue
            assert area in _AREA_KEYWORDS, f"missing keywords for {area}"
