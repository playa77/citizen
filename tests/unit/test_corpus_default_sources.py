"""The ingest default is module data, not a core constant (ARCHITECTURE.md § 8).

``CORPUS_SOURCES`` unset → the ``DEFAULT_MODULE``'s ``corpus.yaml``
``default_ingest_sources``; an explicit list overrides it; a runtime selection
(``.corpus_sources.json``) overrides both.
"""

# Semantic Version: 1.0.0 | 2026-11-16 — WP-97 follow-up (residual coupling).

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from app.core.config import Settings, settings
from app.modules.areas import area_tables
from app.services import corpus
from app.services.corpus import default_corpus_sources, get_effective_corpus_sources


def test_core_config_carries_no_area_default() -> None:
    assert Settings.model_fields["CORPUS_SOURCES"].default is None


def test_sozialrecht_default_is_unchanged() -> None:
    """Behaviour identity with the former ``["sgb2", "sgbx"]`` core default."""
    assert settings.DEFAULT_MODULE == "sozialrecht"
    assert area_tables().default_ingest_sources == ("sgb2", "sgbx")
    with patch.object(settings, "CORPUS_SOURCES", None):
        assert default_corpus_sources() == ["sgb2", "sgbx"]


def test_explicit_setting_overrides_module_default() -> None:
    with patch.object(settings, "CORPUS_SOURCES", ["sgb3"]):
        assert default_corpus_sources() == ["sgb3"]
    assert default_corpus_sources(["sgg"]) == ["sgg"]


async def test_runtime_selection_wins(tmp_path: Path) -> None:
    runtime_file = tmp_path / ".corpus_sources.json"
    with patch.object(corpus, "_CORPUS_SOURCES_FILE", runtime_file):
        assert await get_effective_corpus_sources() == default_corpus_sources()
        corpus.save_runtime_sources(["sgb12"])
        assert await get_effective_corpus_sources() == ["sgb12"]
