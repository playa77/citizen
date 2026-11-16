"""Citizen module platform (WP-91, D-036).

`app.modules` is the domain-neutral module layer: the typed import surface
for module code (`sdk`), the manifest schema (`manifest.schema.json`,
versioned with the core contract) and the registry (`registry`) that
discovers, validates, enables and resolves modules.

Pipeline and API wiring is deliberately absent here — that is WP-93 and
WP-95. The only consumer today is app startup validation and the module
import lint (`lint`).
"""

# Semantic Version: 0.1.0

from pathlib import Path

SCHEMA_PATH = Path(__file__).with_name("manifest.schema.json")
"""Manifest JSON Schema, versioned with the core_api contract (currently 3.0)."""

__all__ = ["SCHEMA_PATH"]
