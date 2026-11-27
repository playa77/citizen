"""Official employment sources retain identities across ingestion and lookup."""

import uuid
from datetime import date

import pytest
from bs4 import BeautifulSoup
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.db.models import SOURCE_TYPE_ALLOWED, LegalSource
from app.db.session import engine
from app.services import corpus
from app.services.retrieval import _STATUTE_TO_SOURCE_TYPE, _extract_norm_references

SOURCES = [
    ("kschg", "KSchG"),
    ("burlg", "BUrlG"),
    ("tzbfg", "TzBfG"),
    ("entgfg", "EntgFG"),
    ("milog", "MiLoG"),
    ("muschg", "MuSchG"),
    ("arbzg", "ArbZG"),
    ("arbgg", "ArbGG"),
]


@pytest.mark.parametrize("key,law", SOURCES)
def test_employment_sources_are_selectable_parsed_and_retrievable(key, law):
    assert key in SOURCE_TYPE_ALLOWED
    assert corpus.CORPUS_SOURCE_METADATA[key]["has_scraper"] is True
    assert corpus.CORPUS_SOURCE_METADATA[key]["checked_by_default"] is False
    assert corpus.gii_source_slugs()[key] == ("muschg_2018" if key == "muschg" else key)
    assert (
        corpus._infer_law_name(
            BeautifulSoup("<html><h1>Long official title</h1></html>", "html.parser"), key
        )
        == law
    )
    assert _STATUTE_TO_SOURCE_TYPE[law] == [key]
    assert _extract_norm_references(f"§ 4 {law}") == [f"§ 4 {law}"]
    soup = BeautifulSoup(
        '<div class="jnnorm"><span class="jnenbez">§ 4</span>'
        '<div class="jurAbsatz">(1) Synthetische Regel.</div></div>',
        "html.parser",
    )
    chunk = corpus._parse_law_sections(soup, key, law, date(2026, 11, 27), f"/{key}/")[0]
    assert chunk["hierarchy_path"] == f"{law} > § 4 > Abs. 1"
    assert chunk["source_type"] == key


@pytest.mark.parametrize("key,law", SOURCES)
async def test_migrated_postgres_accepts_employment_sources(key, law):
    test_engine = create_async_engine(engine.url, poolclass=NullPool)
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    try:
        async with factory() as session:
            chunk = {
                "source_type": key,
                "title": law,
                "version_hash": uuid.uuid4().hex,
                "source_url": f"https://www.gesetze-im-internet.de/{key}/",
                "effective_date": "2026-11-27",
            }
            row = await corpus._get_or_create_source(session, chunk)
            assert await session.get(LegalSource, row.id) is row
            assert row.source_type == key
            await session.rollback()
    finally:
        await test_engine.dispose()
