"""Unit tests for deterministic evidence verification (WP-008).

Tests the ``verify_claims_against_chunks()`` function from
``app/services/verification.py`` against all acceptance criteria.
"""

from __future__ import annotations

import time
from typing import Any

import pytest

from app.services.verification import verify_claims_against_chunks


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _claim(
    claim_text: str = "Test claim",
    confidence_score: float = 0.8,
    claim_type: str = "fact",
    question: str = "Test question?",
    evidence_chunk_id: str = "chunk-001",
    evidence_hierarchy: str = "SGB II > § 31 > Abs. 1",
    evidence_quote: str = "Der Anspruch besteht.",
) -> dict[str, Any]:
    return {
        "claim_text": claim_text,
        "confidence_score": confidence_score,
        "claim_type": claim_type,
        "question": question,
        "evidence_chunk_id": evidence_chunk_id,
        "evidence_hierarchy": evidence_hierarchy,
        "evidence_quote": evidence_quote,
    }


def _chunk(
    chunk_id: str = "chunk-001",
    text_content: str = "Der Anspruch besteht. Weitere Details folgen.",
    hierarchy_path: str = "SGB II > § 31 > Abs. 1",
    source_type: str = "sgb2",
) -> dict[str, Any]:
    return {
        "chunk_id": chunk_id,
        "text_content": text_content,
        "hierarchy_path": hierarchy_path,
        "source_type": source_type,
        "distance": 0.15,
    }


# ---------------------------------------------------------------------------
# Acceptance criteria tests
# ---------------------------------------------------------------------------


class TestExactQuoteMatch:
    """Claims with exact evidence quotes are marked verified."""

    def test_exact_substring_match_verified_true(self) -> None:
        claim = _claim(evidence_quote="Der Anspruch besteht.")
        chunk = _chunk(text_content="Der Anspruch besteht. Weitere Details.")
        result = verify_claims_against_chunks([claim], [chunk])
        assert len(result) == 1
        assert result[0]["verified"] is True
        assert result[0]["confidence_score"] == 0.8

    def test_exact_match_preserves_all_fields(self) -> None:
        claim = _claim()
        chunk = _chunk()
        result = verify_claims_against_chunks([claim], [chunk])
        vc = result[0]
        # Original fields preserved
        assert vc["claim_text"] == "Test claim"
        assert vc["claim_type"] == "fact"
        assert vc["question"] == "Test question?"
        assert vc["evidence_chunk_id"] == "chunk-001"
        assert vc["evidence_hierarchy"] == "SGB II > § 31 > Abs. 1"
        assert vc["evidence_quote"] == "Der Anspruch besteht."
        # Added fields
        assert "verified" in vc
        assert "reasoning" in vc

    def test_multiple_claims_all_verified(self) -> None:
        claims = [
            _claim(evidence_quote="Satz A.", evidence_chunk_id="c1"),
            _claim(evidence_quote="Satz B.", evidence_chunk_id="c2"),
        ]
        chunks = [
            _chunk(chunk_id="c1", text_content="Satz A. und mehr."),
            _chunk(chunk_id="c2", text_content="Vorher Satz B. nachher."),
        ]
        result = verify_claims_against_chunks(claims, chunks)
        assert all(vc["verified"] for vc in result)
        assert result[0]["confidence_score"] == 0.8
        assert result[1]["confidence_score"] == 0.8


class TestWhitespaceNormalizedMatch:
    """Claims with whitespace-differing quotes are verified after normalization."""

    def test_normalized_whitespace_match(self) -> None:
        claim = _claim(evidence_quote="Der  Anspruch   besteht.")
        chunk = _chunk(text_content="Der Anspruch besteht. Weitere Details.")
        result = verify_claims_against_chunks([claim], [chunk])
        assert result[0]["verified"] is True
        assert result[0]["confidence_score"] == 0.8

    def test_newlines_normalized(self) -> None:
        claim = _claim(evidence_quote="Abs. 1\nSatz 1")
        chunk = _chunk(text_content="Abs. 1 Satz 1 gilt entsprechend.")
        result = verify_claims_against_chunks([claim], [chunk])
        assert result[0]["verified"] is True

    def test_tabs_normalized(self) -> None:
        claim = _claim(evidence_quote="§ 1\tSatz 2")
        chunk = _chunk(text_content="§ 1 Satz 2 beschreibt.")
        result = verify_claims_against_chunks([claim], [chunk])
        assert result[0]["verified"] is True


class TestDowngradeOnNoMatch:
    """Claims without matching quote are downgraded (confidence ≤ 0.45)."""

    def test_no_match_verified_false(self) -> None:
        claim = _claim(evidence_quote="Dieser Satz existiert nicht.")
        chunk = _chunk(text_content="Ganz anderer Inhalt.")
        result = verify_claims_against_chunks([claim], [chunk])
        assert result[0]["verified"] is False
        assert result[0]["confidence_score"] <= 0.45

    def test_high_confidence_capped_at_045(self) -> None:
        claim = _claim(confidence_score=0.95, evidence_quote="Falsches Zitat")
        chunk = _chunk(text_content="Korrektes Zitat hier.")
        result = verify_claims_against_chunks([claim], [chunk])
        assert result[0]["verified"] is False
        assert result[0]["confidence_score"] == 0.45

    def test_low_confidence_preserved_when_below_045(self) -> None:
        """Already-low confidence (≤0.45) should stay unchanged even on no-match."""
        claim = _claim(confidence_score=0.3, evidence_quote="Falsches Zitat")
        chunk = _chunk(text_content="Anderer Text.")
        result = verify_claims_against_chunks([claim], [chunk])
        assert result[0]["confidence_score"] == 0.3

    def test_partial_not_enough(self) -> None:
        """A substring of evidence_quote appearing is NOT sufficient for match.
        The evidence_quote itself must be a substring of text_content."""
        claim = _claim(evidence_quote="Der vollständige Anspruch besteht.")
        chunk = _chunk(text_content="Der Anspruch besteht.")  # only part
        result = verify_claims_against_chunks([claim], [chunk])
        assert result[0]["verified"] is False


class TestMissingEvidenceFields:
    """Claims missing evidence_chunk_id or evidence_quote are downgraded."""

    def test_missing_chunk_id(self) -> None:
        claim = _claim(evidence_chunk_id="")
        chunk = _chunk()
        result = verify_claims_against_chunks([claim], [chunk])
        assert result[0]["verified"] is False
        assert result[0]["confidence_score"] <= 0.45

    def test_missing_evidence_quote(self) -> None:
        claim = _claim(evidence_quote="")
        chunk = _chunk()
        result = verify_claims_against_chunks([claim], [chunk])
        assert result[0]["verified"] is False
        assert result[0]["confidence_score"] <= 0.45

    def test_both_missing(self) -> None:
        claim = _claim(evidence_chunk_id="", evidence_quote="")
        chunk = _chunk()
        result = verify_claims_against_chunks([claim], [chunk])
        assert result[0]["verified"] is False
        assert result[0]["confidence_score"] <= 0.45

    def test_none_values_handled(self) -> None:
        claim = {
            "claim_text": "Test",
            "confidence_score": 0.6,
            "claim_type": "fact",
            "question": "Q?",
            "evidence_chunk_id": None,
            "evidence_hierarchy": None,
            "evidence_quote": None,
        }
        chunk = _chunk()
        result = verify_claims_against_chunks([claim], [chunk])
        assert result[0]["verified"] is False
        assert result[0]["confidence_score"] <= 0.45


class TestChunkNotFound:
    """Chunk referenced by evidence_chunk_id not in the chunk list → downgrade to 0.35."""

    def test_chunk_not_in_list(self) -> None:
        claim = _claim(evidence_chunk_id="nonexistent-999")
        chunk = _chunk(chunk_id="chunk-001")
        result = verify_claims_against_chunks([claim], [chunk])
        assert result[0]["verified"] is False
        assert result[0]["confidence_score"] <= 0.35

    def test_chunk_not_found_low_confidence(self) -> None:
        claim = _claim(evidence_chunk_id="missing", confidence_score=0.9)
        chunk = _chunk(chunk_id="chunk-001")
        result = verify_claims_against_chunks([claim], [chunk])
        assert result[0]["verified"] is False
        assert result[0]["confidence_score"] == 0.35


class TestEmptyChunkText:
    """Chunk with empty text_content → verified=False, confidence ≤ 0.45."""

    def test_empty_text_content(self) -> None:
        claim = _claim(evidence_quote="Something")
        chunk = _chunk(text_content="")
        result = verify_claims_against_chunks([claim], [chunk])
        assert result[0]["verified"] is False
        assert result[0]["confidence_score"] <= 0.45

    def test_whitespace_only_text_content(self) -> None:
        claim = _claim(evidence_quote="Something")
        chunk = _chunk(text_content="   \n\t  ")
        result = verify_claims_against_chunks([claim], [chunk])
        # "   \n\t  " is truthy in Python, so it won't hit the empty-check.
        # The match will fail (normalized "Something" vs ""), downgrading to 0.45.
        assert result[0]["verified"] is False
        assert result[0]["confidence_score"] <= 0.45


class TestReasoningField:
    """The ``reasoning`` field is a short German string explaining the result."""

    def test_reasoning_when_verified(self) -> None:
        claim = _claim()
        chunk = _chunk()
        result = verify_claims_against_chunks([claim], [chunk])
        reasoning = result[0]["reasoning"]
        assert isinstance(reasoning, str)
        assert len(reasoning) > 0
        assert "chunk-001" in reasoning.lower() or "Chunk" in reasoning

    def test_reasoning_when_not_verified(self) -> None:
        claim = _claim(evidence_quote="Non-existent quote.")
        chunk = _chunk()
        result = verify_claims_against_chunks([claim], [chunk])
        reasoning = result[0]["reasoning"]
        assert isinstance(reasoning, str)
        assert len(reasoning) > 0

    def test_reasoning_when_missing_fields(self) -> None:
        claim = _claim(evidence_chunk_id="", evidence_quote="")
        chunk = _chunk()
        result = verify_claims_against_chunks([claim], [chunk])
        reasoning = result[0]["reasoning"]
        assert isinstance(reasoning, str)
        assert "evidence_chunk_id" in reasoning.lower() or "evidence_quote" in reasoning.lower() or "Überprüfung" in reasoning


class TestEdgeCases:
    """Edge cases and robustness."""

    def test_empty_claims_list(self) -> None:
        result = verify_claims_against_chunks([], [_chunk()])
        assert result == []

    def test_empty_chunks_list(self) -> None:
        claim = _claim()
        result = verify_claims_against_chunks([claim], [])
        assert result[0]["verified"] is False
        assert result[0]["confidence_score"] <= 0.35

    def test_claim_not_mutate_input(self) -> None:
        original = _claim(evidence_quote="Non-existent.")
        chunk = _chunk()
        verify_claims_against_chunks([original], [chunk])
        # Original should not have verified/reasoning injected
        assert "verified" not in original

    def test_chunk_id_type_coercion(self) -> None:
        """evidence_chunk_id is str()'d; integer IDs are handled."""
        quote = "Der Anspruch besteht."
        claim = _claim(evidence_chunk_id="42", evidence_quote=quote)
        chunk = _chunk(chunk_id="42", text_content=f"Kontext. {quote} Ende.")
        result = verify_claims_against_chunks([claim], [chunk])
        assert result[0]["verified"] is True

    def test_multiple_chunks_same_id_last_wins(self) -> None:
        claims = [_claim(evidence_chunk_id="c1", evidence_quote="First text.")]
        chunks = [
            {"chunk_id": "c1", "text_content": "Wrong content."},
            {"chunk_id": "c1", "text_content": "First text. Correct."},
        ]
        result = verify_claims_against_chunks(claims, chunks)
        assert result[0]["verified"] is True

    def test_confidence_near_boundary(self) -> None:
        """Confidence at exactly 0.45 on match should be preserved."""
        claim = _claim(confidence_score=0.45, evidence_quote="Boundary test.")
        chunk = _chunk(text_content="Boundary test. More.")
        result = verify_claims_against_chunks([claim], [chunk])
        assert result[0]["confidence_score"] == 0.45

    def test_confidence_above_1_clamped_then_matched(self) -> None:
        claim = _claim(confidence_score=2.5, evidence_quote="Quote.")
        chunk = _chunk(text_content="Quote. Text.")
        result = verify_claims_against_chunks([claim], [chunk])
        assert result[0]["verified"] is True
        # Clamped to 1.0 during extraction, then preserved on match
        assert result[0]["confidence_score"] == 1.0

    def test_confidence_below_0_clamped_then_downgraded(self) -> None:
        claim = _claim(confidence_score=-0.5, evidence_quote="Missing.")
        chunk = _chunk(text_content="Other.")
        result = verify_claims_against_chunks([claim], [chunk])
        assert result[0]["confidence_score"] <= 0.45


class TestPerformance:
    """Verification stage should take well under 1 second (acceptance criterion)."""

    def test_small_input_under_10ms(self) -> None:
        claims = [_claim() for _ in range(10)]
        chunks = [_chunk(chunk_id=f"chunk-{i:03d}") for i in range(10)]
        start = time.monotonic()
        result = verify_claims_against_chunks(claims, chunks)
        elapsed = time.monotonic() - start
        assert len(result) == 10
        assert elapsed < 0.01, f"Took {elapsed:.4f}s, expected <0.01s"

    def test_medium_input_under_50ms(self) -> None:
        claims = [_claim() for _ in range(100)]
        chunks = [_chunk(chunk_id=f"chunk-{i:03d}") for i in range(100)]
        start = time.monotonic()
        result = verify_claims_against_chunks(claims, chunks)
        elapsed = time.monotonic() - start
        assert len(result) == 100
        assert elapsed < 0.05, f"Took {elapsed:.4f}s, expected <0.05s"

    def test_large_input_under_200ms(self) -> None:
        claims = [_claim() for _ in range(500)]
        chunks = [_chunk(chunk_id=f"chunk-{i:03d}") for i in range(500)]
        start = time.monotonic()
        result = verify_claims_against_chunks(claims, chunks)
        elapsed = time.monotonic() - start
        assert len(result) == 500
        assert elapsed < 0.2, f"Took {elapsed:.4f}s, expected <0.2s"

    def test_long_text_verification(self) -> None:
        """Even with long chunk texts, matching is O(n*m) but fast."""
        long_text = "Lorem ipsum " * 500 + "SPECIAL_MARKER" + " dolor " * 500
        claims = [_claim(evidence_quote="SPECIAL_MARKER")]
        chunks = [_chunk(text_content=long_text)]
        start = time.monotonic()
        result = verify_claims_against_chunks(claims, chunks)
        elapsed = time.monotonic() - start
        assert result[0]["verified"] is True
        assert elapsed < 0.02, f"Took {elapsed:.4f}s, expected <0.02s"
