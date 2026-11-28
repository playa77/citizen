"""Public module catalog views (WP-95 helpers, shared since WP-116).

What ``GET /api/v1/modules/{id}`` and the read-only MCP server
(``app/mcp``) serve about a module: deadline catalog, document types,
public compliance facts, scope. Only public manifest parts — never file
paths or code references.
"""

# Semantic Version: 1.0.0 | 2026-11-17 — extracted from app/api/routes/modules.py 1.1.0.

from __future__ import annotations

from typing import Any

import jsonschema

from app.fristen.specs import DeadlineSpec, Duration
from app.modules.content import load_section
from app.modules.registry import ModuleManifest
from app.modules.runtime import deadline_specs, document_templates


def public_intake_schema(manifest: ModuleManifest) -> dict[str, Any] | None:
    """Return validated module-owned form data, without exposing its file path."""
    data = load_section(manifest, "intake_schema")
    if data is None:
        return None
    if not isinstance(data, dict):
        raise ValueError("intake_schema must be a JSON Schema mapping")
    jsonschema.Draft202012Validator.check_schema(data)
    return data


def duration_dict(duration: Duration) -> dict[str, int]:
    return {"days": duration.days, "months": duration.months, "years": duration.years}


def deadline_entry(spec: DeadlineSpec) -> dict[str, Any]:
    return {
        "id": spec.id,
        "label_de": spec.label_de,
        "trigger": spec.trigger,
        "duration": duration_dict(spec.duration),
        "basis": spec.basis,
        "fristbeginn_basis": spec.fristbeginn_basis,
        "bekanntgabe_fiction": spec.bekanntgabe_fiction,
        "rollover": spec.rollover,
        "missing_rechtsbehelfsbelehrung": (
            {
                "duration": duration_dict(spec.missing_rechtsbehelfsbelehrung.duration),
                "basis": spec.missing_rechtsbehelfsbelehrung.basis,
            }
            if spec.missing_rechtsbehelfsbelehrung is not None
            else None
        ),
        "severity": spec.severity,
        "applies_when": dict(spec.applies_when),
    }


def document_types(manifest: ModuleManifest) -> list[dict[str, Any]]:
    """Declared action-draft types with their template titles (if any)."""
    templates = (document_templates(manifest.id) or {}).get("templates") or {}
    result: list[dict[str, Any]] = []
    for doc_id in manifest.raw.get("documents") or []:
        template = templates.get(doc_id) or {}
        result.append({"id": doc_id, "title": template.get("title")})
    return result


def public_compliance(manifest: ModuleManifest) -> dict[str, Any] | None:
    """Public compliance facts (referral duty, special regimes); no file paths."""
    compliance = manifest.raw.get("compliance")
    if not isinstance(compliance, dict):
        return None
    referral = compliance.get("referral")
    return {
        "special_regimes": list(compliance.get("special_regimes") or []),
        "referral": dict(referral) if isinstance(referral, dict) else None,
    }


def public_scope(manifest: ModuleManifest) -> dict[str, Any]:
    scope = manifest.raw.get("scope") or {}
    return {
        "summary_de": scope.get("summary_de"),
        "own_matter_only": scope.get("own_matter_only"),
        "out_of_scope": list(scope.get("out_of_scope") or []),
        **(
            {"third_party_assistance": scope["third_party_assistance"]}
            if "third_party_assistance" in scope
            else {}
        ),
    }


def module_deadlines(module_id: str) -> list[dict[str, Any]]:
    return [deadline_entry(spec) for spec in deadline_specs(module_id)]


__all__ = [
    "deadline_entry",
    "document_types",
    "duration_dict",
    "module_deadlines",
    "public_compliance",
    "public_scope",
]
