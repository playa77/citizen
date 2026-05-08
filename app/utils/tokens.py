"""Prompt and token budgeting utilities.

Provides helpers to keep LLM prompts within configurable character budgets,
preventing accidental giant prompts that explode latency and cost.
"""

# Semantic Version: 0.1.0

from __future__ import annotations


def trim_text(text: str, max_chars: int) -> str:
    """Trim *text* to at most *max_chars* characters.

    Returns *text* unchanged if it already fits within the budget.
    Otherwise returns the prefix of *text* up to *max_chars* characters
    (no ellipsis suffix — the caller can add one if desired).

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
    return text[:max_chars]


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
