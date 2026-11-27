"""WP-100/WP-103/WP-104 — dossier generator, schema, PDF export, goldset gate.

The goldset gate runs here as a test (offline, deterministic): every case of
the Sozialrecht dossier goldset must produce a schema-valid dossier with
100 % deadline completeness, and the aggregate must pass the module's gate.
"""

# Semantic Version: 1.0.0 | 2026-11-16 — P10

from __future__ import annotations

import copy
import json
from typing import Any

import fitz
import jsonschema
import pytest

from app.core.config import settings
from app.dossier.builder import DossierInputs, build_dossier, validate_dossier
from app.dossier.chronology import SourceText
from app.dossier.drafts import make_draft_factory
from app.dossier.pdf import render_pdf
from app.services.disclosure import build_disclosure_and_provenance
from eval import dossier_eval

LETTER = (
    "Jobcenter Essen\nEssen, 06.07.2026\n\nBewilligungsbescheid\n"
    "auf Ihren Weiterbewilligungsantrag vom 15.06.2026 bewillige ich für den "
    "Zeitraum vom 01.08.2026 bis 31.07.2027 Leistungen. Ihr Erwerbseinkommen "
    "wird angerechnet."
)


def _inputs(**overrides: Any) -> DossierInputs:
    disclosure, provenance = build_disclosure_and_provenance(settings, ["sozialrecht"])
    values: dict[str, Any] = {
        "case_id": "case-1",
        "title": "Test",
        "created_at": None,
        "legal_areas": ["sozialrecht"],
        "module_ids": ["sozialrecht"],
        "sources": [SourceText("case_input", "Analysierter Text", LETTER)],
        "revision": 1,
        "generated_at": "2026-11-16T12:00:00+00:00",
        "disclosure": disclosure.model_dump(mode="json"),
        "provenance": provenance.model_dump(mode="json"),
        "disclaimer_version": settings.DISCLAIMER_VERSION,
    }
    values.update(overrides)
    return DossierInputs(**values)


CLAIMS = [
    {
        "claim_id": "c1",
        "claim_text": "Der Freibetrag wurde mit 20 % statt 30 % berechnet.",
        "claim_type": "fact",
        "confidence_score": 0.9,
        "user_adjudication": {"status": "disputed", "note": "Bitte prüfen"},
        "bindings": [
            {"quote_excerpt": "§ 11b Abs. 3", "binding_strength": 0.95, "source": "SGB II"}
        ],
    },
    {
        "claim_id": "c2",
        "claim_text": "Unbelegte Aussage.",
        "claim_type": "interpretation",
        "confidence_score": 0.4,
        "user_adjudication": None,
        "bindings": [],
    },
]


def test_full_dossier_has_all_sections_and_validates() -> None:
    calc = {
        "result": {
            "calculations_found": [
                {
                    "label": "Freibetrag",
                    "relevant_rule": "§ 11b Abs. 3 SGB II",
                    "computed_values": {"deterministic_result": 338.0, "computation_detail": "…"},
                    "document_values": {"extracted_numbers": {"authority": 290.0}},
                    "discrepancy_found": True,
                    "discrepancy_amount_eur": 48.0,
                    "discrepancy_direction": "zulasten",
                    "commentary": "LLM text that must not reach the dossier",
                }
            ],
            "overall_assessment": {"total_discrepancies": 1, "total_amount_eur": 48.0},
        }
    }
    dossier = build_dossier(
        _inputs(claims=CLAIMS, calculation=calc), make_draft_factory("sozialrecht")
    )
    sections = dossier["sections"]
    assert list(sections) == [
        "chronology",
        "document_checklist",
        "deadlines",
        "calculations",
        "evidence",
        "questions",
        "drafts",
        "export",
    ]
    assert sections["deadlines"]["items"][0]["status"] == "provisional"
    assert sections["calculations"]["status"] == "available"
    assert "commentary" not in json.dumps(sections["calculations"])
    assert [e["verification"] for e in sections["evidence"]["items"]] == ["exakt", "unverifiziert"]
    disputed = [q for q in sections["questions"]["items"] if q["origin"] == "disputed_claim"]
    assert len(disputed) == 1 and "Bitte prüfen" in disputed[0]["text_de"]
    assert sections["drafts"]["items"][0]["module_id"] == "sozialrecht"
    assert dossier["provenance"]["modules"][0]["id"] == "sozialrecht"
    assert any("vorläufig" in w for w in dossier["warnings"])


def test_summary_only_calculation_and_no_claims() -> None:
    calc = {"summary": {"calculations_found": 2, "discrepancies": 1, "total_amount_eur": 12.5}}
    dossier = build_dossier(_inputs(calculation=calc))
    section = dossier["sections"]["calculations"]
    assert section["status"] == "summary_only"
    assert section["summary"]["total_discrepancies"] == 1
    assert dossier["sections"]["drafts"]["items"] == []
    assert any("Belege ist leer" in w for w in dossier["warnings"])


def test_module_without_dossier_content_is_reported() -> None:
    dossier = build_dossier(_inputs(module_ids=["sozialrecht", "vertragsrecht"]))
    assert any("vertragsrecht" in w for w in dossier["warnings"])
    assert all(
        i["module_id"] == "sozialrecht" for i in dossier["sections"]["document_checklist"]["items"]
    )


def test_schema_rejects_drift() -> None:
    dossier = build_dossier(_inputs())
    broken = copy.deepcopy(dossier)
    broken["sections"]["deadlines"]["items"][0]["frist_ende"] = "10.08.2026"
    with pytest.raises(jsonschema.ValidationError):
        validate_dossier(broken)
    broken = copy.deepcopy(dossier)
    del broken["provenance"]
    with pytest.raises(jsonschema.ValidationError):
        validate_dossier(broken)


def test_pdf_embeds_json_and_provenance() -> None:
    dossier = build_dossier(_inputs(claims=CLAIMS), make_draft_factory("sozialrecht"))
    data = render_pdf(dossier)
    doc = fitz.open(stream=data, filetype="pdf")
    try:
        assert doc.embfile_names() == ["dossier.json", "provenance.json"]
        assert json.loads(doc.embfile_get("dossier.json")) == dossier
        assert json.loads(doc.embfile_get("provenance.json")) == dossier["provenance"]
        assert json.loads(doc.metadata["keywords"]) == dossier["provenance"]
        first = doc[0].get_text()
        # The deadline banner precedes every numbered section.
        assert first.index("Fristen — bitte zuerst lesen") < first.index("1. Chronologie")
        assert "10.08.2026" in first
        assert all("Art. 50" in page.get_text() for page in doc)
    finally:
        doc.close()


def test_dossier_goldset_gate_passes() -> None:
    content, goldset, base_cases = dossier_eval._load_cases("sozialrecht")
    results = []
    for case in goldset["cases"]:
        metrics, dossier = dossier_eval.evaluate_case("sozialrecht", case, base_cases[case["id"]])
        assert metrics.schema_valid, metrics.errors
        assert metrics.deadline_completeness == 1.0, metrics.missing_deadlines
        results.append(metrics)
    assert len(results) == 12
    agg = dossier_eval.aggregate(results)
    assert dossier_eval.gate(agg, content.gate) == []


def test_eval_metric_definitions() -> None:
    assert dossier_eval.chronology_accuracy(
        [{"date": "2026-01-01", "kind": "a"}, {"date": "2026-01-02", "kind": "b"}],
        [{"date": "2026-01-01", "kind": "a"}, {"date": "2026-01-02", "kind": "c"}],
    )[0] == pytest.approx(1 / 3)
    assert dossier_eval.checklist_recall(["a", "b"], ["a"]) == (0.5, ["b"])
    produced = [
        {"spec_id": "s", "status": "computed", "frist_ende": "2026-01-01", "frist_typ": "monat"}
    ]
    assert (
        dossier_eval.deadline_completeness(
            [{"spec_id": "s", "frist_ende": "2026-01-01"}], produced
        )[0]
        == 1.0
    )
    assert (
        dossier_eval.deadline_completeness(
            [{"spec_id": "s", "frist_ende": "2026-01-02"}], produced
        )[0]
        == 0.0
    )
    assert dossier_eval.gate(
        {
            "schema_valid_rate": 1.0,
            "deadline_completeness": 0.9,
            "checklist_recall": 1.0,
            "chronology_accuracy": 1.0,
        },
        {"deadline_completeness_min": 1.0},
    )
