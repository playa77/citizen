"""Verify parsed citations against the ingested corpus (WP-114).

Statuses (one per citation; for ``§§`` lists/ranges the weakest of the
cited paragraphs wins, range endpoints are checked):

``verified``             the cited § (and Absatz, if given) exists in an
                         active ingested source of the law
``absatz_not_found``     the § exists, the cited Absatz does not
``not_found``            the law is ingested, the § is not — a likely
                         mis-citation (or a § newer than the ingested Fassung)
``source_not_ingested``  the law's corpus source type has no chunks here
``not_in_catalog``       the law is recognised, but the core corpus carries
                         no source for it (cannot be checked)
``no_law``               a § without a recognised law (cannot be checked)
``decision_found`` / ``decision_not_found``
                         ECLI or docket number in / not in the ingested case
                         law (``not_ingested`` when no case law exists)

Read-only; statute hierarchy paths look like ``"SGB X > § 44 > Abs. 1 > Satz 2"``.
"""

# Semantic Version: 1.0.0 | 2026-11-17 — WP-114: initial version.

from __future__ import annotations

from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.citations.parser import Citation
from app.db.models import LegalChunk, LegalSource

_STATUS_RANK = {
    "verified": 0,
    "absatz_not_found": 1,
    "not_found": 2,
}


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _path_conditions(
    paragraph: str,
    absatz: str | None,
    *,
    article: bool = False,
    article_scope: str | None = None,
) -> Any:
    sign = "Art." if article else "§"
    unit = f"{sign} {_escape_like(paragraph)}"
    if article_scope is not None:
        unit = f"Art. {_escape_like(article_scope)} > {unit}"
    if absatz is not None:
        unit += f" > Abs. {_escape_like(absatz)}"
    return or_(
        LegalChunk.hierarchy_path.like(f"%> {unit} >%", escape="\\"),
        LegalChunk.hierarchy_path.like(f"%> {unit}", escape="\\"),
    )


async def _count(session: AsyncSession, source_type: str, condition: Any | None = None) -> int:
    query = (
        select(func.count(LegalChunk.id))
        .join(LegalSource, LegalSource.id == LegalChunk.source_id)
        .where(and_(LegalSource.source_type == source_type, LegalSource.is_active.is_(True)))
    )
    if condition is not None:
        query = query.where(condition)
    return int(await session.scalar(query) or 0)


async def _verify_statute(session: AsyncSession, citation: Citation) -> dict[str, Any]:
    if citation.law is None:
        return {"status": "no_law"}
    if citation.source_type is None:
        return {"status": "not_in_catalog"}
    if citation.article and citation.source_type not in {"egbgb", "eu261"}:
        return {"status": "not_in_catalog"}
    if (
        citation.source_type == "egbgb"
        and not citation.article
        and not citation.extra.get("article_scope")
    ):
        # Sections restart within EGBGB articles; a bare section has no unique
        # corpus identity and must not verify against an unrelated article.
        return {"status": "not_found"}
    if await _count(session, citation.source_type) == 0:
        return {"status": "source_not_ingested"}
    scope = citation.extra.get("article_scope")
    worst = "verified"
    details: list[dict[str, str]] = []
    single = len(citation.paragraphs) == 1
    for entry in citation.paragraphs:
        for paragraph in entry.split("–"):
            found = await _count(
                session,
                citation.source_type,
                _path_conditions(paragraph, None, article=citation.article, article_scope=scope),
            )
            status = "verified" if found else "not_found"
            if found and single and citation.absatz is not None:
                with_absatz = await _count(
                    session,
                    citation.source_type,
                    _path_conditions(
                        paragraph, citation.absatz, article=citation.article, article_scope=scope
                    ),
                )
                status = "verified" if with_absatz else "absatz_not_found"
            details.append({"paragraph": paragraph, "status": status})
            if _STATUS_RANK[status] > _STATUS_RANK[worst]:
                worst = status
    return {"status": worst, "paragraphs": details}


async def _verify_decision(session: AsyncSession, citation: Citation) -> dict[str, Any]:
    from app.services.corpus import CASE_LAW_SOURCE_TYPES

    case_law = select(func.count(LegalSource.id)).where(
        LegalSource.source_type.in_(sorted(CASE_LAW_SOURCE_TYPES))
    )
    if not int(await session.scalar(case_law) or 0):
        return {"status": "not_ingested"}
    identifier = _escape_like(citation.identifier or citation.text)
    found = await session.scalar(
        select(LegalSource.title)
        .where(LegalSource.source_type.in_(sorted(CASE_LAW_SOURCE_TYPES)))
        .where(LegalSource.title.ilike(f"%{identifier}%", escape="\\"))
        .limit(1)
    )
    if found is None:
        return {"status": "decision_not_found"}
    return {"status": "decision_found", "title": found}


async def verify_citations(
    session: AsyncSession, citations: list[Citation]
) -> list[dict[str, Any]]:
    """``citation.as_dict()`` plus a ``verification`` object per citation."""
    results: list[dict[str, Any]] = []
    for citation in citations:
        if citation.kind == "statute":
            verification = await _verify_statute(session, citation)
        else:
            verification = await _verify_decision(session, citation)
        results.append({**citation.as_dict(), "verification": verification})
    return results


__all__ = ["verify_citations"]
