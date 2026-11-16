"""Case-type presets — composite legal-area packages declared by modules.

The intake LLM is allowed to choose any combination of the supported
``legal_areas`` per case. A *preset* is a sensible default bundle that
the LLM can suggest or the user can pick manually; a preset may span the
areas of several modules.

WP-93: presets are module data (``presets`` in ``modules/<id>/intake.yaml``)
and are listed in area-table order (``app.modules.areas``); the catalog
stays version-controlled with the module that owns it.

The composite for any specific case is composed dynamically by the LLM;
presets are starting points, not restrictions.
"""

# Semantic Version: 0.4.0

from __future__ import annotations

import copy
from typing import Any

from app.modules.areas import area_tables


def _catalog() -> tuple[dict[str, Any], ...]:
    return area_tables().presets


def get_preset(preset_id: str) -> dict[str, Any] | None:
    """Return the preset with the given id, or ``None`` if not found."""
    for preset in _catalog():
        if preset["id"] == preset_id:
            return copy.deepcopy(preset)
    return None


def list_presets() -> list[dict[str, Any]]:
    """Return all presets in declaration order."""
    return copy.deepcopy(list(_catalog()))
