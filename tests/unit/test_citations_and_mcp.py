"""WP-114 (citation service) and WP-116 (read-only MCP surface).

Parser: German statute forms, ECLI, BSG dockets, spans. Verification
against synthetic corpus rows in a rolled-back transaction. The
``POST /api/v1/citations/verify`` route. The MCP JSON-RPC handler:
handshake, tool listing, tool calls, argument validation, error codes.
"""

# Semantic Version: 1.0.0 | 2026-11-17 — WP-114, WP-116

from __future__ import annotations

import contextlib
import json
import os
from collections.abc import AsyncGenerator, AsyncIterator
from datetime import date
from typing import Any

import httpx
import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.citations.parser import parse_citations
from app.citations.verify import verify_citations
from app.core.config import settings
from app.db.models import LegalChunk, LegalSource
from app.db.session import engine
from app.main import app
from app.mcp.server import TOOLS, handle_line, handle_message

HEADERS = {"X-Disclaimer-Ack": settings.DISCLAIMER_VERSION}


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "law", "source_type", "paragraphs", "absatz", "satz", "nummer", "ff"),
    [
        ("§ 44 Abs. 1 Satz 2 SGB X", "SGB X", "sgbx", ["44"], "1", "2", None, False),
        ("§ 37 Abs. 2 S. 1 SGB 10", "SGB X", "sgbx", ["37"], "2", "1", None, False),
        ("§§ 11, 11b SGB II", "SGB II", "sgb2", ["11", "11b"], None, None, None, False),
        ("§§ 11–11b SGB II", "SGB II", "sgb2", ["11–11b"], None, None, None, False),
        ("§ 11b Abs. 3 S. 2 Nr. 1-3 SGB II", "SGB II", "sgb2", ["11b"], "3", "2", "1", False),
        ("§§ 535 ff. BGB", "BGB", "bgb", ["535"], None, None, None, True),
        ("§ 84 SGG", "SGG", "sgg", ["84"], None, None, None, False),
        ("§ 4 KSchG", "KSchG", "kschg", ["4"], None, None, None, False),
        ("§ 31a SGB II", "SGB II", "sgb2", ["31a"], None, None, None, False),
    ],
)
def test_statute_forms(
    text: str,
    law: str,
    source_type: str,
    paragraphs: list[str],
    absatz: str | None,
    satz: str | None,
    nummer: str | None,
    ff: bool,
) -> None:
    sentence = f"Nach {text} gilt das."
    (citation,) = parse_citations(sentence)
    assert citation.text == text
    assert sentence[citation.start : citation.end] == text
    assert (citation.law, citation.source_type) == (law, source_type)
    assert list(citation.paragraphs) == paragraphs
    assert (citation.absatz, citation.satz, citation.nummer, citation.ff) == (
        absatz,
        satz,
        nummer,
        ff,
    )


def test_other_kinds_and_unknowns() -> None:
    text = (
        "Art. 3 Abs. 1 GG; § 5 des Vertrags; BSG, Urteil vom 12.06.2024 – B 4 AS 19/23 R, "
        "ecli:de:bsg:2024:120624UB4AS1923R0; § 12 StVO"
    )
    kinds = [(c.kind, c.law, c.identifier) for c in parse_citations(text)]
    assert kinds == [
        ("statute", "GG", None),
        ("statute", None, None),
        ("docket", None, "B 4 AS 19/23 R"),
        ("ecli", None, "ECLI:DE:BSG:2024:120624UB4AS1923R0"),
        ("statute", "StVO", None),
    ]
    art = parse_citations("Art. 3 Abs. 1 GG")[0]
    assert art.article and art.source_type is None


def test_no_false_positives_on_plain_text() -> None:
    assert parse_citations("Am 12.03.2026 wurden 563,00 EUR überwiesen (Kd.-Nr. 4711).") == []


def test_parser_is_linear_on_hostile_input() -> None:
    import time

    hostile = "§ 1" + " Abs. 1," * 5000 + " SGB X"
    started = time.perf_counter()
    parse_citations(hostile)
    assert time.perf_counter() - started < 2.0


# ---------------------------------------------------------------------------
# Verification (synthetic corpus rows, rolled back)
# ---------------------------------------------------------------------------


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    db_engine = create_async_engine(os.environ["DATABASE_URL"], poolclass=NullPool)
    try:
        async with db_engine.connect() as conn:
            outer = await conn.begin()
            db = AsyncSession(bind=conn, expire_on_commit=False)
            try:
                yield db
            finally:
                await db.close()
                await outer.rollback()
    finally:
        await db_engine.dispose()


async def _corpus(db: AsyncSession) -> None:
    # Other suites leave statute rows in the shared DB; inside this
    # rolled-back transaction the ErbStG source is guaranteed empty.
    await db.execute(delete(LegalSource).where(LegalSource.source_type == "erbstg"))
    sgbx = LegalSource(
        source_type="sgbx",
        title="SGB X",
        effective_date=date(2026, 1, 1),
        source_url="https://example.invalid",
        version_hash="wp114-sgbx",
    )
    bsg = LegalSource(
        source_type="bsg",
        title="BSG, Urteil vom 12.06.2024 – B 4 AS 19/23 R (ECLI:DE:BSG:2024:120624UB4AS1923R0)",
        effective_date=date(2024, 6, 12),
        source_url="https://example.invalid",
        version_hash="wp114-bsg",
    )
    db.add_all([sgbx, bsg])
    await db.flush()
    for path in (
        "SGB X > § 44 > Abs. 1 > Satz 1",
        "SGB X > § 44 > Abs. 2 > Satz 1",
        "SGB X > § 144 > Satz 1",
        "SGB X > § 45",
    ):
        db.add(
            LegalChunk(
                source_id=sgbx.id,
                unit_type="satz",
                hierarchy_path=path,
                text_content="synthetisch",
                text_hash=path[-32:].ljust(32, "0"),
                effective_date=date(2026, 1, 1),
            )
        )
    db.add(
        LegalChunk(
            source_id=bsg.id,
            unit_type="paragraph",
            hierarchy_path="BSG > B 4 AS 19/23 R > Leitsatz > 1",
            text_content="synthetisch",
            text_hash="b" * 32,
            effective_date=date(2024, 6, 12),
        )
    )
    await db.flush()


async def test_verification_statuses(session: AsyncSession) -> None:
    await _corpus(session)
    text = (
        "§ 44 Abs. 1 SGB X | § 44 Abs. 9 SGB X | § 4 SGB X | § 45 SGB X | §§ 44, 46 SGB X | "
        "§ 1 ErbStG | Art. 3 GG | § 5 | B 4 AS 19/23 R | ECLI:DE:BSG:2024:120624UB4AS1923R0 | "
        "ECLI:DE:BSG:2020:000000UB1AS000R0"
    )
    results = await verify_citations(session, parse_citations(text))
    statuses = [r["verification"]["status"] for r in results]
    assert statuses == [
        "verified",
        "absatz_not_found",
        "not_found",  # "§ 144" must not satisfy "§ 4"
        "verified",
        "not_found",  # weakest of the listed paragraphs wins
        "source_not_ingested",
        "not_in_catalog",
        "no_law",
        "decision_found",
        "decision_found",
        "decision_not_found",
    ]


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------


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


async def test_route(client: httpx.AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/citations/verify",
        json={"text": "Gemäß § 44 Abs. 1 SGB X und Art. 3 GG."},
        headers=HEADERS,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 2 and body["corpus_checked"] is True
    assert body["citations"][0]["span"] == [6, 23]
    assert body["citations"][1]["verification"] == {"status": "not_in_catalog"}
    assert "disclosure" not in body

    unverified = await client.post(
        "/api/v1/citations/verify", json={"text": "§ 1 BGB", "verify": False}, headers=HEADERS
    )
    assert unverified.json()["citations"][0]["verification"] is None
    assert (
        await client.post("/api/v1/citations/verify", json={"text": ""}, headers=HEADERS)
    ).status_code == 422
    assert (await client.post("/api/v1/citations/verify", json={"text": "x"})).status_code == 403


# ---------------------------------------------------------------------------
# MCP
# ---------------------------------------------------------------------------


async def _call(method: str, params: dict[str, Any] | None = None, msg_id: int = 1) -> Any:
    reply = await handle_message(
        {"jsonrpc": "2.0", "id": msg_id, "method": method, "params": params or {}}
    )
    assert reply is not None
    return reply


async def test_mcp_handshake_and_listing() -> None:
    init = await _call("initialize", {"protocolVersion": "2025-03-26", "capabilities": {}})
    assert init["result"]["protocolVersion"] == "2025-03-26"
    assert init["result"]["capabilities"] == {"tools": {"listChanged": False}}
    unknown = await _call("initialize", {"protocolVersion": "1999-01-01"})
    assert unknown["result"]["protocolVersion"] == "2025-06-18"
    assert await handle_message({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
    assert (await _call("ping"))["result"] == {}
    tools = (await _call("tools/list"))["result"]["tools"]
    assert {t["name"] for t in tools} == set(TOOLS)
    assert all(t["annotations"]["readOnlyHint"] for t in tools)


async def test_mcp_tool_calls() -> None:
    listing = await _call("tools/call", {"name": "list_modules", "arguments": {}})
    data = listing["result"]["structuredContent"]
    assert data["default_module"] == settings.DEFAULT_MODULE
    module = await _call(
        "tools/call", {"name": "get_module", "arguments": {"module_id": settings.DEFAULT_MODULE}}
    )
    detail = module["result"]["structuredContent"]
    assert detail["deadlines"] and detail["errata"] and "path" not in json.dumps(detail["scope"])
    catalog = await _call("tools/call", {"name": "deadline_catalog", "arguments": {}})
    assert catalog["result"]["structuredContent"]["modules"]
    citations = await _call(
        "tools/call",
        {"name": "check_citations", "arguments": {"text": "§ 44 SGB X", "verify": False}},
    )
    assert citations["result"]["structuredContent"]["citations"][0]["law"] == "SGB X"
    status = await _call("tools/call", {"name": "corpus_status", "arguments": {}})
    assert status["result"]["isError"] is False


async def test_mcp_errors() -> None:
    missing = await _call("tools/call", {"name": "get_module", "arguments": {"module_id": "zz_no"}})
    assert missing["result"]["isError"] is True
    assert "MODULE_UNKNOWN" in missing["result"]["content"][0]["text"]
    bad_args = await _call("tools/call", {"name": "get_module", "arguments": {}})
    assert bad_args["error"]["code"] == -32602
    unknown_tool = await _call("tools/call", {"name": "write_things", "arguments": {}})
    assert unknown_tool["error"]["code"] == -32602
    assert (await _call("resources/list"))["error"]["code"] == -32601
    statute = await _call(
        "tools/call", {"name": "get_statute", "arguments": {"law": "GG", "paragraph": "1"}}
    )
    assert statute["result"]["isError"] is True
    parse_error = json.loads(await handle_line("{not json") or "{}")
    assert parse_error["error"]["code"] == -32700
    assert await handle_line("   ") is None
