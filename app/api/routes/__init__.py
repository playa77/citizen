"""API routes package — re-export submodules for convenient inclusion in main.py."""

from . import analyze, corpus, ingest

__all__ = ["ingest", "analyze", "corpus"]
