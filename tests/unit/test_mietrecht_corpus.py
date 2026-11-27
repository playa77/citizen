"""Tenancy source adapters preserve source identity and reject unverified snapshots."""

import hashlib
from datetime import date

import pytest
from bs4 import BeautifulSoup

from app.db.models import SOURCE_TYPE_ALLOWED
from app.services import corpus
from app.services.retrieval import _extract_norm_references


@pytest.mark.parametrize(
    ("key", "law", "slug"),
    [("betrkv", "BetrKV", "betrkv"), ("heizkostenv", "HeizkostenV", "heizkostenv")],
)
def test_tenancy_statutes_can_be_selected_parsed_and_directly_retrieved(key, law, slug):
    assert key in SOURCE_TYPE_ALLOWED
    assert corpus.CORPUS_SOURCE_METADATA[key]["checked_by_default"] is False
    assert corpus.gii_source_slugs()[key] == slug
    soup = BeautifulSoup(
        '<div class="jnnorm"><span class="jnenbez">§ 2</span>'
        '<div class="jurAbsatz">(1) Synthetische Kostenregel.</div></div>',
        "html.parser",
    )
    chunks = corpus._parse_law_sections(soup, key, law, date(2026, 11, 26), f"/{slug}/")
    assert len(chunks) == 1
    assert chunks[0]["source_url"] == f"https://www.gesetze-im-internet.de/{slug}/"
    assert chunks[0]["hierarchy_path"] == f"{law} > § 2 > Abs. 1"
    assert _extract_norm_references(f"§ 2 {law}") == [f"§ 2 {law}"]


def snapshot(**changes):
    text = "§ 1 Synthetische Landesverordnung.\nBerlin ist ein synthetisches Gebiet."
    record = {
        "bundesland": "BE",
        "title": "Synthetische Mietverordnung",
        "official_url": "https://gesetze.berlin.de/fixture",
        "effective_date": "2026-01-01",
        "publication": "Synthetisches GVBl. 2025 S. 1",
        "text": text,
        "sha256": hashlib.sha256(text.encode()).hexdigest(),
        "snapshot_kind": "applicability_excerpt",
    }
    record.update(changes)
    return record


def test_state_snapshot_preserves_jurisdiction_publication_and_content_identity():
    chunks = corpus.normalize_state_ordinance(snapshot())
    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk["source_type"] == "landes_mietrecht"
    assert chunk["jurisdiction"] == "DE-BE"
    assert chunk["effective_date"] == "2026-01-01"
    assert chunk["source_url"] == "https://gesetze.berlin.de/fixture"
    assert "Synthetisches GVBl. 2025 S. 1" in chunk["hierarchy_path"]
    assert "Synthetische Landesverordnung" in chunk["text_content"]
    other = corpus.normalize_state_ordinance(
        snapshot(bundesland="BB", official_url="https://mil.brandenburg.de/fixture")
    )
    # Identical words in different jurisdictions must never collapse to one LegalSource.
    assert chunk["version_hash"] != other[0]["version_hash"]


@pytest.mark.parametrize(
    "changes",
    [
        {"sha256": "0" * 64},
        {"bundesland": "DE"},
        {"effective_date": "not-a-date"},
        {"official_url": "http://gesetze.berlin.de/fixture"},
        {"official_url": "https://gesetze.berlin.de.evil.invalid/fixture"},
        {"official_url": "https://person:secret@gesetze.berlin.de/fixture"},
        {"publication": ""},
        {"bundesland": "BB"},
        {"snapshot_kind": "full_statute"},
        {"text": ""},
    ],
)
def test_state_snapshot_rejects_missing_provenance_or_tampering(changes):
    with pytest.raises(ValueError):
        corpus.normalize_state_ordinance(snapshot(**changes))


async def test_state_source_requires_explicit_snapshot_import():
    assert "landes_mietrecht" in SOURCE_TYPE_ALLOWED
    assert corpus.CORPUS_SOURCE_METADATA["landes_mietrecht"]["has_scraper"] is False
    assert "landes_mietrecht" not in corpus.gii_source_slugs()
    with pytest.raises(ValueError, match="explicit official snapshot import"):
        await corpus.scrape_and_chunk("landes_mietrecht")


@pytest.mark.parametrize("key", ["betrkv", "heizkostenv", "landes_mietrecht"])
async def test_migrated_postgres_accepts_tenancy_sources(key):
    import uuid

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.db.models import LegalSource
    from app.db.session import engine

    test_engine = create_async_engine(engine.url, poolclass=NullPool)
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    try:
        async with factory() as session:
            chunk = corpus.normalize_state_ordinance(snapshot())[0]
            chunk["source_type"] = key
            chunk["version_hash"] = uuid.uuid4().hex
            source = await corpus._get_or_create_source(session, chunk)
            assert await session.get(LegalSource, source.id) is source
            assert source.jurisdiction == "DE-BE"
            assert source.source_url == "https://gesetze.berlin.de/fixture"
            assert source.effective_date == date(2026, 1, 1)
            assert await corpus._get_or_create_source(session, chunk) is source
            await session.rollback()
    finally:
        await test_engine.dispose()
