"""Actual migrated PostgreSQL constraint and exact residence-source identity; synthetic rows."""

from datetime import date
from uuid import uuid4

import pytest

from app.citations.parser import parse_citations
from app.citations.verify import _verify_statute
from app.db.models import LegalChunk, LegalSource
from app.db.session import get_session_factory
from app.services import retrieval


@pytest.mark.parametrize(
    "source_type,law",
    [
        ("aufenthg", "AufenthG"),
        ("asylg", "AsylG"),
        ("aufenthv", "AufenthV"),
        ("beschv", "BeschV"),
        ("freizuegg_eu", "FreizügG/EU"),
        ("stag", "StAG"),
        ("vwgo", "VwGO"),
    ],
)
async def test_residence_source_constraint_and_exact_lookup(monkeypatch, source_type, law):
    async with get_session_factory()() as session:
        source = LegalSource(
            source_type=source_type,
            title="Synthetic WP-136",
            effective_date=date(2026, 11, 27),
            source_url="https://example.invalid/synthetic",
            version_hash=uuid4().hex,
        )
        session.add(source)
        await session.flush()
        for path in [f"{law} > § 10 > Abs. 1", f"{law} > § 1 > Abs. 1"]:
            session.add(
                LegalChunk(
                    source_id=source.id,
                    unit_type="satz",
                    hierarchy_path=path,
                    text_content="Synthetic residence statute fixture",
                    text_hash=uuid4().hex,
                    effective_date=date(2026, 11, 27),
                )
            )
        await session.flush()
        citation = parse_citations(f"§ 1 Abs. 1 {law}")[0]
        assert (await _verify_statute(session, citation))["status"] == "verified"

        async def sessions():
            yield session

        monkeypatch.setattr(retrieval, "get_async_session", sessions)
        chunks = await retrieval.retrieve_chunks_by_norm_reference(f"§ 1 {law}", (source_type,))
        assert [c["hierarchy_path"] for c in chunks] == [f"{law} > § 1 > Abs. 1"]
        # Session closure rolls back uncommitted synthetic rows.


async def test_ingested_lettered_section_is_retrievable_without_numeric_collision(monkeypatch):
    from bs4 import BeautifulSoup
    from app.services import corpus

    soup = BeautifulSoup(
        "".join(
            f'<div class="jnnorm"><span class="jnenbez">§ {number}</span>'
            f'<div class="jurAbsatz">(1) Synthetic paragraph {number}.</div></div>'
            for number in ("34", "34a", "87", "87e")
        ),
        "html.parser",
    )
    parsed = corpus._parse_law_sections(
        soup, "asylg", "AsylG", date(2026, 11, 27), "/asylvfg_1992/"
    )
    async with get_session_factory()() as session:
        source = LegalSource(
            source_type="asylg",
            title="Synthetic WP-136 identity",
            effective_date=date(2026, 11, 27),
            source_url="https://example.invalid/synthetic",
            version_hash=uuid4().hex,
        )
        session.add(source)
        await session.flush()
        for c in parsed:
            session.add(
                LegalChunk(
                    source_id=source.id,
                    unit_type="satz",
                    hierarchy_path=c["hierarchy_path"],
                    text_content=c["text_content"],
                    text_hash=uuid4().hex,
                    effective_date=date(2026, 11, 27),
                )
            )
        await session.flush()

        async def sessions():
            yield session

        monkeypatch.setattr(retrieval, "get_async_session", sessions)
        for number in ("34a", "87e"):
            citation = parse_citations(f"§ {number} Abs. 1 AsylG")[0]
            assert (await _verify_statute(session, citation))["status"] == "verified"
        # Retrieval owns/closes this supplied session; verify both citations
        # first, then retrieve both identities in one operation.
        chunks = await retrieval.retrieve_chunks_by_norm_reference(
            "§ 34a AsylG und § 87e AsylG", ("asylg",)
        )
        assert {c["hierarchy_path"] for c in chunks} == {
            "AsylG > § 34a > Abs. 1",
            "AsylG > § 87e > Abs. 1",
        }
