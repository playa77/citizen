"""Endpoint prompts of prompt set 3.0.0 (P-09…P-13; CR-05, CR-11, CR-14)."""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.core.config import settings
from app.services.prompts import ModuleSelectionRequired, get_chat_prompt

# ---------------------------------------------------------------------------
# CR-05 — chat personas follow the module profile
# ---------------------------------------------------------------------------


def test_chat_persona_follows_area() -> None:
    soz = get_chat_prompt("chat", ["sozialrecht"])
    erb = get_chat_prompt("chat", ["erbrecht"])
    assert "deutsches Sozialrecht" in soz and "SGB" in soz
    assert "Erbrecht" in erb and "SGB II" not in erb
    with pytest.raises(ModuleSelectionRequired):
        get_chat_prompt("chat")
    merged = get_chat_prompt("case_chat", ["sozialrecht", "erbrecht"])
    assert "deutsches Sozialrecht sowie deutsches Erbrecht" in merged


async def test_generate_chat_response_uses_area_prompt_and_drops_append(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import chat_reasoning

    client = MagicMock()
    client.chat_completion = AsyncMock(return_value="Antwort")
    monkeypatch.setattr(chat_reasoning, "get_shared_client", lambda: client)
    retrieve = AsyncMock(return_value=(
        {"erbrecht": []},
        [{"hierarchy_path": "BGB > § 1922", "text_content": "t"}],
    ))
    monkeypatch.setattr(chat_reasoning, "retrieve_chunks_for_areas", retrieve)
    events = [
        e
        async for e in chat_reasoning.generate_chat_response(
            [{"role": "user", "content": "Frage"}], legal_areas=["erbrecht"]
        )
    ]
    system = client.chat_completion.call_args.args[0][0]["content"]
    assert retrieve.await_args.kwargs["legal_areas"] == ["erbrecht"]
    assert retrieve.await_args.kwargs["client"] is client
    assert system.startswith(get_chat_prompt("chat", ["erbrecht"]))
    assert "Zitiere Paragraphen mit exaktem Wortlaut" not in system
    done = json.loads(events[-1][6:])
    assert [m["id"] for m in done["provenance"]["modules"]] == ["erbrecht"]


# ---------------------------------------------------------------------------
# CR-14 — case-chat context: edits first, visible cuts, own history budget
# ---------------------------------------------------------------------------


def test_case_context_priority_and_cut_markers(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services import case_chat

    # Patch the settings object the module reads (other tests swap instances).
    monkeypatch.setattr(case_chat.settings, "MAX_CHUNK_CONTEXT_CHARS", 900)
    context = case_chat._assemble_case_context(
        {"sachverhalt": "S" * 2000},
        {"ergebnis": "korrigiert"},
        None,
        [{"claim_text": "c", "claim_type": "interpretation", "confidence_score": 0.5}],
    )
    assert context.index("Korrekturen der Person") < context.index("Auszüge der Analyse")
    assert "[… gekürzt]" in context
    assert "[Nicht im Kontext: Claims der Analyse]" in context
    assert "autoritativ" not in context


async def test_case_chat_prompt_follows_case_areas(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services import case_chat

    client = MagicMock()
    client.chat_completion = AsyncMock(return_value="ok")
    monkeypatch.setattr(case_chat, "get_shared_client", lambda: client)
    _ = [
        e
        async for e in case_chat.generate_case_chat_response(
            [{"role": "user", "content": "Warum?"}],
            pipeline_output={"ergebnis": "x"},
            legal_areas=["erbrecht"],
        )
    ]
    kwargs = client.chat_completion.call_args.kwargs
    system = client.chat_completion.call_args.args[0][0]["content"]
    assert system.startswith(get_chat_prompt("case_chat", ["erbrecht"]))
    assert kwargs["temperature"] == 0.1


# ---------------------------------------------------------------------------
# Conversation endpoint — optional legal_areas (additive)
# ---------------------------------------------------------------------------


@pytest.fixture
async def api() -> AsyncGenerator[httpx.AsyncClient, None]:
    from app.main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


@pytest.mark.parametrize(
    ("areas", "status", "code"),
    [(["nope"], 422, "MODULE_UNKNOWN"), ("sozialrecht", 400, None)],
)
async def test_message_legal_areas_validated(
    api: httpx.AsyncClient, areas: Any, status: int, code: str | None
) -> None:
    import uuid

    resp = await api.post(
        f"/api/v1/conversations/{uuid.uuid4()}/messages",
        json={"content": "Hallo", "legal_areas": areas},
        headers={"X-Disclaimer-Ack": settings.DISCLAIMER_VERSION},
    )
    assert resp.status_code == status
    if code:
        assert resp.json()["detail"]["error"] == code


# ---------------------------------------------------------------------------
# CR-11 — preset suggestion
# ---------------------------------------------------------------------------


def _presets_route() -> Any:
    from app.api.routes import presets

    return presets


@pytest.mark.parametrize(
    ("raw", "match", "preset"),
    [
        (
            '```json\n{"preset_id": "erbe-mit-testament", "primary_area": "erbrecht"}\n```',
            "llm",
            "erbe-mit-testament",
        ),
        (
            '{"preset_id": "", "primary_area": "andere", "secondary_areas": []}',
            "keyword_fallback",
            None,
        ),
        ("keine Ahnung", "keyword_fallback", None),
    ],
)
async def test_preset_suggest_match_field(
    monkeypatch: pytest.MonkeyPatch, raw: str, match: str, preset: str | None
) -> None:
    route = _presets_route()

    class _Client:
        def __init__(self) -> None:
            self.chat_completion = AsyncMock(return_value=raw)
            self.close = AsyncMock()

    fake = _Client()
    monkeypatch.setattr(route, "OpenRouterClient", lambda: fake)
    result = await route._call_llm_suggest("Mein Vater hat ein Testament hinterlassen.")
    assert result["match"] == match
    if preset:
        assert result["preset_id"] == preset
    system = fake.chat_completion.call_args.args[0][0]["content"]
    assert 'Passt keine: ""' in system


# ---------------------------------------------------------------------------
# P-09 / P-13
# ---------------------------------------------------------------------------


def test_intake_has_no_escape_hatch_and_valid_example() -> None:
    from app.services.intake import _INTAKE_SYSTEM, _STRICT_SUFFIX

    assert '"done": true' not in _STRICT_SUFFIX and "{" not in _STRICT_SUFFIX
    example = _INTAKE_SYSTEM.split("<ausgabeformat>\n", 1)[1].split("\n\n", 1)[0]
    assert json.loads(example)["done"] is False
    assert "Erstberater" not in _INTAKE_SYSTEM


def test_ocr_synthesis_does_not_correct_wording() -> None:
    from app.services.reasoning import _OCR_SYNTHESIS_SYSTEM

    assert "[OCR unsicher]" in _OCR_SYNTHESIS_SYSTEM
    assert "Rechtschreib- und Grammatikprüfung" not in _OCR_SYNTHESIS_SYSTEM
