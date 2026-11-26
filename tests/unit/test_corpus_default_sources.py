"""Corpus ingestion requires explicit source configuration (D-070).

Runtime selections override deployment settings, including a saved empty selection.
"""

# Revision: 2026-11-25-r1

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from app.core.config import Settings, settings
from app.services import corpus
from app.services.corpus import default_corpus_sources, get_effective_corpus_sources


def test_core_config_carries_no_area_default() -> None:
    assert Settings.model_fields["CORPUS_SOURCES"].default is None
    assert "DEFAULT_MODULE" not in Settings.model_fields


def test_unconfigured_sources_are_empty() -> None:
    with patch.object(settings, "CORPUS_SOURCES", None):
        assert default_corpus_sources() == []


def test_explicit_setting_and_one_shot_override_are_preserved() -> None:
    with patch.object(settings, "CORPUS_SOURCES", ["sgb3"]):
        assert default_corpus_sources() == ["sgb3"]
        assert default_corpus_sources(["sgg"]) == ["sgg"]
        assert default_corpus_sources([]) == []


async def test_runtime_selection_wins(tmp_path: Path) -> None:
    runtime_file = tmp_path / ".corpus_sources.json"
    with (
        patch.object(corpus, "_CORPUS_SOURCES_FILE", runtime_file),
        patch.object(settings, "CORPUS_SOURCES", ["sgb2"]),
    ):
        assert await get_effective_corpus_sources() == ["sgb2"]
        corpus.save_runtime_sources(["sgb12"])
        assert await get_effective_corpus_sources() == ["sgb12"]


@pytest.mark.parametrize("selected", [[], ["unknown-source"]])
async def test_saved_empty_or_unknown_selection_does_not_fall_back(
    tmp_path: Path, selected: list[str]
) -> None:
    with (
        patch.object(corpus, "_CORPUS_SOURCES_FILE", tmp_path / ".corpus_sources.json"),
        patch.object(settings, "CORPUS_SOURCES", ["sgb2", "sgbx"]),
    ):
        corpus.save_runtime_sources(selected)
        assert corpus.load_runtime_sources() == selected
        assert await get_effective_corpus_sources() == []


async def test_runtime_selection_filters_unknown_without_discarding_known(tmp_path: Path) -> None:
    with (
        patch.object(corpus, "_CORPUS_SOURCES_FILE", tmp_path / ".corpus_sources.json"),
        patch.object(settings, "CORPUS_SOURCES", ["sgbx"]),
    ):
        corpus.save_runtime_sources(["unknown-source", "sgb12"])
        assert await get_effective_corpus_sources() == ["sgb12"]
