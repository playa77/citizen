"""Suggestion matching with HTTP/inference boundaries replaced, no API calls."""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.modules import runtime
from app.modules.registry import default_modules_root, load_registry


@pytest.fixture
def preset_route(monkeypatch: pytest.MonkeyPatch):
    class Router:
        def get(self, *args: object, **kwargs: object):
            return lambda function: function

        post = get

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("Offline suggestion tests must not create an inference client")

    monkeypatch.setitem(sys.modules, "fastapi", SimpleNamespace(
        APIRouter=Router, Body=lambda *a, **kw: None,
        HTTPException=ValueError, status=SimpleNamespace(),
    ))
    monkeypatch.setitem(sys.modules, "app.core.router", SimpleNamespace(OpenRouterClient=forbidden))
    monkeypatch.setitem(sys.modules, "app.services.reasoning", SimpleNamespace(
        JSONParseError=ValueError, _parse_json_response=forbidden,
    ))
    source = Path(__file__).resolve().parents[2] / "app/api/routes/presets.py"
    spec = importlib.util.spec_from_file_location("citizen_offline_presets", source)
    assert spec is not None and spec.loader is not None
    route = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, route)
    spec.loader.exec_module(route)
    registry = load_registry(default_modules_root(), "dev", None, entry_points=[])
    monkeypatch.setattr(runtime, "module_registry", lambda: registry)
    return route


@pytest.mark.parametrize("text, expected", [
    ("schnickschnack", set()),
    ("jobcenter", {"sozialrecht"}),
    ("jobcenter testament", {"sozialrecht", "erbrecht"}),
])
def test_all_tied_modules_are_suggested_without_choosing_one(
    preset_route, monkeypatch: pytest.MonkeyPatch, text: str, expected: set[str],
) -> None:
    suggestion = preset_route._keyword_suggest(text)
    assert {candidate["primary_area"] for candidate in suggestion["suggestions"]} == expected
    if len(expected) == 1:
        assert suggestion["preset_id"] == "sozialrecht-allgemein"
    else:
        assert suggestion["preset_id"] == ""
        assert suggestion["secondary_areas"] == []

    monkeypatch.setattr(preset_route, "_call_llm_suggest", AsyncMock(return_value=suggestion))
    response = asyncio.run(preset_route.post_suggest_preset({"text": text}))
    assert {entry["module_id"] for entry in response["resolved_modules"]} == expected
    assert response["suggestions"] == suggestion["suggestions"]
