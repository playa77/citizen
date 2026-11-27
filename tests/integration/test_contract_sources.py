"""WP-133 PostgreSQL storage and exact article/section identity, with synthetic rows."""

from datetime import date
from uuid import uuid4

import pytest

from app.citations.parser import parse_citations
from app.citations.verify import _verify_statute
from app.db.models import LegalChunk, LegalSource
from app.db.session import get_session_factory
from app.services import retrieval


@pytest.mark.parametrize(
    "source_type,reference,paths,expected",
    [
        (
            "eu261",
            "Art. 1 Verordnung (EG) Nr. 261/2004",
            ["VO (EG) Nr. 261/2004 > Art. 10", "VO (EG) Nr. 261/2004 > Art. 1 > Abs. 1"],
            "VO (EG) Nr. 261/2004 > Art. 1 > Abs. 1",
        ),
        (
            "egbgb",
            "Art. 246a § 1 Abs. 2 EGBGB",
            ["EGBGB > Art. 247 > § 1 > Abs. 2", "EGBGB > Art. 246a > § 1 > Abs. 2"],
            "EGBGB > Art. 246a > § 1 > Abs. 2",
        ),
    ],
)
async def test_contract_source_constraint_and_exact_lookup(
    monkeypatch, source_type, reference, paths, expected
):
    async with get_session_factory()() as session:
        source = LegalSource(
            source_type=source_type,
            title="Synthetic WP-133",
            effective_date=date(2026, 11, 27),
            source_url="https://example.invalid/synthetic",
            version_hash=uuid4().hex,
        )
        session.add(source)
        await session.flush()  # Actual migrated PostgreSQL constraint accepts both new keys.
        for path in paths:
            session.add(
                LegalChunk(
                    source_id=source.id,
                    unit_type="satz",
                    hierarchy_path=path,
                    text_content="Synthetic statute fixture",
                    text_hash=uuid4().hex,
                    effective_date=date(2026, 11, 27),
                )
            )
        await session.flush()
        assert (await _verify_statute(session, parse_citations(reference)[0]))[
            "status"
        ] == "verified"
        if source_type == "egbgb":
            assert (await _verify_statute(session, parse_citations("§ 1 EGBGB")[0]))[
                "status"
            ] == "not_found"

        async def sessions():
            yield session

        monkeypatch.setattr(retrieval, "get_async_session", sessions)
        chunks = await retrieval.retrieve_chunks_by_norm_reference(reference, (source_type,))
        assert [chunk["hierarchy_path"] for chunk in chunks] == [expected]
        # Retrieval closes this uncommitted session; synthetic rows roll back.
