"""Text normalisation, regex cleaning, and chunking helpers."""

import re
import unicodedata

# Multiple horizontal whitespace (within a line) → single space
_HORIZONTAL_WS_RE = re.compile(r"[^\S\n]+")

# Lines that consist purely of optional whitespace
_BLANK_LINE_RE = re.compile(r"^[ \t]*$", re.MULTILINE)

# Three or more consecutive newlines → two newlines (preserve paragraph breaks)
_EXCESS_NEWLINES_RE = re.compile(r"\n{3,}")

# Characters commonly produced by OCR artefacts (zero-width, BOM, soft hyphens)
_INVISIBLE_RE = re.compile(r"[\u200B-\u200D\uFEFF\u00AD\u2060\u200C\u200D\u200E\u200F]")


def normalize_text(raw: str) -> str:
    """Return cleaned, deterministic UTF-8 text from arbitrary input.

    Steps applied in order:
    1. NFC unicode normalisation
    2. Strip invisible / OCR artefact characters
    3. Collapse horizontal whitespace within each line
    4. Remove lines that are entirely blank
    5. Collapse excessive newline runs into a single newline
    6. Strip leading / trailing whitespace from the entire string
    """
    text = unicodedata.normalize("NFC", raw)
    text = _INVISIBLE_RE.sub("", text)
    text = _HORIZONTAL_WS_RE.sub(" ", text)
    text = _BLANK_LINE_RE.sub("", text)
    text = _EXCESS_NEWLINES_RE.sub("\n", text)
    return text.strip()
