"""API routes package — re-export submodules for convenient inclusion in main.py."""

# Semantic Version: 0.2.0

from . import (
    analyze,
    cases,
    conversations,
    corpus,
    documents,
    eval_reports,
    goldset,
    ingest,
    intake,
    meta,
    presets,
)

__all__ = [
    "analyze",
    "cases",
    "conversations",
    "corpus",
    "documents",
    "eval_reports",
    "goldset",
    "ingest",
    "intake",
    "meta",
    "presets",
]
