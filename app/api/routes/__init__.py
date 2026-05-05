"""API routes package — re-export submodules for convenient inclusion in main.py."""

# Semantic Version: 0.1.0

from . import analyze, corpus, ingest, meta

__all__ = ["analyze", "corpus", "ingest", "meta"]
