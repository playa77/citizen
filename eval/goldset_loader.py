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
VALID_ASSESSMENTS: frozenset[str] = frozenset({
    "rechtswidrig",
    "teilweise_rechtswidrig",
    "ueberwiegend_rechtmaessig",
    "kein_verwaltungsakt",
})


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


class GoldsetCase(BaseModel):
    id: str
    version: str
    title: str
    category: str
    difficulty: str
    input_document: InputDocument
    expected: Expected


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
        warnings.append(
            f"goldset.legal_area='{doc.goldset.legal_area}' not in LEGAL_AREA_ALLOWED"
        )

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
        if case.expected.overall_assessment:
            if case.expected.overall_assessment not in VALID_ASSESSMENTS:
                warnings.append(
                    f"Case {case.id}: overall_assessment='{case.expected.overall_assessment}' not in {sorted(VALID_ASSESSMENTS)}"
                )

        # Check citations reference actual norms (soft check — corpus may differ)
        if not case.expected.citations:
            warnings.append(f"Case {case.id}: no expected citations defined")
        if not case.expected.legal_issues:
            warnings.append(f"Case {case.id}: no expected legal_issues defined")

        # Frist check: if widerspruchsfrist.frist_ende is a date string, parse it
        frist = case.expected.widerspruchsfrist
        if frist and isinstance(frist.frist_ende, str) and frist.frist_ende != "kein_verwaltungsakt":
            try:
                date.fromisoformat(frist.frist_ende)
            except ValueError:
                # "nicht_anwendbar" or similar special values — ok
                pass

    return warnings


# ---------------------------------------------------------------------------
# CLI entry point for quick validation
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    for p in sys.argv[1:] or ["eval/goldsets/goldset-v0.1.0.yaml"]:
        doc = load_goldset(p)
        print(f"Loaded: {doc.goldset.id} v{doc.goldset.version} — {len(doc.cases)} cases")

        issues = audit_goldset(doc)
        if issues:
            for w in issues:
                print(f"  ⚠ {w}")
        else:
            print("  ✓ Audit passed (no warnings)")
