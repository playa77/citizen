"""Deterministic evidence verification — local quote-matching against source chunks.

Replaces the expensive LLM verification pass (WP-007 / WP-008) with a fast,
deterministic check: for each claim, verify that its ``evidence_quote`` actually
appears in the chunk identified by ``evidence_chunk_id``.

Semantic Version: 0.1.0
"""

from __future__ import annotations

import logging
from typing import Any


logger = logging.getLogger(__name__)


def _normalize_whitespace(text: str) -> str:
    """Collapse all whitespace runs to single spaces and strip."""
    return " ".join(text.split())


def verify_claims_against_chunks(
    claims: list[dict[str, Any]],
    chunks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Verify each claim by checking whether ``evidence_quote`` appears in the
    source chunk's ``text_content``.

    Algorithm
    ---------
    1. Build a lookup ``dict[str, dict]`` mapping ``chunk_id`` → chunk.
    2. For each claim:
       a. Find the source chunk via ``evidence_chunk_id``.
       b. Check if ``evidence_quote`` appears exactly in ``text_content``.
       c. If not, try again with normalized whitespace.
       d. If matched: ``verified=True``, preserve ``confidence_score``.
       e. If not matched: ``verified=False``, reduce ``confidence_score``
          to at most 0.45.
    3. Always preserve: ``claim_text``, ``confidence_score``, ``claim_type``,
       ``question``, ``evidence_chunk_id``, ``evidence_hierarchy``,
       ``evidence_quote``, ``verified``, ``reasoning``.

    Parameters
    ----------
    claims :
        List of claim dicts as produced by ``generate_grounded_answer()``.
        Each must have keys: ``claim_text``, ``confidence_score``,
        ``claim_type``, ``question``, ``evidence_chunk_id``,
        ``evidence_hierarchy``, ``evidence_quote``.
    chunks :
        List of chunk dicts as returned by retrieval. Each must have keys
        ``chunk_id`` and ``text_content``.

    Returns
    -------
    list[dict[str, Any]]
        Verified claims with added ``verified`` (bool) and ``reasoning``
        (str, German) fields. ``confidence_score`` may be adjusted downward
        for unmatched claims.
    """
    # Build chunk lookup by ID.
    chunk_map: dict[str, dict[str, Any]] = {}
    for c in chunks:
        cid = c.get("chunk_id", "")
        if cid:
            chunk_map[cid] = c

    verified_claims: list[dict[str, Any]] = []

    for claim in claims:
        claim = dict(claim)  # shallow copy so we don't mutate the input

        evidence_chunk_id = str(claim.get("evidence_chunk_id", "")).strip()
        evidence_quote = str(claim.get("evidence_quote", "")).strip()
        confidence = float(claim.get("confidence_score", 0.5))
        confidence = max(0.0, min(1.0, confidence))

        if not evidence_chunk_id or not evidence_quote:
            # No evidence to verify — downgrade.
            verified_claims.append({
                **claim,
                "verified": False,
                "confidence_score": min(confidence, 0.45),
                "reasoning": (
                    "Keine Überprüfung möglich: evidence_chunk_id oder "
                    "evidence_quote fehlen."
                ),
            })
            continue

        chunk = chunk_map.get(evidence_chunk_id)
        if chunk is None:
            verified_claims.append({
                **claim,
                "verified": False,
                "confidence_score": min(confidence, 0.35),
                "reasoning": (
                    f"Quell-Chunk {evidence_chunk_id} nicht in den "
                    f"abgerufenen Chunks gefunden."
                ),
            })
            continue

        text_content = str(chunk.get("text_content", ""))
        if not text_content:
            verified_claims.append({
                **claim,
                "verified": False,
                "confidence_score": min(confidence, 0.45),
                "reasoning": (
                    f"Chunk {evidence_chunk_id} hat keinen text_content."
                ),
            })
            continue

        # Strategy 1: exact match.
        matched = evidence_quote in text_content

        # Strategy 2: normalized whitespace match.
        if not matched and evidence_quote and text_content:
            matched = (
                _normalize_whitespace(evidence_quote)
                in _normalize_whitespace(text_content)
            )

        if matched:
            verified_claims.append({
                **claim,
                "verified": True,
                "confidence_score": confidence,
                "reasoning": (
                    f"Zitat in Chunk {evidence_chunk_id} exakt "
                    f"(oder whitespace-normalisiert) gefunden."
                ),
            })
        else:
            verified_claims.append({
                **claim,
                "verified": False,
                "confidence_score": min(confidence, 0.45),
                "reasoning": (
                    f"Zitat nicht in Chunk {evidence_chunk_id} gefunden "
                    f"(weder exakt noch whitespace-normalisiert)."
                ),
            })

    # Log summary
    verified_count = sum(1 for vc in verified_claims if vc.get("verified"))
    logger.info(
        "verify_claims_against_chunks: %d/%d claims verified",
        verified_count,
        len(verified_claims),
    )

    return verified_claims
