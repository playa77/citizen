"""Prompt and token budgeting utilities.

Provides helpers to keep LLM prompts within configurable character budgets,
preventing accidental giant prompts that explode latency and cost.
"""

# Semantic Version: 0.2.0 | 2026-11-16 — CR-07 (F-07): trim_text accepts a
# truncation marker; trim_document marks cut document text for the model.
# 0.1.0

from __future__ import annotations

#: Appended when a document is cut before it reaches a model (CR-07, F-07).
#: Stage prompts tell the model that a text "kann gekürzt sein"; the marker
#: makes the cut observable, so verbatim quotes do not cross it.
DOCUMENT_TRUNCATION_MARKER = "\n[DOKUMENT GEKÜRZT]"


def trim_text(text: str, max_chars: int, marker: str = "") -> str:
    """Trim *text* to at most *max_chars* characters.

    Returns *text* unchanged if it already fits within the budget.
    Otherwise returns the prefix of *text* up to *max_chars* characters,
    followed by *marker* when given (the marker is not counted against the
    budget; default: no marker).

    Parameters
    ----------
    text :
        The input text to potentially trim.
    max_chars :
        Maximum allowed character count.

    Returns
    -------
    str
        *text* truncated to *max_chars* characters if necessary.
    """
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + marker


def trim_document(text: str, max_chars: int, marker: str = DOCUMENT_TRUNCATION_MARKER) -> str:
    """:func:`trim_text` for text a model reads: a cut is always marked."""
    return trim_text(text, max_chars, marker)


def estimate_tokens(text: str) -> int:
    """Return a rough token-count estimate for *text*.

    Uses a simple heuristic: 1 token ≈ 4 characters for German/English text.
    This is intentionally fast and local — no tiktoken dependency.

    Parameters
    ----------
    text :
        The text to estimate.

    Returns
    -------
    int
        Estimated token count (ceil division).
    """
    if not text:
        return 0
    # Ceil division: (len + 3)//4
    return (len(text) + 3) // 4
