"""Unit tests for WP-011: Reasoning Engine Prompts & JSON Parsing.

Covers
------
- ``app.services.reasoning`` — prompt construction, JSON parsing retry,
  output validation, edge cases for all 5 reasoning functions.

Acceptance criteria
-------------------
- ``test_json_parsing`` — mocks malformed LLM output, verifies retry.
- Output of ``generate_output`` contains mandatory keys: ``sachverhalt``,
  ``rechtliche_wuerdigung``, ``ergebnis``, ``handlungsempfehlung``,
  ``entwurf``, ``unsicherheiten``.
- ``mypy app/services/reasoning.py`` returns 0 errors.
"""

from __future__ import annotations

import json
from typing import ClassVar
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from app.services.reasoning import (
    JSONParseError,
    _parse_json_response,
    classify_issues,
    construct_claims,
    decompose_questions,
    generate_output,
    reset_client,
    verify_claims,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SAMPLE_TEXT = (
    "Sehr geehrte Damen und Herren,\n\nhiermit widerspreche ich dem "
    "Bewilligungsbescheid vom 01.03.2025. Die Kosten der Unterkunft wurden "
    "unzureichend berücksichtigt. Ich bitte um Überprüfung gemäß § 22 SGB II.\n\n"
    "Mit freundlichen Grüßen\nMax Mustermann"
)

_SAMPLE_CHUNKS: list[dict[str, str]] = [
    {
        "hierarchy_path": "SGB II > § 22 > Abs. 1",
        "text_content": (
            "Leistungen für Unterkunft und Heizung werden in Höhe der "
            "tatsächlichen Aufwendungen erbracht, soweit diese angemessen sind."
        ),
    },
    {
        "hierarchy_path": "SGB II > § 22 > Abs. 2",
        "text_content": (
            "Für die Angemessenheit der Aufwendungen sind die Verhältnisse "
            "im Einzelfall zu berücksichtigen."
        ),
    },
]

_VALID_OUTPUT_JSON = json.dumps(
    {
        "sachverhalt": "Der Antragsteller widerspricht dem Bewilligungsbescheid.",
        "rechtliche_wuerdigung": "Gemäß § 22 Abs. 1 SGB II sind die Kosten zu prüfen.",
        "ergebnis": "Der Widerspruch ist teilweise begründet.",
        "handlungsempfehlung": "Belege für die Wohnkosten nachreichen.",
        "entwurf": "Sehr geehrte Damen und Herren, ...",
        "unsicherheiten": "Fehlende Angaben zum Haushaltseinkommen.",
    }
)


def _make_mock_response(content: str) -> AsyncMock:
    """Return an AsyncMock that resolves to the given string."""
    m = AsyncMock()
    m.chat_completion = AsyncMock(return_value=content)
    return m


@pytest.fixture(autouse=True)
def reset_module_client() -> None:
    """Ensure each test starts with a fresh ``_client`` = None."""
    reset_client()
    yield
    reset_client()


# ===========================================================================
# 1. _parse_json_response — happy path and edge cases
# ===========================================================================


class TestParseJsonResponse:
    def test_valid_json_object(self) -> None:
        raw = '{"issues": ["SGB II", "KdU"]}'
        result = _parse_json_response(raw, context="test")
        assert result == {"issues": ["SGB II", "KdU"]}

    def test_valid_json_array(self) -> None:
        raw = '[{"claim_text": "test", "confidence_score": 0.8}]'
        result = _parse_json_response(raw, context="test")
        assert result == [{"claim_text": "test", "confidence_score": 0.8}]

    def test_whitespace_stripped(self) -> None:
        raw = '  { "ok": true }  \n'
        result = _parse_json_response(raw, context="test")
        assert result == {"ok": True}

    def test_markdown_fence_opening_stripped(self) -> None:
        raw = '```json\n{"key": "value"}\n```'
        result = _parse_json_response(raw, context="test")
        assert result == {"key": "value"}

    def test_markdown_fence_without_language(self) -> None:
        raw = '```\n{"a": 1}\n```'
        result = _parse_json_response(raw, context="test")
        assert result == {"a": 1}

    def test_malformed_raises_json_parse_error(self) -> None:
        raw = "This is not JSON at all."
        with pytest.raises(JSONParseError, match="malformed JSON"):
            _parse_json_response(raw, context="unit test")

    def test_partial_json_raises(self) -> None:
        raw = '{"incomplete": '
        with pytest.raises(JSONParseError):
            _parse_json_response(raw, context="partial")

    def test_error_message_is_truncated(self) -> None:
        long_text = "x" * 1000
        raw = f'{{"data": "{long_text}"}}'  # valid JSON — should not raise
        result = _parse_json_response(raw, context="truncate test")
        assert result == {"data": long_text}


# ===========================================================================
# 2. classify_issues
# ===========================================================================


class TestClassifyIssues:
    @pytest_asyncio.fixture(autouse=True)
    async def _patch_client(self) -> None:
        """Patch ``_get_client`` to return a mock with valid JSON."""
        self._patcher = patch(
            "app.services.reasoning._get_client",
            return_value=_make_mock_response(json.dumps({"issues": ["KdU", "Meldefrist"]})),
        )
        self._patcher.start()
        yield
        self._patcher.stop()

    async def test_returns_list_of_strings(self) -> None:
        result = await classify_issues(_SAMPLE_TEXT)
        assert result == ["KdU", "Meldefrist"]

    async def test_empty_issues_returns_empty_list(self) -> None:
        patch(
            "app.services.reasoning._get_client",
            return_value=_make_mock_response(json.dumps({"issues": []})),
        ).start()
        result = await classify_issues(_SAMPLE_TEXT)
        assert result == []

    async def test_non_list_issues_returns_empty(self) -> None:
        patch(
            "app.services.reasoning._get_client",
            return_value=_make_mock_response(json.dumps({"issues": "not a list"})),
        ).start()
        result = await classify_issues(_SAMPLE_TEXT)
        assert result == []

    async def test_strips_empty_entries(self) -> None:
        patch(
            "app.services.reasoning._get_client",
            return_value=_make_mock_response(json.dumps({"issues": ["  ", "KdU", ""]})),
        ).start()
        result = await classify_issues(_SAMPLE_TEXT)
        assert result == ["KdU"]


# ===========================================================================
# 3. decompose_questions
# ===========================================================================


class TestDecomposeQuestions:
    @pytest_asyncio.fixture(autouse=True)
    async def _patch_client(self) -> None:
        self._patcher = patch(
            "app.services.reasoning._get_client",
            return_value=_make_mock_response(
                json.dumps({"questions": ["Ist § 22 anwendbar?", "Wie hoch ist der Regelsatz?"]})
            ),
        )
        self._patcher.start()
        yield
        self._patcher.stop()

    async def test_returns_list_of_questions(self) -> None:
        result = await decompose_questions(_SAMPLE_TEXT)
        assert len(result) == 2
        assert "Ist § 22 anwendbar?" in result

    async def test_empty_questions_returns_empty_list(self) -> None:
        patch(
            "app.services.reasoning._get_client",
            return_value=_make_mock_response(json.dumps({"questions": []})),
        ).start()
        result = await decompose_questions(_SAMPLE_TEXT)
        assert result == []

    async def test_non_list_returns_empty(self) -> None:
        patch(
            "app.services.reasoning._get_client",
            return_value=_make_mock_response(json.dumps({"questions": "single question"})),
        ).start()
        result = await decompose_questions(_SAMPLE_TEXT)
        assert result == []


# ===========================================================================
# 4. construct_claims
# ===========================================================================


class TestConstructClaims:
    @pytest_asyncio.fixture(autouse=True)
    async def _patch_client(self) -> None:
        claims_payload = [
            {
                "claim_text": "Aufwendungen sind angemessen.",
                "confidence_score": 0.8,
                "claim_type": "fact",
                "question": "Ist § 22 anwendbar?",
            },
            {
                "claim_text": "Prüfung der Verhältnisse erforderlich.",
                "confidence_score": 0.6,
                "claim_type": "interpretation",
                "question": "Wie wird Angemessenheit bestimmt?",
            },
        ]
        self._patcher = patch(
            "app.services.reasoning._get_client",
            return_value=_make_mock_response(json.dumps(claims_payload)),
        )
        self._patcher.start()
        yield
        self._patcher.stop()

    async def test_returns_validated_claims(self) -> None:
        result = await construct_claims(_SAMPLE_CHUNKS, ["Ist § 22 anwendbar?"])
        assert len(result) == 2
        assert result[0]["claim_text"] == "Aufwendungen sind angemessen."
        assert result[0]["confidence_score"] == 0.8
        assert result[0]["claim_type"] == "fact"

    async def test_clamps_confidence_out_of_range(self) -> None:
        invalid = [
            {
                "claim_text": "test",
                "confidence_score": 1.5,
                "claim_type": "fact",
                "question": "q",
            }
        ]
        patch(
            "app.services.reasoning._get_client",
            return_value=_make_mock_response(json.dumps(invalid)),
        ).start()
        result = await construct_claims([], [])
        assert result[0]["confidence_score"] == 1.0  # clamped

    async def test_defaults_invalid_claim_type(self) -> None:
        invalid = [
            {
                "claim_text": "test",
                "confidence_score": 0.5,
                "claim_type": "bogus",
                "question": "q",
            }
        ]
        patch(
            "app.services.reasoning._get_client",
            return_value=_make_mock_response(json.dumps(invalid)),
        ).start()
        result = await construct_claims([], [])
        assert result[0]["claim_type"] == "fact"

    async def test_non_dict_items_skipped(self) -> None:
        patch(
            "app.services.reasoning._get_client",
            return_value=_make_mock_response(json.dumps(["string item", 42])),
        ).start()
        result = await construct_claims([], [])
        assert result == []

    async def test_non_list_response_returns_empty(self) -> None:
        patch(
            "app.services.reasoning._get_client",
            return_value=_make_mock_response(json.dumps({"unexpected": "object"})),
        ).start()
        result = await construct_claims([], [])
        assert result == []

    async def test_confidence_nan_becomes_default(self) -> None:
        invalid = [
            {
                "claim_text": "x",
                "confidence_score": "not_a_number",
                "claim_type": "recommendation",
                "question": "q",
            }
        ]
        patch(
            "app.services.reasoning._get_client",
            return_value=_make_mock_response(json.dumps(invalid)),
        ).start()
        result = await construct_claims([], [])
        assert result[0]["confidence_score"] == 0.5


# ===========================================================================
# 5. verify_claims
# ===========================================================================


class TestVerifyClaims:
    VALID_RESPONSE: ClassVar[list[dict]] = [
        {
            "claim_text": "Aufwendungen sind angemessen.",
            "confidence_score": 0.7,
            "claim_type": "fact",
            "verified": True,
            "reasoning": "Gestützt durch SGB II § 22 Abs. 1.",
        }
    ]

    @pytest_asyncio.fixture(autouse=True)
    async def _patch_client(self) -> None:
        self._patcher = patch(
            "app.services.reasoning._get_client",
            return_value=_make_mock_response(json.dumps(self.VALID_RESPONSE)),
        )
        self._patcher.start()
        yield
        self._patcher.stop()

    async def test_returns_verified_claims(self) -> None:
        claims = [
            {
                "claim_text": "Aufwendungen sind angemessen.",
                "confidence_score": 0.8,
                "claim_type": "fact",
            }
        ]
        result = await verify_claims(claims, _SAMPLE_CHUNKS)
        assert len(result) == 1
        assert result[0]["verified"] is True
        assert "reasoning" in result[0]

    async def test_empty_claims_returns_empty(self) -> None:
        result = await verify_claims([], _SAMPLE_CHUNKS)
        assert result == []

    async def test_non_list_response_returns_defaults(self) -> None:
        patch(
            "app.services.reasoning._get_client",
            return_value=_make_mock_response(json.dumps({"unexpected": "object"})),
        ).start()
        claims = [{"claim_text": "test", "confidence_score": 0.5, "claim_type": "fact"}]
        result = await verify_claims(claims, _SAMPLE_CHUNKS)
        assert len(result) == 1
        assert result[0]["verified"] is False
        assert "Verification failed" in result[0]["reasoning"]

    async def test_malformed_confidence_handled(self) -> None:
        invalid = [
            {
                "claim_text": "t",
                "confidence_score": None,
                "claim_type": "fact",
                "verified": True,
                "reasoning": "ok",
            }
        ]
        patch(
            "app.services.reasoning._get_client",
            return_value=_make_mock_response(json.dumps(invalid)),
        ).start()
        claims = [{"claim_text": "x", "confidence_score": 0.5, "claim_type": "fact"}]
        result = await verify_claims(claims, _SAMPLE_CHUNKS)
        assert result[0]["confidence_score"] == 0.5


# ===========================================================================
# 6. generate_output
# ===========================================================================


class TestGenerateOutput:
    @pytest_asyncio.fixture(autouse=True)
    async def _patch_client(self) -> None:
        self._patcher = patch(
            "app.services.reasoning._get_client",
            return_value=_make_mock_response(_VALID_OUTPUT_JSON),
        )
        self._patcher.start()
        yield
        self._patcher.stop()

    async def test_all_six_keys_present(self) -> None:
        verified_claims = [
            {"claim_text": "test", "confidence_score": 0.8, "claim_type": "fact", "verified": True}
        ]
        result = await generate_output(verified_claims)
        expected_keys = {
            "sachverhalt",
            "rechtliche_wuerdigung",
            "ergebnis",
            "handlungsempfehlung",
            "entwurf",
            "unsicherheiten",
        }
        assert set(result.keys()) == expected_keys

    async def test_all_values_are_strings(self) -> None:
        verified_claims = [
            {"claim_text": "test", "confidence_score": 0.8, "claim_type": "fact", "verified": True}
        ]
        result = await generate_output(verified_claims)
        for v in result.values():
            assert isinstance(v, str)

    async def test_missing_keys_default_to_empty_string(self) -> None:
        patch(
            "app.services.reasoning._get_client",
            return_value=_make_mock_response(json.dumps({"sachverhalt": "only this key"})),
        ).start()
        result = await generate_output([])
        assert result["sachverhalt"] == "only this key"
        assert result["rechtliche_wuerdigung"] == ""
        assert result["ergebnis"] == ""

    async def test_non_dict_response_handled(self) -> None:
        """A response that is a plain string (not a JSON object) should yield
        all empty-string defaults."""
        patch(
            "app.services.reasoning._get_client",
            return_value=_make_mock_response('"just a string"'),
        ).start()
        result = await generate_output([])
        for v in result.values():
            assert v == ""


# ===========================================================================
# 7. JSON parsing retry (malformed → retry)
# ===========================================================================


class TestJSONParsingRetry:
    """Verify that a malformed LLM response triggers a second call with a
    stricter prompt."""

    async def test_classify_issues_retry_on_malformed_json(self) -> None:
        """First call returns non-JSON; second call succeeds."""
        mock = AsyncMock()
        mock.chat_completion = AsyncMock(
            side_effect=[
                "This is not JSON",
                json.dumps({"issues": ["retry worked"]}),
            ]
        )
        with patch("app.services.reasoning._get_client", return_value=mock):
            result = await classify_issues(_SAMPLE_TEXT)

        assert mock.chat_completion.call_count == 2
        assert result == ["retry worked"]

    async def test_decompose_questions_retry_on_malformed_json(self) -> None:
        mock = AsyncMock()
        mock.chat_completion = AsyncMock(
            side_effect=[
                "nope",
                json.dumps({"questions": ["retried question"]}),
            ]
        )
        with patch("app.services.reasoning._get_client", return_value=mock):
            result = await decompose_questions(_SAMPLE_TEXT)

        assert mock.chat_completion.call_count == 2
        assert result == ["retried question"]

    async def test_construct_claims_retry_on_malformed_json(self) -> None:
        mock = AsyncMock()
        mock.chat_completion = AsyncMock(
            side_effect=[
                "garbage",
                json.dumps(
                    [
                        {
                            "claim_text": "retry claim",
                            "confidence_score": 0.7,
                            "claim_type": "fact",
                            "question": "q",
                        }
                    ]
                ),
            ]
        )
        with patch("app.services.reasoning._get_client", return_value=mock):
            result = await construct_claims(_SAMPLE_CHUNKS, ["q"])

        assert mock.chat_completion.call_count == 2
        assert result[0]["claim_text"] == "retry claim"

    async def test_verify_claims_retry_on_malformed_json(self) -> None:
        mock = AsyncMock()
        mock.chat_completion = AsyncMock(
            side_effect=[
                "not json",
                json.dumps(
                    [
                        {
                            "claim_text": "verified after retry",
                            "confidence_score": 0.6,
                            "claim_type": "fact",
                            "verified": True,
                            "reasoning": "ok",
                        }
                    ]
                ),
            ]
        )
        claims = [{"claim_text": "x", "confidence_score": 0.5, "claim_type": "fact"}]
        with patch("app.services.reasoning._get_client", return_value=mock):
            result = await verify_claims(claims, _SAMPLE_CHUNKS)

        assert mock.chat_completion.call_count == 2
        assert result[0]["claim_text"] == "verified after retry"

    async def test_generate_output_retry_on_malformed_json(self) -> None:
        mock = AsyncMock()
        mock.chat_completion = AsyncMock(
            side_effect=[
                "broken{}",
                _VALID_OUTPUT_JSON,
            ]
        )
        with patch("app.services.reasoning._get_client", return_value=mock):
            result = await generate_output([])

        assert mock.chat_completion.call_count == 2
        assert "sachverhalt" in result


# ===========================================================================
# 8. reset_client helper
# ===========================================================================


class TestResetClient:
    def test_reset_sets_client_to_none(self) -> None:
        from app.services import reasoning

        reasoning._client = AsyncMock()
        assert reasoning._client is not None
        reset_client()
        assert reasoning._client is None


# ===========================================================================
# 9. JSONParseError class
# ===========================================================================


class TestJSONParseErrorClass:
    def test_is_exception_subclass(self) -> None:
        assert issubclass(JSONParseError, Exception)

    def test_accepts_message(self) -> None:
        err = JSONParseError("bad json")
        assert "bad json" in str(err)
