"""Run the real preparation path with external DB/config boundaries replaced.

This does not exercise ASGI or PostgreSQL. It needs no application environment,
API key, model, database or spaCy model; all text is synthetic.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.modules import runtime
from app.modules.registry import default_modules_root, load_registry
from app.services import pseudonymization
from app.utils.text import normalize_text

TEXT = (
    "  Herr Max Mustermann hat ein Schreiben erhalten. "
    "Er möchte das Dokument für einen Termin vorbereiten.  "
)


@pytest.mark.parametrize("scope", [[], ["verwaltungsrecht"], ["mietrecht"], ["sozialrecht", "mietrecht"]])
def test_preparation_keeps_privacy_and_reload_snapshot_without_legal_work(
    monkeypatch: pytest.MonkeyPatch, scope: list[str],
) -> None:
    import app.core

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("Preparation must not access legal inference, retrieval or the DB")

    config = SimpleNamespace(_get_settings=lambda: SimpleNamespace(
        PIPELINE_TIMEOUT_SEC=480,
        OCR_QUALITY_ENABLED=True, OCR_QUALITY_MIN_SCORE=0.3, OCR_QUALITY_WARN_SCORE=0.8,
        PSEUDONYMIZATION_ENABLED=True,
    ))
    monkeypatch.setitem(sys.modules, "app.core.config", config)
    monkeypatch.setattr(app.core, "config", config, raising=False)
    monkeypatch.setitem(sys.modules, "sqlalchemy", SimpleNamespace(func=forbidden, select=forbidden))
    monkeypatch.setitem(sys.modules, "app.db.models", SimpleNamespace(LegalChunk=object))
    monkeypatch.setitem(sys.modules, "app.db.session", SimpleNamespace(get_async_session=forbidden))
    # Exercise the real regex/gazetteer replacement and reinsertion; only NER's
    # optional external model is replaced, as in other synthetic unit fixtures.
    monkeypatch.setattr(pseudonymization, "_get_nlp", lambda: None)
    registry = load_registry(default_modules_root(), "dev", None, entry_points=[])
    monkeypatch.setattr(runtime, "module_registry", lambda: registry)

    source = Path(__file__).resolve().parents[2] / "app/core/pipeline.py"
    spec = importlib.util.spec_from_file_location("citizen_offline_preparation", source)
    assert spec is not None and spec.loader is not None
    pipeline = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, pipeline)
    spec.loader.exec_module(pipeline)
    monkeypatch.setattr(pipeline, "_run_classification_and_decomposition_stages", forbidden)
    monkeypatch.setattr(pipeline, "_stage_retrieval", forbidden)
    monkeypatch.setattr(pipeline, "_run_final_stages", forbidden)

    state = pipeline.PipelineState(input_text=TEXT, legal_areas=scope)

    async def collect() -> list[dict[str, object]]:
        return [json.loads(event.removeprefix("data: ")) async for event in pipeline.run_pipeline(state)]

    events = asyncio.run(collect())
    assert state.pii_mapping["placeholder_to_value"]
    assert "Max Mustermann" not in state.input_text
    assert state.final_output["sachverhalt"] == normalize_text(TEXT)
    assert state.final_output["rechtliche_wuerdigung"] == ""
    assert state.final_output["entwurf"] == ""
    assert not state.prompt_ids and not state.retrieved_chunks and not state.calculation_result
    generation = next(event for event in events if event.get("stage") == "generation")
    assert generation["status"] == "complete"
    assert generation["payload"]["sachverhalt"] == normalize_text(TEXT)
    assert events[-1]["stage"] == "module_selection"
    assert events[-1]["payload"]["error"] == "MODULE_SELECTION_REQUIRED"
