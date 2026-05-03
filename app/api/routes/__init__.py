"""API routes package — re-export submodules for convenient inclusion in main.py."""

from . import analyze, corpus, ingest, meta

__all__ = ["analyze", "corpus", "ingest", "meta"]
