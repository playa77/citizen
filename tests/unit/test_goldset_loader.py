"""Unit tests for goldset loader — v0.1.0 and v0.2.0 validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from eval.goldset_loader import (
    GoldsetCase,
    GoldsetDocument,
    PiiAnnotation,
    PiiSpan,
    audit_goldset,
    load_goldset,
    resolve_goldset_path,
)

_HERE = Path(__file__).resolve().parent
_GOLDSETS = _HERE.parent.parent / "eval" / "goldsets"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def v010_doc() -> GoldsetDocument:
    return load_goldset(str(_GOLDSETS / "goldset-v0.1.0.yaml"))


@pytest.fixture(scope="module")
def v020_doc() -> GoldsetDocument:
    return load_goldset(str(_GOLDSETS / "goldset-v0.2.0.yaml"))


# ---------------------------------------------------------------------------
# v0.1.0 — unchanged
# ---------------------------------------------------------------------------


class TestV010Loads:
    """v0.1.0 still loads correctly and is backward-compatible."""

    def test_version(self, v010_doc: GoldsetDocument) -> None:
        assert v010_doc.goldset.version == "0.1.0"

    def test_case_count(self, v010_doc: GoldsetDocument) -> None:
        assert len(v010_doc.cases) == 10

    def test_gs001_loaded(self, v010_doc: GoldsetDocument) -> None:
        case = next(c for c in v010_doc.cases if c.id == "GS-001")
        assert case.title == "Bewilligungsbescheid — Erwerbstätigenfreibetrag mit veralteter 20%-Staffel berechnet"
        assert case.input_document.text
        assert case.expected.overall_assessment == "teilweise_rechtswidrig"
        # v0.1.0 has no pii_annotations field
        assert hasattr(case, "pii_annotations")
        assert case.pii_annotations == []

    def test_audit_passes(self, v010_doc: GoldsetDocument) -> None:
        warnings = audit_goldset(v010_doc)
        assert len(warnings) == 0, f"Audit warnings: {warnings}"


# ---------------------------------------------------------------------------
# v0.2.0 — additive: v0.1.0 cases unchanged, 2 new cases
# ---------------------------------------------------------------------------


class TestV020Loads:
    """v0.2.0 loads correctly with PII annotations."""

    def test_version(self, v020_doc: GoldsetDocument) -> None:
        assert v020_doc.goldset.version == "0.2.0"

    def test_case_count(self, v020_doc: GoldsetDocument) -> None:
        # v0.1.0 (10) + GS-011 + GS-012 = 12
        assert len(v020_doc.cases) == 12

    def test_v010_cases_still_present(self, v020_doc: GoldsetDocument) -> None:
        v010_ids = {f"GS-{i:03d}" for i in range(1, 11)}
        actual_ids = {c.id for c in v020_doc.cases}
        assert v010_ids.issubset(actual_ids), f"Missing v0.1.0 cases: {v010_ids - actual_ids}"

    def test_new_cases_present(self, v020_doc: GoldsetDocument) -> None:
        actual_ids = {c.id for c in v020_doc.cases}
        assert "GS-011" in actual_ids
        assert "GS-012" in actual_ids

    def test_v010_titles_unchanged(self, v020_doc: GoldsetDocument) -> None:
        v010 = load_goldset(str(_GOLDSETS / "goldset-v0.1.0.yaml"))
        v020 = v020_doc
        v010_by_id = {c.id: c for c in v010.cases}
        for c in v020.cases:
            if c.id in v010_by_id:
                assert c.title == v010_by_id[c.id].title, (
                    f"Case {c.id} title changed in v0.2.0"
                )

    def test_audit_passes(self, v020_doc: GoldsetDocument) -> None:
        warnings = audit_goldset(v020_doc)
        assert len(warnings) == 0, f"Audit warnings: {warnings}"


# ---------------------------------------------------------------------------
# PII annotations validation
# ---------------------------------------------------------------------------


class TestPiiAnnotations:
    """PII annotations in v0.2.0 are correctly structured."""

    def test_gs001_has_pii(self, v020_doc: GoldsetDocument) -> None:
        case = next(c for c in v020_doc.cases if c.id == "GS-001")
        assert len(case.pii_annotations) > 0
        # Should have person, bg_nummer, address annotations
        types = {a.type for a in case.pii_annotations}
        assert "person" in types
        assert "bg_nummer" in types
        assert "address" in types

    def test_gs007_minimal_pii(self, v020_doc: GoldsetDocument) -> None:
        """GS-007 (kein VA case) has minimal PII — just name."""
        case = next(c for c in v020_doc.cases if c.id == "GS-007")
        assert len(case.pii_annotations) > 0
        types = {a.type for a in case.pii_annotations}
        # Person and address should be present
        assert "person" in types

    def test_gs011_has_all_pii_types(self, v020_doc: GoldsetDocument) -> None:
        """GS-011 has diverse PII types including phone, email, iban."""
        case = next(c for c in v020_doc.cases if c.id == "GS-011")
        types = {a.type for a in case.pii_annotations}
        assert "person" in types
        assert "bg_nummer" in types
        assert "iban" in types
        assert "address" in types
        assert "birth_date" in types
        assert "phone" in types
        assert "email" in types

    def test_gs012_has_negative_controls(self, v020_doc: GoldsetDocument) -> None:
        """GS-012 has negative controls for over-redaction check."""
        case = next(c for c in v020_doc.cases if c.id == "GS-012")
        assert len(case.negative_controls) > 0
        assert "03.05.2024" in case.negative_controls  # Bescheiddatum
        assert "563,00 EUR" in case.negative_controls  # amount
        assert "42,00 EUR" in case.negative_controls  # amount
        assert "420,00 EUR" in case.negative_controls  # amount

    def test_all_span_texts_match_text(self, v020_doc: GoldsetDocument) -> None:
        """Every PII span text matches the actual text at those offsets."""
        for case in v020_doc.cases:
            text = case.input_document.text
            for ann in case.pii_annotations:
                for span in ann.spans:
                    assert span.start >= 0
                    assert span.end <= len(text)
                    actual = text[span.start : span.end]
                    assert actual == span.text, (
                        f"{case.id}: span [{span.start}:{span.end}] "
                        f"expected {span.text!r}, got {actual!r}"
                    )

    def test_no_overlapping_spans(self, v020_doc: GoldsetDocument) -> None:
        """No PARTIALLY overlapping PII spans (containment is allowed)."""
        for case in v020_doc.cases:
            all_spans: list[tuple[int, int, str]] = []
            for ann in case.pii_annotations:
                for span in ann.spans:
                    all_spans.append((span.start, span.end, ann.type))
            all_spans.sort()
            for i in range(len(all_spans) - 1):
                s1, e1, t1 = all_spans[i]
                s2, e2, t2 = all_spans[i + 1]
                if s2 < e1:
                    # Allow full containment
                    if s2 >= s1 and e2 <= e1:
                        continue
                    if s1 >= s2 and e1 <= e2:
                        continue
                    pytest.fail(
                        f"{case.id}: overlapping PII spans: "
                        f"({s1},{e1}) type={t1} overlaps with ({s2},{e2}) type={t2}"
                    )

    def test_negative_controls_exist_in_text(self, v020_doc: GoldsetDocument) -> None:
        """All negative controls are actually present in the input text."""
        for case in v020_doc.cases:
            text = case.input_document.text
            for nc in case.negative_controls:
                assert nc in text, (
                    f"{case.id}: negative control {nc!r} not found in input text"
                )


# ---------------------------------------------------------------------------
# resolve_goldset_path
# ---------------------------------------------------------------------------


class TestResolveGoldsetPath:
    def test_default_is_latest(self) -> None:
        path = resolve_goldset_path()
        assert path.endswith("goldset-v0.2.0.yaml")

    def test_v010_explicit(self) -> None:
        path = resolve_goldset_path("0.1.0")
        assert path.endswith("goldset-v0.1.0.yaml")

    def test_v020_explicit(self) -> None:
        path = resolve_goldset_path("0.2.0")
        assert path.endswith("goldset-v0.2.0.yaml")

    def test_unknown_version_raises(self) -> None:
        with pytest.raises(ValueError, match="Unsupported goldset version"):
            resolve_goldset_path("9.9.9")
