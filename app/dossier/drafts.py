"""Draft annex of the dossier (ARCHITECTURE.md § 3.7 item 7).

One action draft from the first case module that ships document templates,
chosen by the module's own selection table from the dossier's critical
deadline. The generic slot renderer (``app/services/document_generators.py``)
leaves every unbound assertion as ``[BITTE PRÜFEN]``; the person decides.
No database access, so the offline dossier eval uses the same code.
"""

# Semantic Version: 1.0.0 | 2026-11-16 — WP-103 initial.

from __future__ import annotations

from datetime import date
from typing import Any

from app.dossier.builder import DraftFactory
from app.fristen.results import FristResult
from app.modules.runtime import document_templates
from app.services.document_generators import generate_document, select_generator


def make_draft_factory(module_id_hint: str | None = None) -> DraftFactory:
    """Draft annex: one draft from the first case module that ships templates.

    The generator's own selection table (module data) picks the draft type
    from the critical deadline; unbound slots stay ``[BITTE PRÜFEN]``.
    """

    def factory(
        frist_result: FristResult | None,
        claims: list[dict[str, Any]],
        deadlines: dict[str, Any],
    ) -> list[dict[str, Any]]:
        module_ids = [
            m for m in [frist_result.module_id if frist_result else None, module_id_hint] if m
        ]
        module_id = next((m for m in module_ids if document_templates(m) is not None), None)
        if module_id is None:
            return []
        draft_claims = [
            {
                "claim_text": c["claim_text"],
                "confidence_score": c["confidence_score"],
                "claim_type": c["claim_type"],
                "verification_status": (
                    "exakt"
                    if any(b["binding_strength"] >= 0.8 for b in c["bindings"])
                    else ("normalisiert" if c["bindings"] else "unverifiziert")
                ),
                "user_adjudication": c.get("user_adjudication") or {},
            }
            for c in claims
        ]
        letter = (deadlines.get("facts_used") or {}).get("bescheid_datum")
        doc_type = select_generator(frist_result, draft_claims, module_id=module_id)
        doc = generate_document(
            doc_type=doc_type,
            frist_result=frist_result,
            reconciliation=[],
            claims=draft_claims,
            bescheid_datum=date.fromisoformat(letter) if letter else None,
            module_id=module_id,
        )
        return [
            {
                "module_id": module_id,
                "document_type": doc.document_type,
                "title": doc.title,
                "rendered_text": doc.rendered_text,
                "review_slots": doc.rendered_text.count("[BITTE PRÜFEN"),
                "warnings": list(doc.warnings),
            }
        ]

    return factory
