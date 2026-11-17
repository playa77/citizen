"""Daily statute change detection for gesetze-im-internet.de (WP-113).

``gii-toc.xml`` lists every federal law with the link to its XML archive
(``https://www.gesetze-im-internet.de/<slug>/xml.zip``). The table of
contents carries no dates, so the change signal is the archive itself: a
``HEAD`` request yields ``ETag`` / ``Last-Modified`` / ``Content-Length``,
compared against the state stored in ``corpus_source_watch``.

Per watched source the outcome is one of

``new``        first observation — baseline stored, nothing to compare;
``unchanged``  every validator the server sent equals the stored one;
``changed``    a validator differs → re-ingest (``--ingest``);
``missing``    the source is no longer listed in ``gii-toc.xml``;
``error``      the archive could not be checked (reported, state kept).

"Daily" is the operator's scheduler (cron/systemd timer, see
``DEPLOYMENT.md``) running ``python -m scripts.corpus_watch``; the service
itself runs no background schedule. Network conduct: one request in flight,
1 s between requests to the host, bounded backoff; the TOC request is
conditional (``If-None-Match``/``If-Modified-Since``) when a previous TOC
validator is known.
"""

# Semantic Version: 1.0.0 | 2026-11-17 — WP-113: initial version.

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

import httpx
from lxml import etree
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import CorpusSourceWatch

logger = logging.getLogger(__name__)

GII_TOC_URL = "https://www.gesetze-im-internet.de/gii-toc.xml"
#: Pseudo source type under which the TOC's own validators are stored.
TOC_STATE_KEY = "_gii_toc"
_POLITENESS_DELAY = 1.0
_ATTEMPTS = 3
_TRANSIENT = frozenset({429, 500, 502, 503, 504})


@dataclass(frozen=True)
class Observation:
    source_type: str
    toc_link: str | None
    etag: str | None
    last_modified: str | None
    content_length: int | None
    in_toc: bool
    error: str | None = None


@dataclass(frozen=True)
class WatchResult:
    source_type: str
    status: str  # new | unchanged | changed | missing | error
    observation: Observation
    changed_fields: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        o = self.observation
        return {
            "source_type": self.source_type,
            "status": self.status,
            "changed_fields": list(self.changed_fields),
            "toc_link": o.toc_link,
            "etag": o.etag,
            "last_modified": o.last_modified,
            "content_length": o.content_length,
            "error": o.error,
        }


def parse_gii_toc(xml_bytes: bytes) -> dict[str, str]:
    """``slug → xml.zip link`` from ``gii-toc.xml`` (links upgraded to https)."""
    parser = etree.XMLParser(resolve_entities=False, no_network=True, recover=True)
    root = etree.fromstring(xml_bytes, parser=parser)
    links: dict[str, str] = {}
    for item in root.iter("item"):
        link_el = item.find("link")
        if link_el is None or not (link_el.text or "").strip():
            continue
        link = link_el.text.strip().replace("http://", "https://", 1)
        parts = [p for p in urlparse(link).path.split("/") if p]
        if len(parts) >= 2 and parts[-1].lower() == "xml.zip":
            links[parts[-2]] = link
    return links


def compare(previous: CorpusSourceWatch | None, observed: Observation) -> WatchResult:
    """Classify *observed* against the stored state (pure)."""
    if observed.error is not None:
        return WatchResult(observed.source_type, "error", observed)
    if not observed.in_toc:
        return WatchResult(observed.source_type, "missing", observed)
    if previous is None:
        return WatchResult(observed.source_type, "new", observed)
    changed: list[str] = []
    # Only validators the server sent this time are compared: a missing
    # header is "unknown", not "changed".
    if observed.etag is not None and observed.etag != previous.etag:
        changed.append("etag")
    if observed.last_modified is not None and observed.last_modified != previous.last_modified:
        changed.append("last_modified")
    if observed.content_length is not None and observed.content_length != previous.content_length:
        changed.append("content_length")
    if observed.toc_link != previous.toc_link:
        changed.append("toc_link")
    status = "changed" if changed else "unchanged"
    return WatchResult(observed.source_type, status, observed, tuple(changed))


async def _request(client: httpx.AsyncClient, method: str, url: str, **kw: Any) -> httpx.Response:
    delay = 1.0
    for attempt in range(1, _ATTEMPTS + 1):
        try:
            resp = await client.request(method, url, **kw)
        except (httpx.TransportError, httpx.TimeoutException):
            if attempt == _ATTEMPTS:
                raise
        else:
            if resp.status_code not in _TRANSIENT or attempt == _ATTEMPTS:
                return resp
            retry_after = resp.headers.get("Retry-After", "")
            delay = float(retry_after) if retry_after.isdigit() else delay
        await asyncio.sleep(min(delay, 60.0))
        delay *= 2
    raise RuntimeError("unreachable")


def _validators(resp: httpx.Response) -> tuple[str | None, str | None, int | None]:
    length = resp.headers.get("Content-Length")
    return (
        resp.headers.get("ETag"),
        resp.headers.get("Last-Modified"),
        int(length) if length and length.isdigit() else None,
    )


async def observe_sources(
    source_types: list[str],
    slugs: dict[str, str],
    toc_state: CorpusSourceWatch | None,
    client: httpx.AsyncClient,
) -> tuple[list[Observation], Observation | None]:
    """Fetch the TOC (conditionally) and HEAD every watched source's archive.

    Returns the per-source observations and the TOC's own observation (its
    validators, to store for the next conditional request). On ``304`` the
    TOC listing is unknown this run; sources are then checked at their
    known links (``https://…/<slug>/xml.zip``).
    """
    headers: dict[str, str] = {}
    if toc_state is not None and toc_state.etag:
        headers["If-None-Match"] = toc_state.etag
    if toc_state is not None and toc_state.last_modified:
        headers["If-Modified-Since"] = toc_state.last_modified
    resp = await _request(client, "GET", GII_TOC_URL, headers=headers)
    listing: dict[str, str] | None
    if resp.status_code == 304:
        listing = None
    else:
        resp.raise_for_status()
        listing = parse_gii_toc(resp.content)
    etag, modified, length = _validators(resp)
    toc_obs = Observation(TOC_STATE_KEY, GII_TOC_URL, etag, modified, length, True)

    observations: list[Observation] = []
    for source_type in source_types:
        slug = slugs[source_type]
        link = (
            listing.get(slug)
            if listing is not None
            else f"https://www.gesetze-im-internet.de/{slug}/xml.zip"
        )
        if link is None:
            observations.append(Observation(source_type, None, None, None, None, False))
            continue
        await asyncio.sleep(_POLITENESS_DELAY)
        try:
            head = await _request(client, "HEAD", link)
            head.raise_for_status()
            etag, modified, length = _validators(head)
            observations.append(Observation(source_type, link, etag, modified, length, True))
        except Exception as exc:  # reported per source; the run continues
            observations.append(
                Observation(
                    source_type, link, None, None, None, True, f"{type(exc).__name__}: {exc}"
                )
            )
    return observations, toc_obs


async def load_state(session: AsyncSession) -> dict[str, CorpusSourceWatch]:
    rows = (await session.execute(select(CorpusSourceWatch))).scalars().all()
    return {row.source_type: row for row in rows}


def store(
    session: AsyncSession,
    state: dict[str, CorpusSourceWatch],
    observation: Observation,
    status: str,
    now: datetime,
) -> None:
    """Write one observation into ``corpus_source_watch`` (no commit)."""
    if status == "error":
        return  # keep the last good state
    row = state.get(observation.source_type)
    if row is None:
        row = CorpusSourceWatch(source_type=observation.source_type)
        session.add(row)
        state[observation.source_type] = row
    row.toc_link = observation.toc_link or row.toc_link
    row.etag = observation.etag or row.etag
    row.last_modified = observation.last_modified or row.last_modified
    if observation.content_length is not None:
        row.content_length = observation.content_length
    row.in_toc = observation.in_toc
    row.checked_at = now
    if status == "changed":
        row.changed_at = now


async def run_watch(
    session: AsyncSession, source_types: list[str], *, client: httpx.AsyncClient | None = None
) -> list[WatchResult]:
    """One detection run over *source_types* (statute sources only); flushes."""
    from app.services.corpus import gii_source_slugs

    slugs = gii_source_slugs()
    unknown = [s for s in source_types if s not in slugs]
    if unknown:
        raise ValueError(f"not gesetze-im-internet sources: {unknown}")
    state = await load_state(session)
    # A caller's client is used as-is (it owns its lifecycle).
    if client is not None:
        observations, toc_obs = await observe_sources(
            source_types, slugs, state.get(TOC_STATE_KEY), client
        )
    else:
        async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as own:
            observations, toc_obs = await observe_sources(
                source_types, slugs, state.get(TOC_STATE_KEY), own
            )
    now = datetime.now(UTC)
    results = [compare(state.get(o.source_type), o) for o in observations]
    for result in results:
        store(session, state, result.observation, result.status, now)
    if toc_obs is not None:
        store(session, state, toc_obs, "unchanged", now)
    await session.flush()
    return results


__all__ = [
    "GII_TOC_URL",
    "Observation",
    "WatchResult",
    "compare",
    "ingest_sources",
    "load_state",
    "observe_sources",
    "parse_gii_toc",
    "run_watch",
    "store",
]


async def ingest_sources(source_types: list[str]) -> dict[str, int]:
    """Re-ingest *source_types* (scrape → embed → upsert); chunk count per source.

    Same three stages as the ``/corpus/update`` job, without the job store.
    Needs the embedding API key (``EMBEDDING_API_KEY``/``OPENROUTER_API_KEY``).
    """
    from app.db.session import async_session_factory
    from app.services.corpus import generate_embeddings, scrape_and_chunk, upsert_chunks

    counts: dict[str, int] = {}
    for source_type in source_types:
        chunks = await scrape_and_chunk(source_type)
        counts[source_type] = len(chunks)
        if not chunks:
            continue
        chunks = await generate_embeddings(chunks)
        async with async_session_factory() as session:
            await upsert_chunks(session, chunks)
    return counts
