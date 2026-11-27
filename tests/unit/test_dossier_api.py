"""P10 — dossier API (``/cases/{case_id}/dossier*``) against the real database.

Covers the confirmation flow (chronology GET/PUT), building revisions as JSON
and PDF, fetching the latest revision, error codes, cascade on case delete,
``dossier_checklist`` on ``/modules/{id}``, and the analyze-side persistence of
the calculation result the dossier reads (SSE unchanged, final_output
unchanged).

Event-loop discipline as in ``test_disclosure.py``: data is seeded on the
test's loop, the app runs on it via httpx ASGITransport, and the engine pool
is disposed after every test.
"""

# Semantic Version: 1.0.0 | 2026-11-16 — P10

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import uuid
from collections.abc import AsyncGenerator
from datetime import date
from typing import Any
from unittest.mock import MagicMock, patch

import fitz
import httpx
import pytest
from sqlalchemy import delete as sa_delete
from sqlalchemy import select

from app.core.config import settings
from app.db.models import (
    CaseDossier,
    CaseRun,
    CaseRunArea,
    Claim,
    Conversation,
    ConversationDocument,
    EvidenceBinding,
    LegalChunk,
    LegalSource,
    PipelineStageLog,
)
from app.db.session import async_session_factory, engine
from app.main import app

HEADERS = {"X-Disclaimer-Ack": settings.DISCLAIMER_VERSION}

LETTER = (
    "Jobcenter Essen\nEssen, 06.07.2026\n\nBewilligungsbescheid\n"
    "auf Ihren Weiterbewilligungsantrag vom 15.06.2026 bewillige ich Ihnen "
    "Leistungen. Ihr Erwerbseinkommen wird angerechnet."
)
ATTACHMENT = "Meine Notiz\nDer Bescheid kam am 09.07.2026 bei mir an."
CALC_RESULT = {
    "calculations_found": [
        {
            "label": "Freibetrag",
            "relevant_rule": "§ 11b Abs. 3 SGB II",
            "computed_values": {
                "deterministic_result": 338.0,
                "computation_detail": "100+84+144+10",
            },
            "document_values": {"extracted_numbers": {"authority": 290.0}},
            "discrepancy_found": True,
            "discrepancy_amount_eur": 48.0,
            "discrepancy_direction": "zulasten",
        }
    ],
    "overall_assessment": {"total_discrepancies": 1, "total_amount_eur": 48.0},
}


@pytest.fixture(autouse=True)
async def _dispose_engine_per_test() -> AsyncGenerator[None, None]:
    yield
    with contextlib.suppress(Exception):
        await engine.dispose()


@pytest.fixture
async def client() -> AsyncGenerator[httpx.AsyncClient, None]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


@pytest.fixture
async def case_id() -> AsyncGenerator[uuid.UUID, None]:
    """A completed case with area, claim + evidence, calculation log, attachment."""
    async with async_session_factory() as db:
        source = LegalSource(
            source_type="sgb2",
            title="SGB II (test)",
            effective_date=date(2026, 1, 1),
            source_url="https://example.invalid/sgb2",
            version_hash=uuid.uuid4().hex,
        )
        db.add(source)
        await db.flush()
        chunk = LegalChunk(
            source_id=source.id,
            unit_type="paragraph",
            hierarchy_path="SGB II > § 11b",
            text_content="Vom Einkommen abzusetzen sind …",
            text_hash=uuid.uuid4().hex,
            effective_date=date(2026, 1, 1),
        )
        case = CaseRun(
            session_id=str(uuid.uuid4()),
            input_text=LETTER,
            status="completed",
            title="Dossier-Testfall",
            user_edits={"section_adjudications": {"x": {"status": "agreed"}}},
        )
        db.add_all([chunk, case])
        await db.flush()
        db.add(
            CaseRunArea(
                case_run_id=case.id,
                legal_area="sozialrecht",
                module_id="sozialrecht",
                module_version="1.3.0",
                is_primary=True,
            )
        )
        claim = Claim(
            case_run_id=case.id,
            claim_text="Der Freibetrag ist zu niedrig.",
            confidence_score=0.9,
            claim_type="fact",
            user_adjudication={"status": "disputed"},
        )
        db.add(claim)
        await db.flush()
        db.add(
            EvidenceBinding(
                claim_id=claim.id, chunk_id=chunk.id, binding_strength=0.95, quote_excerpt="§ 11b"
            )
        )
        db.add(
            PipelineStageLog(
                case_run_id=case.id,
                stage_name="calculation_check",
                output_snapshot={
                    "calculations_found": 1,
                    "discrepancies": 1,
                    "result": CALC_RESULT,
                },
                duration_ms=1,
            )
        )
        conversation = Conversation(title="t")
        db.add(conversation)
        await db.flush()
        for text in (LETTER, ATTACHMENT):  # the analysed text itself is not duplicated
            db.add(
                ConversationDocument(
                    conversation_id=conversation.id,
                    original_filename="notiz.txt",
                    normalized_text=text,
                    case_run_id=case.id,
                )
            )
        await db.commit()
        ids = (case.id, source.id, conversation.id)
    try:
        yield ids[0]
    finally:
        async with async_session_factory() as db:
            await db.execute(sa_delete(CaseRun).where(CaseRun.id == ids[0]))
            await db.execute(sa_delete(Conversation).where(Conversation.id == ids[2]))
            await db.execute(sa_delete(LegalSource).where(LegalSource.id == ids[1]))
            await db.commit()


async def test_unknown_case_is_404_everywhere(client: httpx.AsyncClient) -> None:
    missing = uuid.uuid4()
    for method, suffix in (
        ("GET", "dossier"),
        ("POST", "dossier"),
        ("GET", "dossier/chronology"),
        ("PUT", "dossier/chronology"),
    ):
        response = await client.request(
            method, f"/api/v1/cases/{missing}/{suffix}", headers=HEADERS, json={}
        )
        assert response.status_code == 404, (method, suffix)


async def test_disclaimer_ack_required(client: httpx.AsyncClient, case_id: uuid.UUID) -> None:
    response = await client.post(f"/api/v1/cases/{case_id}/dossier")
    assert response.status_code == 403


async def test_confirmation_flow_and_revisions(
    client: httpx.AsyncClient, case_id: uuid.UUID
) -> None:
    base = f"/api/v1/cases/{case_id}/dossier"

    response = await client.get(base, headers=HEADERS)
    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "dossier_not_built"

    view = (await client.get(f"{base}/chronology", headers=HEADERS)).json()
    kinds = {e["kind"]: e for e in view["entries"]}
    assert set(kinds) >= {"document_date", "antrag", "zugang"}  # attachment read too
    assert all(e["status"] == "proposed" for e in view["entries"])
    assert view["facts"] == {}

    # Build before confirmation: the deadline is provisional.
    first = await client.post(base, headers=HEADERS)
    assert first.status_code == 201, first.text
    body = first.json()
    assert body["revision"] == 1
    dossier = body["dossier"]
    assert dossier["sections"]["deadlines"]["items"][0]["status"] == "provisional"
    canonical = json.dumps(dossier, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    assert body["content_sha256"] == hashlib.sha256(canonical.encode()).hexdigest()
    assert first.headers["X-Dossier-Revision"] == "1"

    # Confirm the letter date, reject the Antrag entry, add an event, set facts.
    update = {
        "entries": [
            {"entry_id": kinds["document_date"]["entry_id"], "status": "confirmed"},
            {"entry_id": kinds["antrag"]["entry_id"], "status": "rejected"},
        ],
        "added": [{"date": "2026-07-12", "label_de": "Beratungstermin vereinbart"}],
        "facts": {"aufgabe_zur_post": "2026-07-06", "bundesland": "NW"},
    }
    response = await client.put(f"{base}/chronology", headers=HEADERS, json=update)
    assert response.status_code == 200, response.text
    statuses = {e["kind"]: e["status"] for e in response.json()["entries"]}
    assert statuses["document_date"] == "confirmed"
    assert statuses["antrag"] == "rejected"
    assert statuses["user_event"] == "user_added"

    second = (await client.post(base, headers=HEADERS)).json()
    assert second["revision"] == 2
    sections = second["dossier"]["sections"]
    deadline = sections["deadlines"]["items"][0]
    assert (deadline["status"], deadline["frist_ende"]) == ("computed", "2026-08-10")
    assert "antrag" not in {e["kind"] for e in sections["chronology"]["entries"]}
    assert sections["chronology"]["counts"]["rejected"] == 1
    assert sections["calculations"]["items"][0]["deterministic_result"] == 338.0
    evidence = sections["evidence"]["items"][0]
    assert evidence["bindings"][0]["source"] == "SGB II > § 11b"
    assert any(q["origin"] == "disputed_claim" for q in sections["questions"]["items"])
    assert second["dossier"]["provenance"]["modules"][0]["id"] == "sozialrecht"

    latest = (await client.get(base, headers=HEADERS)).json()
    assert latest["revision"] == 2 and latest["dossier"] == second["dossier"]

    # Other user edits survive the chronology update.
    async with async_session_factory() as db:
        case = (await db.execute(select(CaseRun).where(CaseRun.id == case_id))).scalar_one()
        assert case.user_edits is not None
        assert "section_adjudications" in case.user_edits

    invalid = await client.put(
        f"{base}/chronology", headers=HEADERS, json={"facts": {"rbb_status": "?"}}
    )
    assert invalid.status_code == 400
    assert invalid.json()["detail"]["error"] == "invalid_chronology_update"


async def test_pdf_export(client: httpx.AsyncClient, case_id: uuid.UUID) -> None:
    base = f"/api/v1/cases/{case_id}/dossier"
    built = await client.post(f"{base}?format=pdf", headers=HEADERS)
    assert built.status_code == 201
    assert built.headers["content-type"] == "application/pdf"
    assert "attachment" in built.headers["content-disposition"]
    fetched = await client.get(f"{base}?format=pdf", headers=HEADERS)
    assert fetched.status_code == 200
    stored = (await client.get(base, headers=HEADERS)).json()
    doc = fitz.open(stream=fetched.content, filetype="pdf")
    try:
        assert json.loads(doc.embfile_get("dossier.json")) == stored["dossier"]
    finally:
        doc.close()
    assert (await client.get(f"{base}?format=docx", headers=HEADERS)).status_code == 422


async def test_case_delete_cascades(client: httpx.AsyncClient, case_id: uuid.UUID) -> None:
    await client.post(f"/api/v1/cases/{case_id}/dossier", headers=HEADERS)
    assert (await client.delete(f"/api/v1/cases/{case_id}", headers=HEADERS)).status_code == 200
    async with async_session_factory() as db:
        rows = await db.execute(select(CaseDossier).where(CaseDossier.case_run_id == case_id))
        assert rows.first() is None


async def test_case_detail_final_output_unchanged(
    client: httpx.AsyncClient, case_id: uuid.UUID
) -> None:
    body = (await client.get(f"/api/v1/cases/{case_id}", headers=HEADERS)).json()
    assert "calculation_result" not in body["final_output"]
    assert body["final_output"]["calculation_discrepancies"] == 1
    stage = next(s for s in body["stages"] if s["stage_name"] == "calculation_check")
    assert stage["output_snapshot"]["result"] == CALC_RESULT


async def test_module_detail_serves_dossier_checklist(client: httpx.AsyncClient) -> None:
    body = (await client.get("/api/v1/modules/sozialrecht", headers=HEADERS)).json()
    assert body["capabilities"]["dossier"] is True
    assert body["dossier_checklist"]["format"] == "citizen-module-dossier-v1.0"
    ids = {i["id"] for i in body["dossier_checklist"]["checklist"]}
    assert "bescheid_vollstaendig" in ids


def _sse(data: dict[str, Any]) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


@patch("app.api.routes.analyze.run_pipeline")
async def test_analyze_persists_calculation_result_but_streams_counts(
    mock_run_pipeline: MagicMock, client: httpx.AsyncClient
) -> None:
    full = {**CALC_RESULT, "legal_snapshot": {"calculators": []}}

    async def generator(state: Any) -> AsyncGenerator[str, None]:
        state.calculation_result = full
        yield _sse(
            {
                "stage": "calculation_check",
                "status": "complete",
                "payload": {"duration_ms": 1, "calculations_found": 1, "discrepancies": 1},
            }
        )

    mock_run_pipeline.side_effect = generator
    async with client.stream(
        "POST", "/api/v1/analyze", json={"text": "Testbescheid."}, headers=HEADERS
    ) as response:
        content = (await response.aread()).decode()
    pending = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    if pending:
        await asyncio.wait(pending, timeout=10)

    events = [json.loads(line[6:]) for line in content.splitlines() if line.startswith("data: ")]
    streamed = next(e for e in events if e.get("stage") == "calculation_check")
    assert "result" not in streamed["payload"]
    case_id = next(e for e in events if "case_run_id" in e)["case_run_id"]
    try:
        async with async_session_factory() as db:
            log = (
                await db.execute(
                    select(PipelineStageLog).where(
                        PipelineStageLog.case_run_id == uuid.UUID(case_id),
                        PipelineStageLog.stage_name == "calculation_check",
                    )
                )
            ).scalar_one()
            assert log.output_snapshot is not None
            assert log.output_snapshot["result"] == CALC_RESULT  # legal_snapshot excluded
    finally:
        async with async_session_factory() as db:
            await db.execute(sa_delete(CaseRun).where(CaseRun.id == uuid.UUID(case_id)))
            await db.commit()


async def test_tenancy_receipt_facts_persist_and_drive_scoped_deadlines(
    client: httpx.AsyncClient, case_id: uuid.UUID
) -> None:
    # Reuse the synthetic case lifecycle, selecting tenancy explicitly.
    async with async_session_factory() as db:
        area = (
            await db.execute(select(CaseRunArea).where(CaseRunArea.case_run_id == case_id))
        ).scalar_one()
        area.legal_area = "mietrecht"
        area.module_id = "mietrecht"
        area.module_version = "0.2.0"
        await db.commit()
    base = f"/api/v1/cases/{case_id}/dossier"
    facts = {
        "document_type": "mieterhoehung",
        "zugang_tatsaechlich": "2026-11-02",
        "bundesland": "BE",
        "feiertagskalender_bestaetigt": True,
        "feiertage_zusaetzlich": [],
        "qualifikationen": {"ordentliche_kuendigung": None},
    }
    updated = await client.put(base + "/chronology", headers=HEADERS, json={"facts": facts})
    assert updated.status_code == 200, updated.text
    assert updated.json()["facts"]["qualifikationen"] == {}
    response = await client.post(base, headers=HEADERS)
    assert response.status_code == 201, response.text
    dossier = response.json()["dossier"]
    deadlines = dossier["sections"]["deadlines"]["items"]
    consent = next(item for item in deadlines if item["spec_id"] == "miet_zustimmung")
    assert (consent["status"], consent["frist_ende"]) == ("computed", "2027-02-01")
    assert all(item["module_id"] == "mietrecht" for item in deadlines)
    assert dossier["provenance"]["modules"][0]["id"] == "mietrecht"
