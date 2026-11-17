"""Case-law ingestion from free, keyless sources (WP-113; ARCHITECTURE.md § 3.3).

Two providers, both public and without API keys:

``rii``
    Rechtsprechung im Internet (federal courts, Bundesamt für Justiz):
    ``rii-toc.xml`` lists every published decision (court, decision date,
    docket number, link to a ZIP holding one XML document). Primary source.
``olda``
    Open Legal Data (``de.openlegaldata.io``) JSON API, for courts RII does
    not cover. The query parameters (``court__slug``, ``date__gte``) follow
    the public API documentation and were **not verified against the live
    service** when this was written (no network access from the build
    environment) — treat OLDA as experimental until a live run confirms it.

What is ingested is declared by modules, never by the core: a module's
``corpus.yaml`` lists ``case_law`` entries, and only modules of tier
``verified`` are honoured ("for verified modules", roadmap WP-113)::

    case_law:
      - source_type: bsg        # a corpus source type the module retrieves from
        provider: rii           # rii | olda
        court: BSG              # RII: prefix of <gericht>; OLDA: court slug
        since: 2023-01-01       # decisions on/after this date
        max_documents: 200      # newest first; bounds traffic and storage

Each decision becomes one ``legal_source`` (title with court, date, docket
number and ECLI; ``version_hash`` over the document) and one chunk per
paragraph of Leitsatz, Tenor, Tatbestand and Gründe (``unit_type``
``paragraph``). Note: a module whose ``corpus.yaml`` already lists the case-law
source type among its ``source_types`` retrieves the chunks once ingested,
which changes analysis input — rerun the module's goldset gate after the
first ingestion.

Network conduct: one request in flight per host, 1 s between requests,
bounded retries with backoff (``corpus._http_get_with_backoff``).
"""

# Semantic Version: 1.0.0 | 2026-11-17 — WP-113: initial version.

from __future__ import annotations

import asyncio
import hashlib
import io
import logging
import re
import zipfile
from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import uuid4

import httpx
from bs4 import BeautifulSoup
from lxml import etree

from app.modules.registry import ModuleManifest, ModuleManifestError

logger = logging.getLogger(__name__)

RII_TOC_URL = "https://www.rechtsprechung-im-internet.de/rii-toc.xml"
OLDA_CASES_URL = "https://de.openlegaldata.io/api/cases/"
PROVIDERS = ("rii", "olda")
_POLITENESS_DELAY = 1.0
_MAX_ZIP_BYTES = 20 * 1024 * 1024
_MAX_OLDA_PAGES = 20

#: Sections of an RII document, in reading order, with their German label.
_RII_SECTIONS: tuple[tuple[str, str], ...] = (
    ("leitsatz", "Leitsatz"),
    ("tenor", "Tenor"),
    ("tatbestand", "Tatbestand"),
    ("entscheidungsgruende", "Entscheidungsgründe"),
    ("gruende", "Gründe"),
)
_MIN_PARAGRAPH_CHARS = 40


# ---------------------------------------------------------------------------
# Module declarations
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CaseLawSpec:
    module_id: str
    source_type: str
    provider: str
    court: str
    since: date
    max_documents: int


def parse_case_law_section(manifest: ModuleManifest, corpus: Any) -> list[CaseLawSpec]:
    """Validate a ``corpus.yaml`` ``case_law`` list (``[]`` when absent)."""
    entries = (corpus or {}).get("case_law") if isinstance(corpus, dict) else None
    if entries is None:
        return []
    where = f"module {manifest.id!r} corpus.yaml case_law"
    if not isinstance(entries, list):
        raise ModuleManifestError(f"{where}: must be a list")
    specs: list[CaseLawSpec] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ModuleManifestError(f"{where}[{index}]: not a mapping")
        unknown = set(entry) - {"source_type", "provider", "court", "since", "max_documents"}
        if unknown:
            raise ModuleManifestError(f"{where}[{index}]: unknown key(s) {sorted(unknown)}")
        provider = entry.get("provider")
        if provider not in PROVIDERS:
            raise ModuleManifestError(f"{where}[{index}]: provider must be one of {PROVIDERS}")
        since = entry.get("since")
        if isinstance(since, str):
            since = date.fromisoformat(since)
        if not isinstance(since, date):
            raise ModuleManifestError(f"{where}[{index}]: `since` must be an ISO date")
        maximum = entry.get("max_documents")
        if not isinstance(maximum, int) or isinstance(maximum, bool) or not 1 <= maximum <= 5000:
            raise ModuleManifestError(f"{where}[{index}]: max_documents must be 1…5000")
        court = entry.get("court")
        source_type = entry.get("source_type")
        if not isinstance(court, str) or not court or not isinstance(source_type, str):
            raise ModuleManifestError(f"{where}[{index}]: `court` and `source_type` required")
        specs.append(CaseLawSpec(manifest.id, source_type, provider, court, since, maximum))
    return specs


def case_law_specs(source_type: str | None = None) -> list[CaseLawSpec]:
    """Case-law declarations of the installed **verified** modules."""
    from app.modules.content import load_section
    from app.modules.runtime import installed_modules

    specs: list[CaseLawSpec] = []
    for manifest in installed_modules().values():
        if manifest.tier != "verified":
            continue
        for spec in parse_case_law_section(manifest, load_section(manifest, "corpus")):
            if source_type is None or spec.source_type == source_type:
                specs.append(spec)
    return specs


# ---------------------------------------------------------------------------
# RII
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RiiTocItem:
    court: str
    decided: date | None
    docket: str
    link: str
    modified: str | None


def _text(element: Any, tag: str) -> str:
    child = element.find(tag)
    return (child.text or "").strip() if child is not None else ""


def _parse_compact_date(value: str) -> date | None:
    value = value.strip()
    try:
        if re.fullmatch(r"\d{8}", value):
            return date(int(value[:4]), int(value[4:6]), int(value[6:]))
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _parse_xml(xml_bytes: bytes) -> Any:
    # No network, no entity expansion: the documents come from a public host.
    parser = etree.XMLParser(resolve_entities=False, no_network=True, recover=True)
    return etree.fromstring(xml_bytes, parser=parser)


def parse_rii_toc(xml_bytes: bytes) -> list[RiiTocItem]:
    """Items of ``rii-toc.xml``."""
    root = _parse_xml(xml_bytes)
    items: list[RiiTocItem] = []
    for item in root.iter("item"):
        link = _text(item, "link")
        if not link:
            continue
        items.append(
            RiiTocItem(
                court=_text(item, "gericht"),
                decided=_parse_compact_date(_text(item, "entsch-datum")),
                docket=_text(item, "aktenzeichen"),
                link=link.replace("http://", "https://", 1),
                modified=_text(item, "modified") or None,
            )
        )
    return items


def select_rii_items(items: list[RiiTocItem], spec: CaseLawSpec) -> list[RiiTocItem]:
    """Items of the spec's court on/after ``since``, newest first, at most N."""
    chosen = [
        i
        for i in items
        if i.court.startswith(spec.court) and i.decided is not None and i.decided >= spec.since
    ]
    chosen.sort(key=lambda i: (i.decided or date.min, i.docket), reverse=True)
    return chosen[: spec.max_documents]


def _paragraphs(element: Any) -> list[str]:
    """Text paragraphs of an RII section (``<p>``/``<dd>`` blocks or its text)."""
    blocks = [b for b in element.iter() if isinstance(b.tag, str) and b.tag in ("p", "dd")]
    texts = [" ".join("".join(b.itertext()).split()) for b in blocks] if blocks else []
    if not texts:
        texts = [" ".join("".join(element.itertext()).split())]
    # Merge fragments (Randnummern, single headings) into the next paragraph.
    merged: list[str] = []
    carry = ""
    for text in texts:
        if not text:
            continue
        text = f"{carry} {text}".strip() if carry else text
        if len(text) < _MIN_PARAGRAPH_CHARS:
            carry = text
            continue
        merged.append(text)
        carry = ""
    if carry:
        if merged:
            merged[-1] = f"{merged[-1]} {carry}"
        else:
            merged.append(carry)
    return merged


def decision_title(court: str, doc_type: str, decided: date | None, docket: str, ecli: str) -> str:
    parts = [court or "Gericht"]
    when = f"{doc_type or 'Entscheidung'} vom {decided:%d.%m.%Y}" if decided else doc_type
    if when:
        parts.append(when)
    title = ", ".join(parts)
    if docket:
        title += f" – {docket}"
    if ecli:
        title += f" ({ecli})"
    return title[:500]


def _chunks_for_decision(
    *,
    source_type: str,
    title: str,
    docket: str,
    decided: date | None,
    url: str,
    sections: list[tuple[str, list[str]]],
    version_hash: str,
) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    effective = (decided or date.today()).isoformat()
    head = title.split(",")[0]
    for label, paragraphs in sections:
        for number, text in enumerate(paragraphs, 1):
            chunks.append(
                {
                    "id": str(uuid4()),
                    "source_type": source_type,
                    "title": title,
                    "unit_type": "paragraph",
                    "hierarchy_path": " > ".join([head, docket or "?", label, str(number)]),
                    "text_content": text,
                    "effective_date": effective,
                    "source_url": url,
                    # One legal_source per decision: the hash of the document.
                    "version_hash": version_hash,
                    "chunk_id": str(uuid4()),
                    "legal_area": None,
                }
            )
    return chunks


def parse_rii_document(xml_bytes: bytes, source_type: str, url: str) -> list[dict[str, Any]]:
    """Chunks of one RII decision document."""
    root = _parse_xml(xml_bytes)
    court = " ".join(filter(None, [_text(root, "gertyp"), _text(root, "gerort")])).strip()
    docket = _text(root, "aktenzeichen")
    decided = _parse_compact_date(_text(root, "entsch-datum"))
    ecli = _text(root, "ecli")
    title = decision_title(court, _text(root, "doktyp"), decided, docket, ecli)
    sections: list[tuple[str, list[str]]] = []
    for tag, label in _RII_SECTIONS:
        element = root.find(tag)
        if element is None:
            continue
        paragraphs = _paragraphs(element)
        if paragraphs:
            sections.append((label, paragraphs))
    return _chunks_for_decision(
        source_type=source_type,
        title=title,
        docket=docket,
        decided=decided,
        url=url,
        sections=sections,
        version_hash=hashlib.sha256(xml_bytes).hexdigest(),
    )


def _xml_from_zip(data: bytes) -> bytes:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = [n for n in archive.namelist() if n.lower().endswith(".xml")]
        if not names:
            raise ValueError("ZIP holds no XML document")
        info = archive.getinfo(names[0])
        if info.file_size > _MAX_ZIP_BYTES:
            raise ValueError("XML document too large")
        return archive.read(names[0])


async def fetch_rii(spec: CaseLawSpec, client: httpx.AsyncClient) -> list[dict[str, Any]]:
    from app.services.corpus import _http_get_with_backoff

    resp = await _http_get_with_backoff(client, RII_TOC_URL)
    resp.raise_for_status()
    items = select_rii_items(parse_rii_toc(resp.content), spec)
    logger.info("RII %s: %d decision(s) selected since %s", spec.court, len(items), spec.since)
    chunks: list[dict[str, Any]] = []
    for index, item in enumerate(items, 1):
        await asyncio.sleep(_POLITENESS_DELAY)
        try:
            resp = await _http_get_with_backoff(client, item.link)
            resp.raise_for_status()
            if len(resp.content) > _MAX_ZIP_BYTES:
                raise ValueError("archive too large")
            chunks.extend(
                parse_rii_document(_xml_from_zip(resp.content), spec.source_type, item.link)
            )
        except Exception as exc:  # one broken decision must not stop the run
            logger.warning("RII %s (%d/%d) skipped: %s", item.docket, index, len(items), exc)
    return chunks


# ---------------------------------------------------------------------------
# Open Legal Data
# ---------------------------------------------------------------------------


def parse_olda_case(case: dict[str, Any], source_type: str) -> list[dict[str, Any]]:
    """Chunks of one OLDA ``/api/cases/`` result (HTML ``content``)."""
    court_info = case.get("court")
    court = str(court_info.get("name") or "") if isinstance(court_info, dict) else ""
    docket = str(case.get("file_number") or "")
    decided = _parse_compact_date(str(case.get("date") or ""))
    ecli = str(case.get("ecli") or "")
    title = decision_title(court, str(case.get("type") or ""), decided, docket, ecli)
    soup = BeautifulSoup(str(case.get("content") or ""), "lxml")
    blocks = [" ".join(p.get_text(" ").split()) for p in soup.find_all(["p", "dd"])]
    paragraphs = [b for b in blocks if len(b) >= _MIN_PARAGRAPH_CHARS]
    slug = case.get("slug") or case.get("id")
    url = f"https://de.openlegaldata.io/case/{slug}" if slug else OLDA_CASES_URL
    payload = f"{case.get('id')}|{case.get('updated_date')}|{len(paragraphs)}|{docket}"
    return _chunks_for_decision(
        source_type=source_type,
        title=title,
        docket=docket,
        decided=decided,
        url=url,
        sections=[("Gründe", paragraphs)] if paragraphs else [],
        version_hash=hashlib.sha256(payload.encode("utf-8")).hexdigest(),
    )


async def fetch_olda(spec: CaseLawSpec, client: httpx.AsyncClient) -> list[dict[str, Any]]:
    from app.services.corpus import _http_get_with_backoff

    url: str | None = (
        f"{OLDA_CASES_URL}?format=json&court__slug={spec.court}"
        f"&date__gte={spec.since.isoformat()}&ordering=-date"
    )
    chunks: list[dict[str, Any]] = []
    fetched = pages = 0
    while url and fetched < spec.max_documents and pages < _MAX_OLDA_PAGES:
        resp = await _http_get_with_backoff(client, url)
        resp.raise_for_status()
        body = resp.json()
        pages += 1
        for case in body.get("results") or []:
            if fetched >= spec.max_documents:
                break
            chunks.extend(parse_olda_case(case, spec.source_type))
            fetched += 1
        url = body.get("next")
        if url:
            await asyncio.sleep(_POLITENESS_DELAY)
    logger.info("OLDA %s: %d decision(s) since %s", spec.court, fetched, spec.since)
    return chunks


async def scrape_case_law(
    source_type: str, *, client: httpx.AsyncClient | None = None
) -> list[dict[str, Any]]:
    """Chunks for *source_type* from every verified module's declarations."""
    specs = case_law_specs(source_type)
    if not specs:
        logger.warning("no verified module declares case law for source_type=%s", source_type)
        return []

    async def _run(c: httpx.AsyncClient) -> list[dict[str, Any]]:
        chunks: list[dict[str, Any]] = []
        for spec in specs:
            fetch = fetch_rii if spec.provider == "rii" else fetch_olda
            chunks.extend(await fetch(spec, c))
        return chunks

    # A caller's client is used as-is (it owns its lifecycle).
    if client is not None:
        return await _run(client)
    async with httpx.AsyncClient(follow_redirects=True, timeout=60.0) as own:
        return await _run(own)


__all__ = [
    "CaseLawSpec",
    "RiiTocItem",
    "case_law_specs",
    "decision_title",
    "fetch_olda",
    "fetch_rii",
    "parse_case_law_section",
    "parse_olda_case",
    "parse_rii_document",
    "parse_rii_toc",
    "scrape_case_law",
    "select_rii_items",
]
