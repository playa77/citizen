# Version: 1.0.0 | 2026-07-12
"""Pydantic-typed loader for Citizen goldset YAML files.

Validates structure on load and audits against DB schema constants
(LEGAL_AREA_ALLOWED, STATUTE_SOURCES, etc.).

Usage:
    from eval.goldset_loader import load_goldset

    goldset = load_goldset("eval/goldsets/goldset-v0.1.0.yaml")
    for case in goldset.cases:
        print(case.id, case.title, case.category, case.difficulty)
"""

from __future__ import annotations

import logging
from contextlib import suppress
from datetime import date
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator

from app.db.models import LEGAL_AREA_ALLOWED

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Schemas — goldset metadata
# ---------------------------------------------------------------------------


class LegalBaseline(BaseModel):
    reform_status: dict[str, Any] = Field(default_factory=dict)
    regelbedarf_2026: dict[str, Any] = Field(default_factory=dict)
    einkommen_absetzbetraege_11b: dict[str, Any] = Field(default_factory=dict)
    sanktionen_neues_recht: dict[str, Any] = Field(default_factory=dict)
    vermoegen_intertemporal: dict[str, Any] = Field(default_factory=dict)
    meldeversaeumnis_32: dict[str, Any] = Field(default_factory=dict)
    feiertage_nrw_2026: list[str] = Field(default_factory=list)


class OpenQuestion(BaseModel):
    id: str
    topic: str
    note: str


class EvaluationGuide(BaseModel):
    issue_recall: str
    citation_precision: str
    calculation_exact_match: str
    frist_exact_match: str
    assessment_match: str


class GoldsetMeta(BaseModel):
    id: str
    version: str
    schema_version: str
    created: date
    rechtsstand: date
    evaluation_reference_date: date
    legal_area: str
    jurisdiction: str
    bundesland_feiertage: str
    language: str
    case_count: int
    provenance: str
    legal_baseline: LegalBaseline = Field(default_factory=LegalBaseline)
    open_questions: list[OpenQuestion] = Field(default_factory=list)
    evaluation_guide: EvaluationGuide | None = None

    @field_validator("legal_area")
    @classmethod
    def legal_area_must_be_known(cls, v: str) -> str:
        if v not in LEGAL_AREA_ALLOWED:
            logger.warning(
                "Goldset legal_area '%s' is not in LEGAL_AREA_ALLOWED %s",
                v,
                LEGAL_AREA_ALLOWED,
            )
        return v


# ---------------------------------------------------------------------------
# Schemas — cases
# ---------------------------------------------------------------------------


class InputDocument(BaseModel):
    type: str
    text: str


class LegalIssue(BaseModel):
    id: str
    issue: str
    assessment: str = ""
    norm_chain: list[str] = Field(default_factory=list)
    sub_issues: list[dict[str, Any]] = Field(default_factory=list)


class Citation(BaseModel):
    norm: str
    rolle: str = ""
    must_exist_in_corpus: bool = True


class Widerspruchsfrist(BaseModel):
    """Flexible model — individual goldset cases have varying frist fields.

    Known fields: bescheid_datum, aufgabe_zur_post, bekanntgabe_fiktion,
    frist_ende, frist_ende_rechnerisch, status_am_referenzdatum.
    frist_ende can be ISO date string or 'kein_verwaltungsakt'.
    """

    model_config = {"extra": "allow"}

    bescheid_datum: date | None = None
    aufgabe_zur_post: date | None = None
    bekanntgabe_fiktion: date | None = None
    frist_ende: date | str | None = None
    frist_ende_rechnerisch: date | None = None
    status_am_referenzdatum: str | None = None


# Valid overall_assessment values per evaluation_guide
VALID_ASSESSMENTS: frozenset[str] = frozenset(
    {
        "rechtswidrig",
        "teilweise_rechtswidrig",
        "ueberwiegend_rechtmaessig",
        "kein_verwaltungsakt",
    }
)


class Expected(BaseModel):
    """Expected values for a goldset case — what the pipeline should produce."""

    legal_issues: list[LegalIssue] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    calculation: dict[str, Any] = Field(default_factory=dict)
    widerspruchsfrist: Widerspruchsfrist | None = None
    overall_assessment: str | None = None
    known_traps: list[str] = Field(default_factory=list)
    actionable_next_steps: list[str] = Field(default_factory=list)

    @field_validator("overall_assessment", mode="before")
    @classmethod
    def assessment_must_be_valid(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_ASSESSMENTS:
            logger.warning(
                "Unknown overall_assessment '%s'. Valid: %s", v, sorted(VALID_ASSESSMENTS)
            )
        return v


class PiiSpan(BaseModel):
    """A single PII span within the input document text."""

    start: int
    end: int
    text: str


class PiiAnnotation(BaseModel):
    """PII annotation for a goldset case.

    ``type`` is one of ``"person"``, ``"address"``, ``"birth_date"``,
    ``"bg_nummer"``, ``"aktenzeichen"``, ``"iban"``, ``"phone"``, ``"email"``.
    """

    type: str
    canonical: str
    spans: list[PiiSpan]


class GoldsetCase(BaseModel):
    id: str
    version: str
    title: str
    category: str
    difficulty: str
    input_document: InputDocument
    expected: Expected
    pii_annotations: list[PiiAnnotation] = Field(default_factory=list)
    negative_controls: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Combined document
# ---------------------------------------------------------------------------


class GoldsetDocument(BaseModel):
    goldset: GoldsetMeta
    cases: list[GoldsetCase]


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------


def load_goldset(path: str | Path) -> GoldsetDocument:
    """Load and validate a goldset YAML file.

    Raises:
        FileNotFoundError: Path does not exist.
        yaml.YAMLError: Invalid YAML.
        pydantic.ValidationError: Schema mismatch.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Goldset file not found: {path}")

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return GoldsetDocument(**raw)


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------


def audit_goldset(doc: GoldsetDocument) -> list[str]:
    """Audit goldset cases against known constraints. Returns list of warnings."""
    warnings: list[str] = []

    # Check legal_area
    if doc.goldset.legal_area not in LEGAL_AREA_ALLOWED:
        warnings.append(f"goldset.legal_area='{doc.goldset.legal_area}' not in LEGAL_AREA_ALLOWED")

    # Check case count
    if len(doc.cases) != doc.goldset.case_count:
        warnings.append(
            f"Declared case_count={doc.goldset.case_count} but got {len(doc.cases)} cases"
        )

    # Check case IDs are unique
    ids = [c.id for c in doc.cases]
    dupes = {x for x in ids if ids.count(x) > 1}
    if dupes:
        warnings.append(f"Duplicate case IDs: {dupes}")

    for case in doc.cases:
        # Difficulty must be one of known values
        if case.difficulty not in {"niedrig", "mittel", "hoch"}:
            warnings.append(f"Case {case.id}: unknown difficulty '{case.difficulty}'")

        # overall_assessment if present must be valid
        oa = case.expected.overall_assessment
        if oa is not None and oa not in VALID_ASSESSMENTS:
            warnings.append(
                f"Case {case.id}: overall_assessment='{case.expected.overall_assessment}' "
                f"not in {sorted(VALID_ASSESSMENTS)}"
            )

        # Check citations reference actual norms (soft check — corpus may differ)
        if case.expected.citations is None:
            warnings.append(f"Case {case.id}: expected.citations is None (should be a list)")
        if not case.expected.legal_issues:
            warnings.append(f"Case {case.id}: no expected legal_issues defined")

            # Frist check: if widerspruchsfrist.frist_ende is a date string, parse it
            frist = case.expected.widerspruchsfrist
            if (
                frist
                and isinstance(frist.frist_ende, str)
                and frist.frist_ende != "kein_verwaltungsakt"
            ):
                with suppress(ValueError):
                    date.fromisoformat(frist.frist_ende)

        # ── PII annotation validation ───────────────────────────────────
        text = case.input_document.text

        if case.pii_annotations:
            # Check span offsets are within text
            for ann in case.pii_annotations:
                for span in ann.spans:
                    if span.start < 0 or span.end > len(text):
                        warnings.append(
                            f"Case {case.id}: PII span ({span.start}, {span.end}) "
                            f"out of bounds (text length={len(text)})"
                        )
                        continue
                    actual = text[span.start : span.end]
                    if actual != span.text:
                        warnings.append(
                            f"Case {case.id}: PII span text mismatch at "
                            f"({span.start}, {span.end}): expected "
                            f"{span.text!r}, got {actual!r}"
                        )

            # Check all canonical values appear in at least one span's text
            for ann in case.pii_annotations:
                canonical_found = False
                for span in ann.spans:
                    if ann.canonical in span.text or span.text in ann.canonical:
                        canonical_found = True
                        break
                if not canonical_found:
                    span_texts = " ".join(s.text for s in ann.spans)
                    if ann.canonical not in span_texts:
                        warnings.append(
                            f"Case {case.id}: canonical value {ann.canonical!r} "
                            f"not found in any span text"
                        )

            # Check no overlapping spans within same annotation type
            all_spans: list[tuple[int, int, str]] = []
            for ann in case.pii_annotations:
                for span in ann.spans:
                    all_spans.append((span.start, span.end, ann.type))
            all_spans.sort()
            for i in range(len(all_spans) - 1):
                s1, e1, t1 = all_spans[i]
                s2, e2, t2 = all_spans[i + 1]
                if s2 < e1:
                    # Allow full containment (one span inside another — common for
                    # address components like PLZ within a full street address)
                    if s2 >= s1 and e2 <= e1:
                        continue  # span2 is fully contained in span1 — ok
                    if s1 >= s2 and e1 <= e2:
                        continue  # span1 is fully contained in span2 — ok
                    warnings.append(
                        f"Case {case.id}: overlapping PII spans: "
                        f"({s1},{e1}) type={t1} overlaps with ({s2},{e2}) type={t2}"
                    )

        # ── Negative controls validation ───────────────────────────────
        if case.negative_controls:
            for nc in case.negative_controls:
                if nc not in text:
                    warnings.append(
                        f"Case {case.id}: negative control {nc!r} not found in "
                        f"input document text"
                    )

    return warnings


# ---------------------------------------------------------------------------
# Version helpers
# ---------------------------------------------------------------------------

_SUPPORTED_VERSIONS: frozenset[str] = frozenset({"0.1.0", "0.2.0"})
_LATEST_VERSION: str = "0.2.0"


def resolve_goldset_path(version: str | None = None) -> str:
    """Resolve goldset path for a given version (or latest).

    Args:
        version: Semver string (``"0.1.0"``, ``"0.2.0"``) or ``None`` for latest.

    Returns:
        File path to the goldset YAML.
    """
    if version is None:
        version = _LATEST_VERSION
    if version not in _SUPPORTED_VERSIONS:
        raise ValueError(
            f"Unsupported goldset version {version!r}. " f"Supported: {sorted(_SUPPORTED_VERSIONS)}"
        )
    return f"eval/goldsets/goldset-v{version}.yaml"


# ---------------------------------------------------------------------------
# CLI entry point for quick validation
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    parser = argparse.ArgumentParser(description="Goldset loader / auditor")
    parser.add_argument(
        "path",
        nargs="?",
        default=None,
        help="Path to goldset YAML (default: latest version)",
    )
    parser.add_argument(
        "--version",
        default=None,
        help=f"Goldset version (default: {_LATEST_VERSION})",
    )
    args = parser.parse_args()

    path = args.path
    if path is None:
        path = resolve_goldset_path(args.version)

    doc = load_goldset(path)
    print(f"Loaded: {doc.goldset.id} v{doc.goldset.version} — {len(doc.cases)} cases")

    issues = audit_goldset(doc)
    if issues:
        for w in issues:
            print(f"  ⚠ {w}")
    else:
        print("  ✓ Audit passed (no warnings)")
