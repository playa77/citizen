"""WP-130 statutory sources use the existing parser, citation and storage contracts."""

from datetime import date

import pytest
from bs4 import BeautifulSoup
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.citations.laws import normalise_law
from app.db.models import SOURCE_TYPE_ALLOWED
from app.db.models import LegalSource
from app.db.session import engine
from app.services.corpus import CORPUS_SOURCE_METADATA, _parse_law_sections, gii_source_slugs


@pytest.mark.parametrize(
    ("key", "law", "slug"),
    [
        ("zpo", "ZPO", "zpo"),
        ("inso", "InsO", "inso"),
        ("rdg", "RDG", "rdg"),
        ("rvg", "RVG", "rvg"),
    ],
)
def test_debt_statute_can_be_selected_parsed_cited_and_stored(key, law, slug):
    assert key in SOURCE_TYPE_ALLOWED
    assert CORPUS_SOURCE_METADATA[key]["checked_by_default"] is False
    assert gii_source_slugs()[key] == slug
    assert normalise_law(law) == (law, key)
    soup = BeautifulSoup(
        """<html><body><div class="jnnorm"><span class="jnenbez">§ 12</span>
      <div class="jurAbsatz">(1) Eine synthetische Regel für den Parsertest.</div>
      </div></body></html>""",
        "html.parser",
    )
    chunks = _parse_law_sections(soup, key, law, date(2026, 11, 26), f"/{slug}/")
    assert chunks
    assert all(chunk["source_type"] == key for chunk in chunks)
    assert any(law in chunk["hierarchy_path"] for chunk in chunks)


@pytest.mark.parametrize("key", ["zpo", "inso", "rdg", "rvg"])
async def test_migrated_postgres_accepts_debt_sources(key):
    import uuid

    # A dedicated pool keeps this schema check independent of prior test loops.
    test_engine = create_async_engine(engine.url, poolclass=NullPool)
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    try:
        async with factory() as session:
            source = LegalSource(
                source_type=key,
                title="Synthetic storage-contract fixture",
                effective_date=date(2026, 11, 26),
                source_url="https://example.invalid/fixture",
                version_hash=uuid.uuid4().hex,
            )
            session.add(source)
            await session.flush()
            assert await session.get(LegalSource, source.id) is source
            await session.rollback()
    finally:
        await test_engine.dispose()
