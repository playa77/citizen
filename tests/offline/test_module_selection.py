"""D-070 pure module contracts; no settings, database or inference needed.

Run with ``python -m pytest --noconftest tests/offline/test_module_selection.py``.
The application suites continue to use the PostgreSQL fixtures in conftest.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from app.modules import runtime
from app.modules.areas import build_area_tables_from
from app.modules.registry import default_modules_root, discover_modules, load_registry


@pytest.mark.parametrize("scope", [None, []])
def test_empty_scope_selects_no_module(monkeypatch: pytest.MonkeyPatch, scope: list[str] | None) -> None:
    # Resolution must not consult a module table at all for empty selection.
    monkeypatch.setattr(
        runtime, "area_tables", lambda: SimpleNamespace(default_module="sozialrecht", owner={})
    )
    assert runtime.request_modules(scope) == []
    assert runtime.provenance_modules(scope) == []


def test_explicit_scope_preserves_order_aliases_and_procedural_ownership(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(runtime, "area_tables", lambda: SimpleNamespace(owner={
        "erbrecht": "erbrecht", "schenkungsrecht": "erbrecht",
        "sozialrecht": "sozialrecht", "verwaltungsrecht": "core:procedural",
    }))
    assert runtime.request_modules([
        "erbrecht", "schenkungsrecht", "verwaltungsrecht", "sozialrecht", "erbrecht",
    ]) == ["erbrecht", "sozialrecht"]


def test_registry_accepts_no_enabled_module_and_no_sozialrecht(tmp_path: Path) -> None:
    module = tmp_path / "peer"
    module.mkdir()
    (module / "module.yaml").write_text(yaml.safe_dump({
        "id": "peer", "version": "1.0.0", "core_api": ">=3.0,<4.0",
        "tier": "experimental", "title": {"de": "Peer", "en": "Peer"},
    }), encoding="utf-8")
    registry = load_registry(tmp_path, "provider", None)
    assert set(registry.modules) == {"peer"}
    assert registry.enabled == frozenset()


def test_peer_tables_do_not_need_sozialrecht() -> None:
    installed = discover_modules(default_modules_root())
    peers = {mid: manifest for mid, manifest in installed.items() if mid != "sozialrecht"}
    tables = build_area_tables_from(peers)
    assert "sozialrecht" not in tables.owner
    assert tables.owner["erbrecht"] == "erbrecht"
    assert tables.catch_all == "andere"


@pytest.mark.parametrize("scope", [None, [], ["verwaltungsrecht"], ["vertragsrecht"], ["unknown"]])
def test_no_usable_profile_never_borrows_legal_prompts(scope: list[str] | None) -> None:
    from app.services.prompts import ModuleSelectionRequired, get_chat_prompt, get_prompts

    with pytest.raises(ModuleSelectionRequired):
        get_prompts(scope)
    with pytest.raises(ModuleSelectionRequired):
        get_chat_prompt("chat", scope)
    with pytest.raises(ModuleSelectionRequired):
        get_chat_prompt("case_chat", scope)


def test_mixed_profileless_scope_is_not_silently_dropped() -> None:
    from app.services.prompts import ModuleSelectionRequired, get_prompts

    with pytest.raises(ModuleSelectionRequired):
        get_prompts(["sozialrecht", "vertragsrecht"])


def test_inference_scope_surfaces_unavailable_modules_instead_of_replacing_them(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services.prompts import ModuleSelectionRequired, require_inference_scope

    with pytest.raises(ModuleSelectionRequired):
        require_inference_scope([])
    with pytest.raises(ModuleSelectionRequired):
        require_inference_scope(["verwaltungsrecht"])
    monkeypatch.setattr(runtime, "module_registry", lambda: SimpleNamespace(is_enabled=lambda _: False))
    with pytest.raises(runtime.ModuleRequestError) as disabled:
        require_inference_scope(["erbrecht"])
    assert disabled.value.code == "MODULE_NOT_ENABLED"
    with pytest.raises(runtime.ModuleRequestError) as unknown:
        require_inference_scope(["removed-module"])
    assert unknown.value.code == "MODULE_UNKNOWN"


def test_explicit_profile_and_alias_content_is_preserved() -> None:
    from app.services.prompts import get_prompts

    assert get_prompts(["erbrecht"]) == get_prompts(["schenkungsrecht"])
    assert "SGB II" in get_prompts(["sozialrecht"])["classification"]
    assert "mehrere Rechtsgebiete" in get_prompts(["sozialrecht", "erbrecht"])["triage"]


def test_case_templates_require_a_scope_and_disambiguate_explicitly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(runtime, "module_registry", lambda: SimpleNamespace(is_enabled=lambda _: True))
    monkeypatch.setattr(runtime, "get_manifest", lambda mid: SimpleNamespace(
        version="1.0.0", raw={"document_templates": "templates.yaml"},
    ))
    assert runtime.template_module_for(["sozialrecht"]) == "sozialrecht"
    assert runtime.template_module_for(["schenkungsrecht"]) == "erbrecht"
    with pytest.raises(runtime.TemplateModuleSelectionError) as missing:
        runtime.template_module_for([])
    assert missing.value.code == "DOCUMENT_TEMPLATES_UNAVAILABLE"
    with pytest.raises(runtime.TemplateModuleSelectionError) as ambiguous:
        runtime.template_module_for(["sozialrecht", "erbrecht"])
    assert ambiguous.value.code == "DOCUMENT_MODULE_REQUIRED"
    assert ambiguous.value.eligible_modules == ["sozialrecht", "erbrecht"]
    assert runtime.template_module_for(["sozialrecht", "erbrecht"], "erbrecht") == "erbrecht"
    with pytest.raises(runtime.TemplateModuleSelectionError) as outside:
        runtime.template_module_for(["sozialrecht"], "erbrecht")
    assert outside.value.code == "DOCUMENT_MODULE_NOT_IN_SCOPE"


def test_mcp_catalog_has_no_preference_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.mcp.server import handle_message

    installed = discover_modules(default_modules_root())
    registry = SimpleNamespace(
        modules=installed, default_module="sozialrecht", is_enabled=lambda mid: mid == "erbrecht",
        get=installed.get,
    )
    monkeypatch.setattr(runtime, "module_registry", lambda: registry)
    monkeypatch.setitem(
        sys.modules, "app.core.config", SimpleNamespace(get_app_version=lambda: "test")
    )
    reply = asyncio.run(handle_message({
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": "list_modules", "arguments": {}},
    }))
    assert reply is not None
    result = reply["result"]
    assert not result["isError"]
    body = result["structuredContent"]
    assert set(body) == {"modules"}
    assert {entry["id"] for entry in body["modules"]} == set(installed)
    for entry in body["modules"]:
        assert "is_default" not in entry
        assert entry["enabled"] is (entry["id"] == "erbrecht")
    assert json.loads(result["content"][0]["text"]) == body
    for module_id in installed:
        detail_reply = asyncio.run(handle_message({
            "jsonrpc": "2.0", "id": 2, "method": "tools/call",
            "params": {"name": "get_module", "arguments": {"module_id": module_id}},
        }))
        assert detail_reply is not None
        detail_result = detail_reply["result"]
        assert not detail_result["isError"]
        detail = detail_result["structuredContent"]
        assert detail["id"] == module_id
        assert "default_module" not in detail and "is_default" not in detail
        assert json.loads(detail_result["content"][0]["text"]) == detail
