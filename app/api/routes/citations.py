"""Citation parsing + corpus verification endpoint (WP-114).

Provides:
    POST /api/v1/citations/verify — parse §/Art./ECLI/BSG-docket citations
                                    in a text and check them against the
                                    ingested corpus

Deterministic and read-only: no LLM call, nothing stored. The response is
not AI-generated content, so it carries no Art. 50 disclosure.
"""

# Semantic Version: 1.0.0 | 2026-11-17 — WP-114: initial version.

from __future__ import annotations

import logging
from collections import Counter
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError

from app.citations.parser import parse_citations
from app.citations.verify import verify_citations
from app.db.session import async_session_factory

logger = logging.getLogger(__name__)

router = APIRouter()

#: Upper bound on the text size (characters) — a long Bescheid fits easily.
MAX_TEXT_CHARS = 200_000


class CitationRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=MAX_TEXT_CHARS)
    verify: bool = True


@router.post("/citations/verify")
async def verify_text_citations(body: CitationRequest) -> dict[str, Any]:
    """Parse every citation in ``text``; verify against the corpus if asked.

    When the database is unreachable the citations are returned parsed but
    unverified (``corpus_checked: false``, ``verification: null``).
    """
    citations = parse_citations(body.text)
    entries: list[dict[str, Any]]
    checked = False
    if body.verify and citations:
        try:
            async with async_session_factory() as session:
                entries = await verify_citations(session, citations)
            checked = True
        except (SQLAlchemyError, OSError) as exc:
            logger.warning("citation verification: database unavailable (%s)", exc)
            entries = [{**c.as_dict(), "verification": None} for c in citations]
    else:
        entries = [{**c.as_dict(), "verification": None} for c in citations]
    summary = Counter(
        e["verification"]["status"] for e in entries if e.get("verification") is not None
    )
    return {
        "count": len(entries),
        "corpus_checked": checked,
        "summary": dict(sorted(summary.items())),
        "citations": entries,
    }
