"""Module parameter files → ``legal_parameter`` rows (WP-93; ARCHITECTURE.md § 3.4).

Pure parsing and validation of the YAML files a manifest declares under
``parameters.files``; the database upsert lives in
``scripts/seed_module_parameters.py``. Replaces the hard-coded tuple list of
the former ``scripts/seed_legal_parameters.py``.
"""

# Semantic Version: 0.1.0

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from app.modules.content import load_yaml
from app.modules.registry import ModuleManifest, ModuleManifestError

_REVIEW_STATUSES = frozenset({"verified", "proposed"})
_ALLOWED_FIELDS = frozenset(
    {
        "key",
        "value_numeric",
        "value_json",
        "value_text",
        "unit",
        "valid_from",
        "valid_to",
        "review_status",
        "regime",
        "notes",
        "basis",  # legal citation for reviewers; documentation only, not stored
    }
)


@dataclass(frozen=True)
class ParameterRow:
    """One versioned parameter as stored in ``legal_parameter``."""

    key: str
    domain: str
    value_numeric: float | int | None
    value_json: dict[str, Any] | None
    value_text: str | None
    unit: str | None
    valid_from: date
    valid_to: date | None
    review_status: str
    regime: str | None
    notes: str | None


def _row(entry: Any, domain: str, where: str) -> ParameterRow:
    if not isinstance(entry, dict):
        raise ModuleManifestError(f"{where}: parameter entry is not a mapping")
    unknown = set(entry) - _ALLOWED_FIELDS
    if unknown:
        raise ModuleManifestError(f"{where}: unknown parameter field(s) {sorted(unknown)}")
    key = entry.get("key")
    if not isinstance(key, str) or not key:
        raise ModuleManifestError(f"{where}: parameter without key")
    valid_from = entry.get("valid_from")
    valid_to = entry.get("valid_to")
    bad_to = valid_to is not None and not isinstance(valid_to, date)
    if not isinstance(valid_from, date) or bad_to:
        raise ModuleManifestError(f"{where}: {key}: valid_from/valid_to must be ISO dates")
    if valid_to is not None and valid_to < valid_from:
        raise ModuleManifestError(f"{where}: {key}: valid_to before valid_from")
    status = entry.get("review_status")
    if status not in _REVIEW_STATUSES:
        raise ModuleManifestError(f"{where}: {key}: review_status must be verified|proposed")
    numeric = entry.get("value_numeric")
    if numeric is not None and (isinstance(numeric, bool) or not isinstance(numeric, int | float)):
        raise ModuleManifestError(f"{where}: {key}: value_numeric must be a number")
    value_json = entry.get("value_json")
    if value_json is not None and not isinstance(value_json, dict):
        raise ModuleManifestError(f"{where}: {key}: value_json must be a mapping")
    regime = entry.get("regime")
    return ParameterRow(
        key=key,
        domain=domain,
        value_numeric=numeric,
        value_json=value_json,
        value_text=entry.get("value_text"),
        unit=entry.get("unit"),
        valid_from=valid_from,
        valid_to=valid_to,
        review_status=str(status),
        regime=str(regime) if regime is not None else None,
        notes=entry.get("notes"),
    )


def load_parameter_rows(manifest: ModuleManifest) -> list[ParameterRow]:
    """All parameter rows of *manifest*, in file order; ``[]`` if none declared.

    Duplicate ``(key, valid_from)`` pairs are rejected — they would collide
    on the loader's upsert identity.
    """
    section = manifest.raw.get("parameters")
    if not isinstance(section, dict):
        return []
    domain = str(section["domain"])
    rows: list[ParameterRow] = []
    for pattern in section["files"]:
        for path in sorted(manifest.path.glob(pattern)):
            relative = str(path.relative_to(manifest.path))
            data = load_yaml(manifest, relative)
            entries = data.get("parameters") if isinstance(data, dict) else None
            if not isinstance(entries, list):
                raise ModuleManifestError(f"{manifest.id}/{relative}: missing 'parameters' list")
            rows.extend(_row(e, domain, f"{manifest.id}/{relative}") for e in entries)
    seen: set[tuple[str, date]] = set()
    for row in rows:
        identity = (row.key, row.valid_from)
        if identity in seen:
            raise ModuleManifestError(
                f"module {manifest.id!r}: duplicate parameter {row.key}@{row.valid_from}"
            )
        seen.add(identity)
    return rows


__all__ = ["ParameterRow", "load_parameter_rows"]
