# Version: 1.0.0 | 2026-07-12
"""Pure metric computation functions for goldset evaluation.

All functions are deterministic — no LLM or DB calls. They take extracted
pipeline values and expected goldset values and return numeric scores.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.services.fristen import compute_widerspruchsfrist
from eval.extractors import extract_norm_references
from eval.goldset_loader import (
    Citation,
    GoldsetCase,
    LegalIssue,
)

if TYPE_CHECKING:
    from app.services.pseudonymization import PiiMapping
    from eval.goldset_loader import PiiAnnotation


def compute_issue_recall(
    pipeline_issues: list[set[str]],
    expected_issues: list[LegalIssue],
) -> float:
    """Compute issue recall between pipeline output and goldset expectations.

    **Strategy (Tier 1 matching):**  For each expected issue, extract
    §-references from its ``issue`` text and ``norm_chain`` entries using
    :func:`~eval.extractors.extract_norm_references`.  Then greedily match:
    each pipeline issue set is compared against each expected issue set; if
    they share at least one §-reference, it's a match.  Each pipeline issue
    can match at most one expected issue.

    Returns ``matches / total_expected`` in range ``[0, 1]``.

    Parameters
    ----------
    pipeline_issues :
        One ``set[str]`` of norm references per pipeline issue, as produced by
        :func:`~eval.extractors.extract_issues_from_pipeline`.
    expected_issues :
        The ``expected.legal_issues`` list from a goldset case.

    Returns
    -------
    float
        Recall score.
    """
    if not expected_issues:
        return 1.0  # nothing expected, nothing missed

    # Build §-reference sets for each expected issue (from issue text + norm_chain)
    expected_norm_sets: list[set[str]] = []
    for issue in expected_issues:
        norms: set[str] = set()
        norms.update(extract_norm_references(issue.issue))
        for chain_entry in issue.norm_chain:
            norms.update(extract_norm_references(chain_entry))
        expected_norm_sets.append(norms)

    # Greedy matching: each pipeline issue can match at most one expected issue
    matched_expected: set[int] = set()

    for pipeline_set in pipeline_issues:
        if not pipeline_set:
            continue  # pipeline issue with no norm references — can't match
        for exp_idx, exp_set in enumerate(expected_norm_sets):
            if exp_idx in matched_expected:
                continue
            if pipeline_set & exp_set:  # at least one shared §-reference
                matched_expected.add(exp_idx)
                break  # each pipeline issue matches at most one expected issue

    return len(matched_expected) / len(expected_issues)


def compute_citation_precision(
    pipeline_norms: set[str],
    expected_citations: list[Citation],
) -> float:
    """Compute citation precision between pipeline output and goldset expectations.

    Precision is defined as:

        ``|correct| / max(|correct| + |extra|, 1)``

    where:

    * ``correct`` = pipeline norms that appear in expected citations
    * ``extra`` = pipeline norms that are not expected

    If no expected citations exist and the pipeline produced none, precision
    is ``1.0``.

    Parameters
    ----------
    pipeline_norms :
        Set of norm strings extracted from the pipeline output, as produced by
        :func:`~eval.extractors.extract_citations_from_pipeline`.
    expected_citations :
        The ``expected.citations`` list from a goldset case.

    Returns
    -------
    float
        Precision score in ``[0, 1]``.
    """
    expected_norms: set[str] = {c.norm for c in expected_citations}

    if not expected_norms and not pipeline_norms:
        return 1.0  # no expectations, none produced

    correct = pipeline_norms & expected_norms  # norms in both
    extra = pipeline_norms - expected_norms  # norms produced but not expected

    denominator = max(len(correct) + len(extra), 1)
    return len(correct) / denominator


def compute_calculation_exact_match(
    pipeline_values: dict[str, float],
    expected_values: dict[str, Any],
) -> float:
    """Compute exact-match accuracy for numeric calculation values.

    Each numeric key in ``expected_values`` is compared against the
    corresponding key in ``pipeline_values``.  A match requires
    ``abs(pipeline - expected) < 0.005``.

    Keys with non-numeric values in ``expected_values`` (e.g. strings like
    ``"rechtswidrig"`` or ``"Keine Anspruchsberechnung..."``) are **skipped**
    — they represent qualitative annotations that cannot be compared as floats.

    Returns ``matches / total_numeric_keys`` in range ``[0, 1]``.
    If ``expected_values`` has no numeric keys, returns ``1.0``.

    Parameters
    ----------
    pipeline_values :
        Pipeline-extracted values keyed by goldset key, as produced by
        :func:`~eval.extractors.extract_calculation_values`.
    expected_values :
        The ``expected.calculation`` dict from a goldset case.

    Returns
    -------
    float
        Exact-match accuracy.
    """
    numeric_expected: dict[str, float] = {}
    for key, val in expected_values.items():
        try:
            numeric_expected[key] = float(val)
        except (TypeError, ValueError):
            # Skip non-numeric expected values (e.g. qualitative annotations)
            continue

    if not numeric_expected:
        return 1.0  # no numeric expectations

    matches = 0
    for key, expected_val in numeric_expected.items():
        pipeline_val = pipeline_values.get(key)
        if pipeline_val is not None and abs(pipeline_val - expected_val) < 0.005:
            matches += 1

    return matches / len(numeric_expected)


def compute_reconciliation_exact_match(
    pipeline_values: dict[str, float],
    expected_values: dict[str, Any],
) -> float | None:
    """Compute exact match for the full Bedarf-vs-Einkommen reconciliation.

    This metric checks whether the pipeline's recomputed ``anspruch_monatlich``
    (derived from the full reconciliation in :func:`reconcile_bedarf_einkommen`)
    matches the goldset's expected ``anspruch_monatlich`` value.  This is the
    single most important calculation — getting the Anspruch right means the
    entire Bedarf-vs-Einkommen computation is correct.

    Returns ``1.0`` if the recomputed ``anspruch_monatlich`` matches
    ``expected_values["anspruch_monatlich"]`` within 0.5 cents, ``0.0`` if it
    doesn't, or ``None`` if no ``anspruch_monatlich`` is available in either
    source.

    Parameters
    ----------
    pipeline_values :
        Pipeline-extracted values keyed by goldset key, as produced by
        :func:`~eval.extractors.extract_calculation_values`.
    expected_values :
        The ``expected.calculation`` dict from a goldset case.
    """
    # Extract expected anspruch_monatlich.
    expected_raw = expected_values.get("anspruch_monatlich")
    if expected_raw is None:
        return None
    try:
        expected = float(expected_raw)
    except (TypeError, ValueError):
        return None

    # Extract pipeline anspruch_monatlich.
    pipeline_raw = pipeline_values.get("anspruch_monatlich")
    if pipeline_raw is None:
        return None

    if abs(pipeline_raw - expected) < 0.005:
        return 1.0
    return 0.0


def compute_frist_exact_match(
    case: GoldsetCase,
) -> float | None:
    """Run the deterministic Fristen engine against a goldset case's expected Frist.

    Compares ``compute_widerspruchsfrist()`` output against
    ``case.expected.widerspruchsfrist.frist_ende``.

    Returns ``1.0`` for exact match, ``0.0`` for mismatch, or ``None`` if
    the goldset case has no widerspruchsfrist expectations.
    """
    from datetime import date

    expected_frist = case.expected.widerspruchsfrist
    if expected_frist is None or expected_frist.frist_ende is None:
        return None  # no expectation to compare against

    # Build the engine inputs from the case's widerspruchsfrist metadata.
    bescheid_datum = expected_frist.bescheid_datum
    if bescheid_datum is None:
        return None  # can't compute without a Bescheid date

    aufgabe = expected_frist.aufgabe_zur_post
    ist_va = not (
        isinstance(expected_frist.frist_ende, str)
        and expected_frist.frist_ende == "kein_verwaltungsakt"
    )

    # rbb_status detection: check if the goldset has rbb_fehlerhaft flag
    rbb_status: str = "korrekt"
    extra = expected_frist.model_extra or {}
    if extra.get("rbb_fehlerhaft") or extra.get("massgebliche_frist") == "jahresfrist_66_2_sgg":
        rbb_status = "fehlerhaft"

    result = compute_widerspruchsfrist(
        bescheid_datum=bescheid_datum,
        aufgabe_zur_post=aufgabe,
        rbb_status=rbb_status,  # type: ignore[arg-type]
        ist_verwaltungsakt=ist_va,
    )

    # Compare
    expected_ende = expected_frist.frist_ende
    if isinstance(expected_ende, str) and expected_ende == "kein_verwaltungsakt":
        return 1.0 if result.frist_typ == "kein_va" else 0.0

    if isinstance(expected_ende, str) and expected_ende == "nicht_anwendbar":
        # Not a date to compare — skip
        return None

    # Convert ISO string to date if needed (YAML stores dates as strings)
    if isinstance(expected_ende, str):
        try:
            expected_ende = date.fromisoformat(expected_ende)
        except (ValueError, TypeError):
            return None  # Can't parse — skip

    # Date comparison
    if result.frist_ende == expected_ende:
        return 1.0
    return 0.0


def compute_quote_verification_rate(verified_claims: list[dict[str, Any]]) -> float:
    """Compute the fraction of claims that passed verification.

    A claim is considered "verified" if its ``verification_status`` is
    ``"exakt"`` or ``"normalisiert"``.

    If ``verified_claims`` is empty (no claims produced), returns ``0.0``.

    Parameters
    ----------
    verified_claims :
        The ``verified_claims`` list from ``PipelineOutput``. Each dict is
        expected to have a ``verification_status`` key (WP-12 format).

    Returns
    -------
    float
        Quote verification rate in ``[0, 1]``.
    """
    if not verified_claims:
        return 0.0
    verified = sum(
        1 for vc in verified_claims if vc.get("verification_status") in ("exakt", "normalisiert")
    )
    return verified / len(verified_claims)


def compute_assessment_match(
    pipeline_assessment: str | None,
    expected_assessment: str | None,
) -> float | None:
    """Compute exact match for the overall assessment classification.

    Parameters
    ----------
    pipeline_assessment :
        Assessment extracted from pipeline output by
        :func:`~eval.extractors.extract_assessment_from_pipeline`.
    expected_assessment :
        ``expected.overall_assessment`` from a goldset case.

    Returns
    -------
    float | None
        ``1.0`` if exact match, ``0.0`` if mismatch, ``None`` if
        ``expected_assessment`` is ``None`` (not applicable).
    """
    if expected_assessment is None:
        return None  # not applicable
    if pipeline_assessment is None:
        return 0.0  # could not extract
    return 1.0 if pipeline_assessment == expected_assessment else 0.0


# ---------------------------------------------------------------------------
# PII metrics (WP-32)
# ---------------------------------------------------------------------------


def compute_leakage_rate(
    pseudonymized_text: str,
    pii_mapping: PiiMapping | dict[str, Any],
) -> float:
    """Check if any original PII values appear in pseudonymized text.

    Returns ``0.0`` if no leakage (all original values replaced), ``1.0`` if
    any leakage found. This is a hard CI gate — any leakage fails.

    Uses casefolded matching for tolerance. Scans only values that were
    actually mapped (original PII) — not the entire mapping structure.

    Parameters
    ----------
    pseudonymized_text :
        Text after pseudonymization (should contain only placeholders).
    pii_mapping :
        ``PiiMapping`` instance or its ``to_dict()`` representation.
        Must contain the ``value_to_placeholder`` mapping.

    Returns
    -------
    float
        ``0.0`` for clean, ``1.0`` if any original PII leaks through.
    """
    # Extract original values from the mapping
    if isinstance(pii_mapping, dict):
        value_to_placeholder = pii_mapping.get("value_to_placeholder", {})
    else:
        value_to_placeholder = getattr(pii_mapping, "value_to_placeholder", {})

    if not value_to_placeholder:
        return 0.0  # Nothing to check — no PII mapped

    text_lower = pseudonymized_text.casefold()

    for original_value in value_to_placeholder:
        if not original_value or len(original_value) < 2:
            continue
        # Skip placeholder-formatted strings that might be in the mapping
        if original_value.startswith("[["):
            continue
        if original_value.casefold() in text_lower:
            return 1.0  # Leak detected

    return 0.0


def compute_pii_recall(
    text: str,
    annotations: list[PiiAnnotation],
    pii_mapping: PiiMapping | dict[str, Any],
) -> float:
    """Fraction of annotated PII spans that were correctly pseudonymized.

    A span is *recalled* if the pseudonymized text at that span position
    contains a placeholder (``[[...]]``) and not the original value.

    Parameters
    ----------
    text :
        Original input text (pre-pseudonymization).
    annotations :
        Goldset ``pii_annotations`` for this case.
    pii_mapping :
        ``PiiMapping`` instance or dict representation.

    Returns
    -------
    float
        Recall in ``[0, 1]``. Returns ``1.0`` if no annotations.
    """
    if not annotations:
        return 1.0

    # Run pseudonymization to get the pseudonymized text
    from app.services.pseudonymization import pseudonymize

    pseudo_text, _ = pseudonymize(text)

    total_spans = 0
    recalled = 0

    for ann in annotations:
        for span in ann.spans:
            total_spans += 1
            span_text = text[span.start : span.end]
            # Check that the span position in pseudonymized text has a placeholder
            if span.end > len(pseudo_text):
                continue  # Text changed length — can't verify
            pseudonymized_slice = pseudo_text[span.start : span.end]
            # Recalled if placeholder present in the slice OR original value absent
            if "[[" in pseudonymized_slice or span_text not in pseudo_text:
                recalled += 1

    return recalled / total_spans if total_spans > 0 else 1.0


def compute_pii_precision(
    text: str,
    annotations: list[PiiAnnotation],
    pii_mapping: PiiMapping | dict[str, Any],
) -> float:
    """Fraction of pseudonymized spans that correspond to actual PII annotations.

    High precision = few false positives (regions pseudonymized that weren't
    marked as PII in the goldset).

    Since goldset annotations are a subset of all possible PII, this is an
    approximation: we count how many placeholder instances appear in the
    pseudonymized text, and how many of those overlap with annotated spans.

    Parameters
    ----------
    text :
        Original input text.
    annotations :
        Goldset ``pii_annotations`` for this case.
    pii_mapping :
        ``PiiMapping`` instance or dict representation.

    Returns
    -------
    float
        Precision in ``[0, 1]``.
    """
    from app.services.pseudonymization import pseudonymize

    pseudo_text, _ = pseudonymize(text)

    if not annotations:
        # If no annotations but text was pseudonymized, precision is 0
        if "[[" in pseudo_text:
            return 0.0
        return 1.0

    # Count all placeholder instances in pseudonymized text
    import re

    placeholder_spans: list[tuple[int, int]] = []
    for match in re.finditer(r"\[\[\w+\]\]", pseudo_text):
        placeholder_spans.append((match.start(), match.end()))

    if not placeholder_spans:
        return 1.0  # Nothing pseudonymized, nothing false

    # Build set of annotated positions
    annotated_positions: set[tuple[int, int]] = set()
    for ann in annotations:
        for span in ann.spans:
            annotated_positions.add((span.start, span.end))

    # Count placeholders that overlap with annotated spans
    true_positives = 0
    for ps_start, ps_end in placeholder_spans:
        is_tp = any(
            not (ps_end <= a_start or ps_start >= a_end) for a_start, a_end in annotated_positions
        )
        if is_tp:
            true_positives += 1

    return true_positives / len(placeholder_spans)


def compute_over_redaction_count(
    pseudonymized_text: str,
    original_text: str,
    negative_controls: list[str],
) -> int:
    """Count how many negative control strings were incorrectly redacted.

    A negative control is a string that *must* survive pseudonymization
    (e.g. Bescheid dates, amounts, authority names). Each missing negative
    control in the pseudonymized text counts as one over-redaction.

    Must be ``0`` for GS-012 to pass.

    Parameters
    ----------
    pseudonymized_text :
        Text after pseudonymization.
    original_text :
        Original input text (for verification that the control existed).
    negative_controls :
        List of strings that should remain unchanged.

    Returns
    -------
    int
        Count of negative controls incorrectly redacted.
    """
    if not negative_controls:
        return 0

    count = 0
    for nc in negative_controls:
        # Verify it exists in the original
        if nc not in original_text:
            continue  # Skip controls that aren't in the original
        # Check if it survived
        if nc not in pseudonymized_text:
            # Check if a placeholder replaced it
            # (over-redaction means it was removed/replaced)
            count += 1

    return count


def compute_reinjection_integrity(
    original_text: str,
    pseudonymized_text: str,
    depseudonymized_text: str,
) -> float:
    """Roundtrip fidelity: depseudonymized_text should equal original_text.

    Returns ``1.0`` for perfect match. For partial match, returns fraction
    of characters that match, with tolerance for whitespace differences.

    Parameters
    ----------
    original_text :
        Original input text.
    pseudonymized_text :
        Text after pseudonymization (not used directly but provided for
        diagnostic logging).
    depseudonymized_text :
        Text after reinjection (depseudonymization).

    Returns
    -------
    float
        Roundtrip fidelity in ``[0, 1]``.
    """
    import difflib

    # Normalize whitespace for comparison
    orig_normalized = " ".join(original_text.split())
    depseudo_normalized = " ".join(depseudonymized_text.split())

    if orig_normalized == depseudo_normalized:
        return 1.0

    # Token-level comparison
    orig_tokens = orig_normalized.split()
    depseudo_tokens = depseudo_normalized.split()

    if not orig_tokens:
        return 1.0 if not depseudo_tokens else 0.0

    # Use SequenceMatcher for token-level match ratio
    matcher = difflib.SequenceMatcher(None, orig_tokens, depseudo_tokens)
    return matcher.ratio()
