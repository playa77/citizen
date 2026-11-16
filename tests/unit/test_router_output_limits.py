"""Router output limits (CR-03, F-02): max_tokens, JSON mode, truncation."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import httpx
import pytest

from app.core import router as router_mod
from app.core.router import OpenRouterClient, TruncatedResponseError

_MESSAGES = [{"role": "user", "content": "x"}]


def _response(content: str, finish_reason: str | None = "stop") -> httpx.Response:
    body = {
        "choices": [{"message": {"content": content}, "finish_reason": finish_reason}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
    }
    return httpx.Response(
        200, request=httpx.Request("POST", "https://example.com"), content=json.dumps(body).encode()
    )


@pytest.fixture
def http() -> AsyncMock:
    return AsyncMock(spec=httpx.AsyncClient)


async def test_optional_fields_absent_by_default(http: AsyncMock) -> None:
    http.post.return_value = _response("ok")
    await OpenRouterClient(client=http).chat_completion(_MESSAGES, model="m")
    payload = http.post.call_args.kwargs["json"]
    assert "max_tokens" not in payload
    assert "response_format" not in payload


async def test_max_tokens_sent(http: AsyncMock) -> None:
    http.post.return_value = _response("ok")
    await OpenRouterClient(client=http).chat_completion(_MESSAGES, model="m", max_tokens=123)
    assert http.post.call_args.kwargs["json"]["max_tokens"] == 123


@pytest.mark.parametrize("enabled", [True, False])
async def test_response_format_gated_on_json_mode(
    http: AsyncMock, monkeypatch: pytest.MonkeyPatch, enabled: bool
) -> None:
    monkeypatch.setattr(router_mod, "_json_mode_enabled", lambda: enabled)
    http.post.return_value = _response("{}")
    await OpenRouterClient(client=http).chat_completion(
        _MESSAGES, model="m", response_format={"type": "json_object"}
    )
    assert ("response_format" in http.post.call_args.kwargs["json"]) is enabled


async def test_truncation_retries_once_with_double_budget(http: AsyncMock) -> None:
    http.post.side_effect = [_response('{"a"', "length"), _response('{"a": 1}')]
    result = await OpenRouterClient(client=http).chat_completion(
        _MESSAGES, model="m", max_tokens=100, max_retries=1
    )
    assert result == '{"a": 1}'
    budgets = [c.kwargs["json"]["max_tokens"] for c in http.post.call_args_list]
    assert budgets == [100, 200]


async def test_truncation_twice_raises(http: AsyncMock) -> None:
    http.post.side_effect = [_response("{", "length"), _response("{", "length")]
    with pytest.raises(TruncatedResponseError) as err:
        await OpenRouterClient(client=http).chat_completion(_MESSAGES, model="m", max_tokens=50)
    assert err.value.max_tokens == 100


async def test_uncapped_length_stop_returns_content(http: AsyncMock) -> None:
    http.post.return_value = _response("partial", "length")
    assert await OpenRouterClient(client=http).chat_completion(_MESSAGES, model="m") == "partial"
