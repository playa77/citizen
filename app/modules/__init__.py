"""Citizen module platform (WP-91, D-036).

`app.modules` is the domain-neutral module layer: the typed import surface
for module code (`sdk`), the manifest schema (`manifest.schema.json`,
versioned with the core contract) and the registry (`registry`) that
discovers, validates, enables and resolves modules.

WP-93 adds the content layer: `content` (manifest-declared files and
code references, loaded under the synthetic package `citizen_modules`),
`areas` (area-keyed tables reassembled from module data in v2.0.0 order),
`runtime` (request → modules; calculators, regime providers, templates,
deadline specs) and `parameters` (parameter files → `legal_parameter`
rows). API wiring (`/modules*`, enablement errors) is WP-95.
"""

# Semantic Version: 0.2.0

from pathlib import Path

SCHEMA_PATH = Path(__file__).with_name("manifest.schema.json")
"""Manifest JSON Schema, versioned with the core_api contract (currently 3.0)."""

__all__ = ["SCHEMA_PATH"]
