"""Corpus scraper, parser, hierarchical chunker, and vector upserter.

Fetches legal texts from ``gesetze-im-internet.de``, parses their hierarchical
structure into ``§ → Absatz → Satz`` units, generates metadata, and returns
normalised :class:`dict` objects ready for embedding and DB insertion.
"""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import date
from typing import Any
from urllib.parse import urljoin
from uuid import uuid4

import httpx
from bs4 import BeautifulSoup, Tag

from app.utils.text import normalize_text

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Source URL prefixes (gesetze-im-internet.de official XML/HTML endpoints)
# ---------------------------------------------------------------------------
_BASE = "https://www.gesetze-im-internet.de"

_SOURCE_TYPE_PREFIX: dict[str, str] = {
    "sgb2": "/sgb_2/",
    "sgbx": "/sgb_x/",
    "weisung": "/faw/",  # Fachliche Anweisungen / Weisungen
    "bsg": "/bsg/",  # Bundessozialgericht decisions (future extension)
}

# Regex for paragraph references, e.g. "§ 31"
_PARA_TAG_RE = re.compile(r"§\s*(\d+)")

# Regex for Absatz references, e.g. "Abs. 1", "Abs. 2", "Abs. 3"
_ABSATZ_RE = re.compile(r"Abs\.\s*(\d+)")

# Regex for Satz references, e.g. "Satz 1", "Satz 2", "Satz 3"
# Also matches numbered sentences like "1.", "2." at start of lines
_SATZ_RE = re.compile(r"Satz\s*(\d+)")
_ENUM_SENTENCE_RE = re.compile(r"^(\d+)\.\s+")

# ---------------------------------------------------------------------------
# Core public API
# ---------------------------------------------------------------------------


async def scrape_and_chunk(
    source_type: str,
    *,
    client: httpx.AsyncClient | None = None,
) -> list[dict[str, Any]]:
    """Scrape a legal corpus from gesetze-im-internet.de and return hierarchical chunks.

    Args:
        source_type: One of ``sgb2``, ``sgbx``, ``weisung``, ``bsg``.

    Returns:
        List of dicts with keys: ``id``, ``source_type``, ``title``,
        ``unit_type``, ``hierarchy_path``, ``text_content``, ``effective_date``,
        ``source_url``, ``version_hash``, ``chunk_id``.
    """
    if source_type not in _SOURCE_TYPE_PREFIX:
        raise ValueError(
            f"Unknown source_type={source_type!r}. " f"Allowed: {list(_SOURCE_TYPE_PREFIX)}"
        )

    prefix = _SOURCE_TYPE_PREFIX[source_type]
    index_url = urljoin(_BASE, prefix)

    async with client or httpx.AsyncClient(follow_redirects=True, timeout=30.0) as c:
        resp = await c.get(index_url)
        resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "lxml")
    paragraphs = _extract_paragraph_nodes(soup, source_type)

    chunks: list[dict[str, Any]] = []

    for para_el in paragraphs:
        hierarchy, text = _parse_paragraph_element(para_el, source_type)
        if not text or not text.strip():
            continue

        norm_text = normalize_text(text)
        if not norm_text:
            continue

        hierarchy_path = " > ".join(hierarchy)
        effective_date = _infer_effective_date(soup)

        chunks.append(
            {
                "id": str(uuid4()),
                "source_type": source_type,
                "title": hierarchy[0],
                "unit_type": "satz",
                "hierarchy_path": hierarchy_path,
                "text_content": norm_text,
                "effective_date": effective_date.isoformat(),
                "source_url": urljoin(_BASE, prefix),
                "version_hash": _compute_version_hash(norm_text),
                "chunk_id": str(uuid4()),
            }
        )

    logger.info("Scraped %d chunks for source_type=%s", len(chunks), source_type)
    return chunks


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _extract_paragraph_nodes(soup: BeautifulSoup, source_type: str) -> list[Tag]:
    """Find all paragraph elements (<p>, <norm> <jur> etc.) carrying legal text."""

    # Strategy 1: look for <p> tags inside <content> or <body>
    content_area = soup.find("content") or soup.find("body") or soup

    paragraphs: list[Tag] = []
    for tag in content_area.find_all(["p", "jur-body", "norm"]):
        if isinstance(tag, Tag):
            # Only include tags that have actual text content
            text = tag.get_text(strip=True)
            if text:
                paragraphs.append(tag)

    # Strategy 2: If the page has no structured elements, fall back to all <p>
    if not paragraphs:
        paragraphs = [p for p in soup.find_all("p") if p.get_text(strip=True)]

    return paragraphs


def _parse_paragraph_element(
    element: Tag,
    source_type: str,
) -> tuple[list[str], str]:
    """Extract hierarchy path and text from a single paragraph / legal element.

    Returns:
        Tuple of (hierarchy_list, raw_text).
        hierarchy_list example: ["SGB II", "§ 31", "Abs. 1", "Satz 2"]
    """
    text = element.get_text(separator=" ", strip=True)
    text = _clean_ocr_artefacts(text)

    # Build hierarchy from tag structure, attributes, and content cues
    law_name = _infer_law_name(element, source_type)

    # Extract paragraph number from text itself (e.g. "§ 31")
    para_match = _PARA_TAG_RE.search(text)
    para_label = f"§ {para_match.group(1)}" if para_match else "Unbekannt"

    # Extract Absatz (Abs./Absatz X)
    absatz_match = _ABSATZ_RE.search(text)
    absatz_label = f"Abs. {absatz_match.group(1)}" if absatz_match else ""

    # Extract Satz (Satz X) or use numbered sentences
    satz_match = _SATZ_RE.search(text)
    satz_label = f"Satz {satz_match.group(1)}" if satz_match else ""

    hierarchy = [law_name, para_label]
    if absatz_label:
        hierarchy.append(absatz_label)
    if satz_label:
        hierarchy.append(satz_label)

    # If we couldn't detect any structural markers, fall back to the full text
    # as a single statute-level chunk.
    if not para_match and not absatz_match and not satz_match:
        return [law_name, "Allgemein"], text

    return hierarchy, text


def _split_into_sentences(text: str) -> list[str]:
    """Split a paragraph into individual sentences for Satz-level chunking."""
    # Split on ". " followed by a capital letter (German sentence boundary)
    sentences = re.split(r"(?<=[.!?])\s+(?=[A-ZÖÜÄ])", text)
    return [s.strip() for s in sentences if s.strip()]


def _infer_law_name(element: Tag, source_type: str) -> str:
    """Derive the law name from surrounding HTML structure or source_type."""
    # Check for <title> or <h1> within the same document
    doc = element.find_parent("html") or element
    if isinstance(doc, Tag):
        title_tag = doc.find("title")
        if title_tag and title_tag.get_text(strip=True):
            return str(title_tag.get_text(strip=True))

        h1_tag = doc.find("h1")
        if h1_tag and h1_tag.get_text(strip=True):
            return str(h1_tag.get_text(strip=True))

    _LAW_NAME_DEFAULT: dict[str, str] = {
        "sgb2": "SGB II",
        "sgbx": "SGB X",
        "weisung": "Fachliche Weisung",
        "bsg": "BSG Urteil",
    }
    return _LAW_NAME_DEFAULT.get(source_type, source_type.upper())


def _infer_effective_date(soup: BeautifulSoup) -> date:
    """Extract the effective date from HTML metadata or use today's date."""
    # Check for <meta> tag with date info
    if isinstance(soup, Tag):
        meta = soup.find("meta", attrs={"name": "date"})
        if meta and isinstance(meta, Tag):
            content = meta.get("content", "")
            try:
                return date.fromisoformat(str(content)[:10])
            except ValueError:
                pass

        meta_fundstelle = soup.find("meta", attrs={"name": "fundstelle"})
        if meta_fundstelle and isinstance(meta_fundstelle, Tag):
            fundstelle = str(meta_fundstelle.get("content", ""))
            date_match = re.search(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", fundstelle)
            if date_match:
                try:
                    return date(
                        int(date_match.group(1)),
                        int(date_match.group(2)),
                        int(date_match.group(3)),
                    )
                except ValueError:
                    pass

    return date.today()


def _compute_version_hash(text: str) -> str:
    """SHA-256 hex digest of the normalised text for version tracking."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _clean_ocr_artefacts(text: str) -> str:
    """Remove common OCR / HTML artefacts from scraped text."""
    # Replace non-breaking spaces with regular spaces
    text = text.replace("\u00a0", " ")
    # Remove zero-width spaces and soft hyphens
    text = re.sub(r"[\u200B-\u200D\uFEFF\u00AD\u2060\u200C\u200D\u200E\u200F]", "", text)
    # Collapse multiple whitespace
    text = re.sub(r"\s+", " ", text)
    return text.strip()


# ---------------------------------------------------------------------------
# Sentence-aware hierarchical splitting (used for fine-grained chunks)
# ---------------------------------------------------------------------------


def build_sentence_level_chunks(
    raw_paragraphs: list[dict[str, Any]],
    *,
    source_type: str,
    title: str,
) -> list[dict[str, Any]]:
    """Take a list of paragraph dicts and split each into Satz-level chunks.

    Each input dict must have at least a ``text`` key.  Optional keys:
    ``paragraph``, ``absatz``.

    Returns enriched chunk dicts with ``unit_type``, ``hierarchy_path``,
    ``text_content``, ``effective_date``, ``source_url``, ``version_hash``.
    """
    chunks: list[dict[str, Any]] = []

    for para in raw_paragraphs:
        raw_text = para.get("text", "")
        if not raw_text or not raw_text.strip():
            continue

        sentences = _split_into_sentences(normalize_text(raw_text))
        if not sentences:
            continue

        para_num = para.get("paragraph", "?")
        absatz_num = para.get("absatz", "")
        effective_date = para.get("effective_date", date.today().isoformat())
        source_url = para.get(
            "source_url", urljoin(_BASE, _SOURCE_TYPE_PREFIX.get(source_type, "/"))
        )

        if len(sentences) == 1:
            # Single-sentence paragraph → one chunk
            hierarchy = _build_hierarchy(title, para_num, absatz_num, "1")
            chunks.append(
                _make_chunk(
                    source_type=source_type,
                    title=title,
                    hierarchy=hierarchy,
                    text=sentences[0],
                    unit_type="satz",
                    effective_date=effective_date,
                    source_url=source_url,
                )
            )
        else:
            # Multi-sentence → one chunk per sentence
            for idx, sentence in enumerate(sentences, start=1):
                hierarchy = _build_hierarchy(title, para_num, absatz_num, str(idx))
                chunks.append(
                    _make_chunk(
                        source_type=source_type,
                        title=title,
                        hierarchy=hierarchy,
                        text=sentence,
                        unit_type="satz",
                        effective_date=effective_date,
                        source_url=source_url,
                    )
                )

    return chunks


def _build_hierarchy(title: str, paragraph: str, absatz: str, satz: str) -> list[str]:
    parts = [title, f"§ {paragraph}"]
    if absatz:
        parts.append(f"Abs. {absatz}")
    parts.append(f"Satz {satz}")
    return parts


def _make_chunk(
    *,
    source_type: str,
    title: str,
    hierarchy: list[str],
    text: str,
    unit_type: str,
    effective_date: str,
    source_url: str,
) -> dict[str, Any]:
    return {
        "id": str(uuid4()),
        "source_type": source_type,
        "title": title,
        "unit_type": unit_type,
        "hierarchy_path": " > ".join(hierarchy),
        "text_content": text,
        "effective_date": effective_date,
        "source_url": source_url,
        "version_hash": _compute_version_hash(text),
        "chunk_id": str(uuid4()),
    }
