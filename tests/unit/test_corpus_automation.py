"""WP-113 — corpus automation: gii-toc change detection, RII/OLDA case law.

No network: every HTTP exchange runs against ``httpx.MockTransport`` with
synthetic fixtures shaped like the public formats (``gii-toc.xml``,
``rii-toc.xml``, the RII decision XML in a ZIP, an OLDA ``/api/cases/``
page). Watch-state writes happen in a rolled-back transaction.
"""

# Semantic Version: 1.0.0 | 2026-11-17 — WP-113
# ruff: noqa: E501 — synthetic XML/JSON fixtures keep their one-element-per-line shape.

from __future__ import annotations

import io
import os
import zipfile
from collections.abc import AsyncIterator
from datetime import date
from typing import Any

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.db.models import CorpusSourceWatch
from app.modules.registry import ModuleManifestError, default_modules_root, discover_modules
from app.services import case_law, corpus_watch
from app.services.case_law import (
    CaseLawSpec,
    case_law_specs,
    parse_case_law_section,
    parse_olda_case,
    parse_rii_document,
    parse_rii_toc,
    scrape_case_law,
    select_rii_items,
)
from app.services.corpus import gii_source_slugs
from app.services.corpus_watch import Observation, compare, parse_gii_toc, run_watch

GII_TOC = b"""<?xml version="1.0" encoding="UTF-8"?>
<items>
  <item><title>Sozialgesetzbuch (SGB) Zweites Buch</title>
        <link>http://www.gesetze-im-internet.de/sgb_2/xml.zip</link></item>
  <item><title>Sozialgesetzbuch (SGB) Zehntes Buch</title>
        <link>http://www.gesetze-im-internet.de/sgb_10/xml.zip</link></item>
</items>"""

RII_TOC = b"""<?xml version="1.0" encoding="utf-8"?>
<items>
 <item><gericht>BSG 4. Senat</gericht><entsch-datum>20240612</entsch-datum>
  <aktenzeichen>B 4 AS 19/23 R</aktenzeichen>
  <link>http://www.rechtsprechung-im-internet.de/jportal/docs/bsjrs/KSRE000001.zip</link>
  <modified>2024-08-01T10:00:00</modified></item>
 <item><gericht>BSG 7. Senat</gericht><entsch-datum>20220101</entsch-datum>
  <aktenzeichen>B 7 AS 1/21 R</aktenzeichen>
  <link>http://www.rechtsprechung-im-internet.de/jportal/docs/bsjrs/KSRE000002.zip</link></item>
 <item><gericht>BVerwG 5. Senat</gericht><entsch-datum>20240301</entsch-datum>
  <aktenzeichen>5 C 1.23</aktenzeichen>
  <link>http://www.rechtsprechung-im-internet.de/jportal/docs/bsjrs/WBRE000003.zip</link></item>
</items>"""

RII_DOC = """<?xml version="1.0" encoding="utf-8"?>
<dokument>
 <doknr>KSRE000001</doknr>
 <ecli>ECLI:DE:BSG:2024:120624UB4AS1923R0</ecli>
 <gertyp>BSG</gertyp><gerort></gerort><spruchkoerper>4. Senat</spruchkoerper>
 <entsch-datum>20240612</entsch-datum>
 <aktenzeichen>B 4 AS 19/23 R</aktenzeichen>
 <doktyp>Urteil</doktyp>
 <leitsatz><div><p>Synthetischer Leitsatz: Ein Bescheid ohne Berechnungsbogen ist nicht hinreichend begründet.</p></div></leitsatz>
 <tenor><div><p>Die Revision wird zurückgewiesen. Kosten sind nicht zu erstatten (synthetisch).</p></div></tenor>
 <gruende><div><p>1</p><p>Die Beteiligten streiten über die Höhe der Leistungen nach dem SGB II (synthetischer Text).</p>
 <p>2</p><p>Die Revision ist unbegründet, weil § 35 SGB X eine Begründung verlangt (synthetisch).</p></div></gruende>
</dokument>""".encode()


def _zip(xml: bytes) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("KSRE000001.xml", xml)
    return buffer.getvalue()


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    async def instant(_: float) -> None:
        return None

    monkeypatch.setattr(case_law.asyncio, "sleep", instant)
    monkeypatch.setattr(corpus_watch.asyncio, "sleep", instant)


# ---------------------------------------------------------------------------
# gii-toc change detection
# ---------------------------------------------------------------------------


def test_parse_gii_toc() -> None:
    links = parse_gii_toc(GII_TOC)
    assert links == {
        "sgb_2": "https://www.gesetze-im-internet.de/sgb_2/xml.zip",
        "sgb_10": "https://www.gesetze-im-internet.de/sgb_10/xml.zip",
    }
    assert gii_source_slugs()["sgbx"] == "sgb_10"


def _obs(**kw: Any) -> Observation:
    base: dict[str, Any] = {
        "source_type": "sgb2",
        "toc_link": "https://x/sgb_2/xml.zip",
        "etag": '"a"',
        "last_modified": "Mon, 01 Jan 2027 00:00:00 GMT",
        "content_length": 100,
        "in_toc": True,
    }
    base.update(kw)
    return Observation(**base)


def test_compare_states() -> None:
    previous = CorpusSourceWatch(
        source_type="sgb2",
        toc_link="https://x/sgb_2/xml.zip",
        etag='"a"',
        last_modified="Mon, 01 Jan 2027 00:00:00 GMT",
        content_length=100,
    )
    assert compare(None, _obs()).status == "new"
    assert compare(previous, _obs()).status == "unchanged"
    changed = compare(previous, _obs(etag='"b"', content_length=101))
    assert changed.status == "changed" and changed.changed_fields == ("etag", "content_length")
    # A header the server did not send is unknown, not a change.
    assert compare(previous, _obs(etag=None, last_modified=None)).status == "unchanged"
    assert compare(previous, _obs(in_toc=False)).status == "missing"
    assert compare(previous, _obs(error="boom")).status == "error"


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(os.environ["DATABASE_URL"], poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            outer = await conn.begin()
            db = AsyncSession(bind=conn, expire_on_commit=False)
            try:
                yield db
            finally:
                await db.close()
                await outer.rollback()
    finally:
        await engine.dispose()


async def test_run_watch_baseline_then_change(session: AsyncSession) -> None:
    etags = {"sgb_2": '"v1"', "sgb_10": '"x1"'}
    seen: list[tuple[str, str, dict[str, str]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path, dict(request.headers)))
        if request.url.path.endswith("gii-toc.xml"):
            if request.headers.get("If-None-Match") == '"toc1"':
                return httpx.Response(304)
            return httpx.Response(200, content=GII_TOC, headers={"ETag": '"toc1"'})
        slug = request.url.path.strip("/").split("/")[0]
        return httpx.Response(200, headers={"ETag": etags[slug], "Content-Length": "10"})

    async def run() -> dict[str, str]:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            results = await run_watch(session, ["sgb2", "sgbx"], client=client)
        return {r.source_type: r.status for r in results}

    assert await run() == {"sgb2": "new", "sgbx": "new"}
    assert {m for m, path, _ in seen if path.endswith("xml.zip")} == {"HEAD"}
    etags["sgb_2"] = '"v2"'
    assert await run() == {"sgb2": "changed", "sgbx": "unchanged"}
    # The second run asked for the TOC conditionally and got 304.
    toc_requests = [h for _, path, h in seen if path.endswith("gii-toc.xml")]
    assert toc_requests[-1].get("if-none-match") == '"toc1"'
    with pytest.raises(ValueError, match="not gesetze-im-internet"):
        await run_watch(session, ["weisung"])


async def test_run_watch_reports_errors_per_source(session: AsyncSession) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("gii-toc.xml"):
            return httpx.Response(200, content=GII_TOC)
        if "sgb_10" in request.url.path:
            return httpx.Response(404)
        return httpx.Response(200, headers={"ETag": '"e"'})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        results = await run_watch(session, ["sgb2", "sgbx", "bgb"], client=client)
    status = {r.source_type: r.status for r in results}
    assert status == {"sgb2": "new", "sgbx": "error", "bgb": "missing"}


# ---------------------------------------------------------------------------
# Case law
# ---------------------------------------------------------------------------


def _spec(**kw: Any) -> CaseLawSpec:
    base: dict[str, Any] = {
        "module_id": "m",
        "source_type": "bsg",
        "provider": "rii",
        "court": "BSG",
        "since": date(2023, 1, 1),
        "max_documents": 10,
    }
    base.update(kw)
    return CaseLawSpec(**base)


def test_rii_toc_selection() -> None:
    items = parse_rii_toc(RII_TOC)
    assert len(items) == 3 and items[0].link.startswith("https://")
    selected = select_rii_items(items, _spec())
    assert [i.docket for i in selected] == ["B 4 AS 19/23 R"]  # court + date filter
    assert select_rii_items(items, _spec(since=date(2020, 1, 1), max_documents=1))[
        0
    ].decided == date(2024, 6, 12)


def test_rii_document_chunks() -> None:
    chunks = parse_rii_document(RII_DOC, "bsg", "https://example.invalid/x.zip")
    assert {c["source_type"] for c in chunks} == {"bsg"}
    title = chunks[0]["title"]
    assert "B 4 AS 19/23 R" in title and "ECLI:DE:BSG:2024:120624UB4AS1923R0" in title
    sections = [c["hierarchy_path"].split(" > ")[2] for c in chunks]
    assert sections[0] == "Leitsatz" and "Tenor" in sections and "Gründe" in sections
    # Randnummern ("1", "2") merge into their paragraph instead of becoming chunks.
    assert all(len(c["text_content"]) >= 40 for c in chunks)
    assert len({c["version_hash"] for c in chunks}) == 1
    assert {c["unit_type"] for c in chunks} == {"paragraph"}


def test_olda_case_chunks() -> None:
    chunks = parse_olda_case(
        {
            "id": 7,
            "slug": "lsg-x-2024",
            "court": {"name": "LSG Beispiel"},
            "file_number": "L 1 AS 2/24",
            "date": "2024-05-02",
            "type": "Beschluss",
            "content": "<p>Kurz</p><p>Ein synthetischer Absatz mit genügend Text für einen Chunk.</p>",
        },
        "bsg",
    )
    assert len(chunks) == 1 and chunks[0]["title"].startswith(
        "LSG Beispiel, Beschluss vom 02.05.2024"
    )


def test_case_law_declarations() -> None:
    manifest = discover_modules(default_modules_root())["sozialrecht"]
    specs = parse_case_law_section(
        manifest,
        {
            "case_law": [
                {
                    "source_type": "bsg",
                    "provider": "rii",
                    "court": "BSG",
                    "since": "2023-01-01",
                    "max_documents": 5,
                }
            ]
        },
    )
    assert specs[0].since == date(2023, 1, 1)
    for bad in (
        {"provider": "web"},
        {"max_documents": 0},
        {"since": "soon"},
        {"surprise": 1},
    ):
        entry = {
            "source_type": "bsg",
            "provider": "rii",
            "court": "BSG",
            "since": "2023-01-01",
            "max_documents": 5,
            **bad,
        }
        with pytest.raises((ModuleManifestError, ValueError)):
            parse_case_law_section(manifest, {"case_law": [entry]})
    # Only verified modules are honoured; Sozialrecht explicitly declares BSG.
    assert [(s.module_id, s.source_type, s.provider) for s in case_law_specs("bsg")] == [
        ("sozialrecht", "bsg", "rii")
    ]


async def test_scrape_case_law_rii(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(case_law, "case_law_specs", lambda st: [_spec(max_documents=5)])
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        if request.url.path.endswith("rii-toc.xml"):
            return httpx.Response(200, content=RII_TOC)
        return httpx.Response(200, content=_zip(RII_DOC))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        chunks = await scrape_case_law("bsg", client=client)
    assert chunks and all(c["source_type"] == "bsg" for c in chunks)
    assert len(requested) == 2  # TOC + the one selected decision
    assert all(u.startswith("https://") for u in requested)


async def test_scrape_case_law_olda(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        case_law,
        "case_law_specs",
        lambda st: [_spec(provider="olda", court="bsg", max_documents=2)],
    )
    case = {
        "id": 1,
        "court": {"name": "BSG"},
        "file_number": "B 1 AS 1/24 R",
        "date": "2024-01-02",
        "content": "<p>" + "Synthetischer Text. " * 5 + "</p>",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["court__slug"] == "bsg"
        page = request.url.params.get("page", "1")
        if page == "1":
            return httpx.Response(
                200, json={"results": [case], "next": str(request.url) + "&page=2"}
            )
        return httpx.Response(200, json={"results": [case, case], "next": None})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        chunks = await scrape_case_law("bsg", client=client)
    assert len(chunks) == 2  # max_documents bounds the run across pages
