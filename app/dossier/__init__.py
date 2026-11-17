"""Appointment dossier (Mandatsvorbereitungs-Dossier) — roadmap P10.

Domain-neutral core service (ARCHITECTURE.md § 3.7): chronology builder
(WP-101), module dossier content and merge (WP-102), generator and JSON/PDF
export (WP-103) against the versioned schema ``citizen-dossier-v1.0``
(WP-100). Area knowledge comes from each module's ``dossier.yaml`` and
``fristen.yaml``; this package holds none.
"""

# Semantic Version: 1.0.0 | 2026-11-16 — P10 initial (WP-100…WP-103).

from app.dossier.builder import (
    DOSSIER_SCHEMA_VERSION,
    DossierInputs,
    build_dossier,
    validate_dossier,
)

__all__ = ["DOSSIER_SCHEMA_VERSION", "DossierInputs", "build_dossier", "validate_dossier"]
