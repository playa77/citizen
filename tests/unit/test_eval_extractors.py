"""Norm extraction and metric normalisation for the eval harness (CR-13, F-19).

Pins the citation formats the goldset and prompt set 3.0.0 use, plus the
three defects found in the prompt-upgrade review: spelled-out "Satz",
"§§" lists, and trailing prose swallowed into the statute name.
"""

from __future__ import annotations

import pytest

from eval.extractors import _hierarchy_to_norm, extract_norm_references
from eval.goldset_loader import Citation
from eval.metrics import (
    compute_citation_precision,
    compute_quote_verification_rate,
    compute_sourced_quote_verification_rate,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("§ 11b Abs. 3 S. 2 Nr. 1-3 SGB II", {"§ 11b SGB II"}),
        ("§ 31 Abs. 1 Satz 2 SGB II", {"§ 31 SGB II"}),
        ("§ 48 Abs. 1 Satz 2 Nr. 3 SGB X aufgehoben", {"§ 48 SGB X"}),
        ("nach § 22 Abs. 1 SGB II zu übernehmen", {"§ 22 SGB II"}),
        ("§§ 45, 48 SGB X", {"§ 45 SGB X", "§ 48 SGB X"}),
        ("§§ 45/48/50 SGB X", {"§ 45 SGB X", "§ 48 SGB X", "§ 50 SGB X"}),
        ("§§ 45 und 48 SGB X", {"§ 45 SGB X", "§ 48 SGB X"}),
        ("§ 41a Abs. 1, 3, 6 SGB II", {"§ 41a SGB II"}),
        ("§ 40 Abs. 2 Nr. 3 SGB II i.V.m. § 330 Abs. 3 SGB III", {"§ 40 SGB II", "§ 330 SGB III"}),
        ("§ 12 Abs. 4 SGB II a.F. (bis 30.06.2026)", {"§ 12 SGB II"}),
        ("Anhörung (§ 24 SGB X)", {"§ 24 SGB X"}),
        ("§ 1924 BGB", {"§ 1924 BGB"}),
        ("§ 16 ErbStG", {"§ 16 ErbStG"}),
        ("§ 17 HöfeO", {"§ 17 HöfeO"}),
        ("§ 84 Abs. 1 S. 1 SGG", {"§ 84 SGG"}),
        ("§ 22 Kosten der Unterkunft", set()),  # prose, not a statute
        ("Fachbegriff (§ X Gesetz)", set()),  # prompt placeholder
    ],
)
def test_extract_norm_references(text: str, expected: set[str]) -> None:
    assert extract_norm_references(text) == expected


def test_case_law_citation_kept_verbatim() -> None:
    cite = "BSG, Urt. v. 19.02.2009 - B 4 AS 30/08 R"
    assert cite in extract_norm_references(cite)


def test_hierarchy_and_text_citation_share_a_key() -> None:
    hierarchy = _hierarchy_to_norm("SGB II > § 31 > Abs. 1")
    assert hierarchy is not None
    assert extract_norm_references(hierarchy) == extract_norm_references("(§ 31 Abs. 1 SGB II)")


def test_citation_precision_normalises_expected_norms() -> None:
    expected = [Citation(norm="§ 11b Abs. 2 S. 1 SGB II"), Citation(norm="§ 84 Abs. 1 S. 1 SGG")]
    assert compute_citation_precision({"§ 11b SGB II", "§ 84 SGG"}, expected) == 1.0
    assert compute_citation_precision({"§ 11b SGB II", "§ 22 SGB II"}, expected) == 0.5


def test_sourced_quote_verification_ignores_unsourced_claims() -> None:
    claims = [
        {"evidence_chunk_id": "c1", "verification_status": "exakt"},
        {"evidence_chunk_id": "", "verification_status": "unverifiziert"},
    ]
    assert compute_quote_verification_rate(claims) == 0.5
    assert compute_sourced_quote_verification_rate(claims) == 1.0
    assert compute_sourced_quote_verification_rate([claims[1]]) is None
