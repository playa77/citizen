"""Actual migrated PostgreSQL constraint and exact family-source identity; synthetic rows."""

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
    [("famfg", "FamFG"), ("uvg", "UhVorschG"), ("minuhv", "MinUhV")],
)
async def test_family_source_constraint_and_exact_lookup(monkeypatch, source_type, law):
    async with get_session_factory()() as session:
        source = LegalSource(
            source_type=source_type,
            title="Synthetic WP-135",
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
                    text_content="Synthetic family statute fixture",
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
