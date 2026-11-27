"""Contract sources preserve article identity and reject unavailable official text."""

import importlib.util
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import httpx
import pytest
from bs4 import BeautifulSoup

from app.citations.parser import parse_citations
from app.db.models import SOURCE_TYPE_ALLOWED
from app.services import corpus
from app.services.retrieval import _extract_norm_references


@pytest.mark.parametrize("key", ["egbgb", "eu261"])
def test_contract_sources_are_explicitly_selectable(key):
    assert key in SOURCE_TYPE_ALLOWED
    assert corpus.CORPUS_SOURCE_METADATA[key]["has_scraper"] is True
    assert corpus.CORPUS_SOURCE_METADATA[key]["checked_by_default"] is False


def test_egbgb_nested_section_keeps_article_identity():
    soup = BeautifulSoup(
        '<div class="jnnorm"><span class="jnenbez">Art 246a</span>'
        '<span class="jnenbez">§ 1</span><div class="jurAbsatz">(1) Synthetische '
        "Information.</div></div>",
        "html.parser",
    )
    chunk = corpus._parse_law_sections(soup, "egbgb", "EGBGB", date(2026, 11, 27), "/bgbeg/")[0]
    assert chunk["hierarchy_path"] == "EGBGB > Art. 246a > § 1 > Abs. 1"
    assert corpus.gii_source_slugs()["egbgb"] == "bgbeg"


async def test_eurlex_dispatch_keeps_official_identity_and_full_article():
    html = (
        "<html><body><p>Verordnung (EG) Nr. 261/2004</p><p>Artikel 7</p>"
        "<p>Ausgleichsanspruch</p><p>(1) Synthetische Regel.</p><p>a) erster Fall;</p>"
        "<p>b) zweiter Fall.</p><p>(2) Synthetische Kürzung.</p>"
        "<p>Artikel 19</p><p>Inkrafttreten</p>"
        "<p>Diese Verordnung tritt am 17. Februar 2005 in Kraft.</p></body></html>"
    )
    html = html.replace("</body></html>", "") + "".join(
        f"<p>Artikel {number}</p><p>Synthetischer weiterer Artikel.</p>"
        for number in [1, 2, 3, 4, 5, 6, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18]
    )
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, text=html, request=request)
        )
    ) as client:
        chunks = await corpus.scrape_and_chunk("eu261", client=client)
    assert chunks[0]["hierarchy_path"] == "VO (EG) Nr. 261/2004 > Art. 7 > Abs. 1"
    assert "a) erster Fall; b) zweiter Fall." in chunks[0]["text_content"]
    assert chunks[0]["source_type"] == "eu261"
    assert chunks[0]["source_url"].startswith("https://eur-lex.europa.eu/")
    assert chunks[0]["effective_date"] == "2005-02-17"
    assert len(chunks[0]["version_hash"]) == 64
    assert chunks[1]["hierarchy_path"].endswith("Art. 7 > Abs. 2")


@pytest.mark.parametrize(
    "status,html", [(202, ""), (200, "<html>Verify you are not a robot</html>")]
)
async def test_eurlex_unavailable_text_fails_closed(status, html):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(status, text=html, request=request)
        )
    ) as client:
        with pytest.raises(ValueError, match="EUR-Lex"):
            await corpus.scrape_and_chunk("eu261", client=client)


def test_contract_article_citations_and_retrieval_do_not_alias_bgb():
    citation = parse_citations("Art. 7 Abs. 1 VO (EG) Nr. 261/2004")[0]
    assert citation.source_type == "eu261"
    assert citation.article is True
    assert parse_citations("Art. 246a EGBGB")[0].source_type == "egbgb"
    assert _extract_norm_references("Art. 7 VO (EG) Nr. 261/2004") == [
        "Art. 7 VO (EG) Nr. 261/2004"
    ]


def test_contract_migration_guards_existing_sources(monkeypatch):
    path = Path("alembic/versions/019_contract_sources.py")
    assert path.exists()
    spec = importlib.util.spec_from_file_location("contract_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    operation = MagicMock()
    monkeypatch.setattr(migration, "op", operation)
    operation.get_bind.return_value.execute.return_value.first.return_value = (1,)
    with pytest.raises(RuntimeError, match="contract sources"):
        migration.downgrade()
    operation.create_check_constraint.assert_not_called()
    operation.get_bind.return_value.execute.return_value.first.return_value = None
    migration.downgrade()
    assert "eu261" not in operation.create_check_constraint.call_args.args[2]
    migration.upgrade()
    assert "'eu261'" in operation.create_check_constraint.call_args.args[2]
    assert "'egbgb'" in operation.create_check_constraint.call_args.args[2]


def test_article_verification_queries_article_hierarchy():
    from app.citations.verify import _path_conditions

    condition = str(
        _path_conditions("7", "1", article=True).compile(compile_kwargs={"literal_binds": True})
    )
    assert "Art. 7 > Abs. 1" in condition
    assert "§ 7" not in condition


async def test_eurlex_article_verification_uses_article_not_section(monkeypatch):
    from unittest.mock import AsyncMock

    from app.citations import verify

    count = AsyncMock(side_effect=[1, 1, 1])
    monkeypatch.setattr(verify, "_count", count)
    result = await verify._verify_statute(
        MagicMock(), parse_citations("Art. 7 Abs. 1 VO (EG) Nr. 261/2004")[0]
    )
    assert result["status"] == "verified"
    conditions = [
        str(call.args[2].compile(compile_kwargs={"literal_binds": True}))
        for call in count.call_args_list[1:]
    ]
    assert all("Art. 7" in condition for condition in conditions)


def test_egbgb_official_heading_without_jnenbez_scopes_following_sections():
    soup = BeautifulSoup(
        '<div class="jnnorm" title="Gliederung"><div class="jnheader">'
        "<h2><span>Art 246a</span><br/><span>Information</span></h2></div></div>"
        '<div class="jnnorm"><span class="jnenbez">§ 1</span>'
        '<div class="jurAbsatz">(1) Synthetische Information.</div></div>'
        '<div class="jnnorm"><span class="jnenbez">Art 247</span>'
        '<div class="jurAbsatz">Andere Regel.</div></div>',
        "html.parser",
    )
    chunks = corpus._parse_law_sections(soup, "egbgb", "EGBGB", date(2026, 11, 27), "/bgbeg/")
    assert chunks[0]["hierarchy_path"] == "EGBGB > Art. 246a > § 1 > Abs. 1"
    assert chunks[1]["hierarchy_path"] == "EGBGB > Art. 247"


async def test_eurlex_rejects_truncated_article_sequence():
    html = "<p>Artikel 1</p><p>Text</p><p>Artikel 19</p><p>Text</p>"
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, text=html, request=request)
        )
    ) as client:
        with pytest.raises(ValueError, match="incomplete"):
            await corpus.scrape_and_chunk("eu261", client=client)


def test_nested_egbgb_citation_preserves_article_scope():
    citations = parse_citations("Art. 246a § 1 Abs. 2 EGBGB")
    assert len(citations) == 1
    assert citations[0].source_type == "egbgb"
    assert citations[0].paragraphs == ("1",)
    assert citations[0].extra["article_scope"] == "246a"
    from app.citations.verify import _path_conditions

    condition = str(
        _path_conditions("1", "2", article_scope="246a").compile(
            compile_kwargs={"literal_binds": True}
        )
    )
    assert "Art. 246a > § 1 > Abs. 2" in condition


def test_nested_egbgb_direct_lookup_keeps_full_scope():
    assert _extract_norm_references("Art. 246a § 1 Abs. 2 EGBGB") == ["Art. 246a § 1 EGBGB"]


@pytest.mark.parametrize(
    "text,expected_unit",
    [
        ("Art. 1 VO (EG) Nr. 261/2004", "Art. 1"),
        ("Art. 7 Verordnung (EG) Nr. 261/2004", "Art. 7"),
        ("Art. 246a § 1 EGBGB", "Art. 246a > § 1"),
    ],
)
async def test_article_direct_lookup_uses_complete_unit_boundary(monkeypatch, text, expected_unit):
    from unittest.mock import AsyncMock

    from app.services import retrieval

    session = MagicMock()
    session.execute = AsyncMock()
    session.execute.return_value = MagicMock()
    session.execute.return_value.mappings.return_value.all.return_value = []
    session.close = AsyncMock()

    async def sessions():
        yield session

    monkeypatch.setattr(retrieval, "get_async_session", sessions)
    await retrieval.retrieve_chunks_by_norm_reference(text, ("egbgb", "eu261"))
    assert session.execute.await_count == 1
    sql = str(session.execute.call_args.args[0].compile(compile_kwargs={"literal_binds": True}))
    assert f"%> {expected_unit} > %" in sql
    assert f"%> {expected_unit}%'" not in sql


async def test_egbgb_section_without_article_never_verifies_or_boosts(monkeypatch):
    from unittest.mock import AsyncMock

    from app.citations import verify

    count = AsyncMock(return_value=1)
    monkeypatch.setattr(verify, "_count", count)
    citation = parse_citations("§ 1 Abs. 2 EGBGB")[0]
    assert (await verify._verify_statute(MagicMock(), citation))["status"] != "verified"
    count.assert_not_awaited()
    assert _extract_norm_references("§ 1 EGBGB") == []
