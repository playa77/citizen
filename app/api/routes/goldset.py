"""Goldset browser endpoints — Prüfstand (WP-14).

Provides:
    GET  /api/v1/goldset               — manifest + case list (parsed JSON, no YAML)
    GET  /api/v1/goldset/{case_id}     — full structured case
    POST /api/v1/goldset/{case_id}/analyze — triggers pipeline with case text (SSE)

The YAML file is the single source of truth. The GUI is a read-only render layer
over the immutable, versioned artifact. No YAML raw text ever appears in API
responses or the frontend DOM.

Goldset path and version are controlled by configuration (GOLDSET_PATH in
settings), so version changes require no code changes.
"""

# Semantic Version: 1.0.0 | 2026-07-12

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import AsyncGenerator
from datetime import date
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse

from app.core.config import _get_settings
from app.core.pipeline import PipelineState, run_pipeline
from app.utils.text import normalize_text

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Category label mapping — snake_case → plain German
# ---------------------------------------------------------------------------

# The goldset stores categories as snake_case identifiers. The UI must never
# show snake_case — this mapping provides human-readable German labels.
# New categories require adding an entry here (not in the YAML).
_CATEGORY_LABELS: dict[str, str] = {
    "bewilligung_einkommensanrechnung": "Bewilligung / Einkommensanrechnung",
    "endgueltige_festsetzung_41a": "Endgültige Festsetzung (§ 41a)",
    "aufhebung_erstattung_48_50": "Aufhebung & Erstattung (§§ 48, 50 SGB X)",
    "ruecknahme_45": "Rücknahme (§ 45 SGB X)",
    "minderung_meldeversaeumnis_32": "Sanktion / Meldeversäumnis",
    "minderung_pflichtverletzung_31a": "Sanktion / Pflichtverletzung",
    "kdu_kostensenkung": "KdU / Kostensenkung",
    "ablehnung_vermoegen": "Ablehnung / Vermögen",
    "versagung_66_sgb1": "Versagung (§ 66 SGB I)",
    "erstattung_fehlerhafte_rbb": "Erstattung / fehlerhafte Rechtsbehelfsbelehrung",
}

# Difficulty labels
_DIFFICULTY_LABELS: dict[str, str] = {
    "niedrig": "niedrig",
    "mittel": "mittel",
    "hoch": "hoch",
}

# Overall assessment → plain German + semantic color
# rot = Fehler zulasten gefunden, grün = Bescheid hält stand, grau = kein VA
_ASSESSMENT_INFO: dict[str, dict[str, str]] = {
    "rechtswidrig": {
        "label": "Fehler zulasten gefunden",
        "color": "red",
    },
    "teilweise_rechtswidrig": {
        "label": "Fehler zulasten gefunden",
        "color": "red",
    },
    "ueberwiegend_rechtmaessig": {
        "label": "Bescheid hält der Prüfung stand",
        "color": "green",
    },
    "kein_verwaltungsakt": {
        "label": "Kein Verwaltungsakt",
        "color": "gray",
    },
}


def _category_label(snake: str) -> str:
    """Convert a snake_case category to a plain German label."""
    return _CATEGORY_LABELS.get(snake, snake.replace("_", " ").title())


def _assessment_info(assessment: str | None) -> dict[str, str]:
    """Return label and color for an overall_assessment value."""
    if assessment and assessment in _ASSESSMENT_INFO:
        return _ASSESSMENT_INFO[assessment]
    return {"label": "Unbekannt", "color": "gray"}


# ---------------------------------------------------------------------------
# Date serialization helper
# ---------------------------------------------------------------------------


def _serialize_date(d: date | str | None) -> str | None:
    """Serialize a date or string to ISO format string. Passes through strings."""
    if d is None:
        return None
    if isinstance(d, date):
        return d.isoformat()
    return str(d)


def _serialize_frist(frist: Any) -> dict[str, Any]:
    """Serialize a Widerspruchsfrist model to a frontend-friendly dict.

    Handles the special 'kein_verwaltungsakt' value and extracts the
    rollover flag by comparing frist_ende_rechnerisch vs frist_ende.
    """
    if frist is None:
        return {"frist_ende": None, "status": "unknown"}

    # The Widerspruchsfrist model uses extra="allow", so we get all fields
    raw = frist.model_dump() if hasattr(frist, "model_dump") else dict(frist)

    frist_ende = raw.get("frist_ende")
    frist_ende_rechnerisch = raw.get("frist_ende_rechnerisch")

    # Handle the special "kein_verwaltungsakt" case
    if isinstance(frist_ende, str) and frist_ende == "kein_verwaltungsakt":
        return {
            "frist_ende": None,
            "frist_ende_rechnerisch": None,
            "status": "kein_verwaltungsakt",
            "bekanntgabe_fiktion": _serialize_date(raw.get("bekanntgabe_fiktion")),
            "aufgabe_zur_post": _serialize_date(raw.get("aufgabe_zur_post")),
            "bescheid_datum": _serialize_date(raw.get("bescheid_datum")),
            "begruendung": raw.get("begruendung", ""),
            "status_am_referenzdatum": raw.get("status_am_referenzdatum"),
            "rollover_applied": False,
        }

    # Detect rollover: frist_ende differs from frist_ende_rechnerisch
    rollover = False
    if frist_ende_rechnerisch is not None and frist_ende is not None:
        fe = _serialize_date(frist_ende)
        fer = _serialize_date(frist_ende_rechnerisch)
        if fe != fer:
            rollover = True

    return {
        "frist_ende": _serialize_date(frist_ende),
        "frist_ende_rechnerisch": _serialize_date(frist_ende_rechnerisch),
        "bekanntgabe_fiktion": _serialize_date(raw.get("bekanntgabe_fiktion")),
        "aufgabe_zur_post": _serialize_date(raw.get("aufgabe_zur_post")),
        "bescheid_datum": _serialize_date(raw.get("bescheid_datum")),
        "status_am_referenzdatum": raw.get("status_am_referenzdatum"),
        "rollover_applied": rollover,
        "rbb_fehlerhaft": raw.get("rbb_fehlerhaft", False),
        "massgebliche_frist": raw.get("massgebliche_frist"),
        "regulaere_frist_haette_geendet": _serialize_date(
            raw.get("regulaere_frist_haette_geendet")
        ),
    }


# ---------------------------------------------------------------------------
# Goldset loading (cached per-version)
# ---------------------------------------------------------------------------

# Cache the loaded goldset document to avoid re-parsing on every request.
# The cache key is the file path + modification time.
_goldset_cache: dict[str, tuple[float, Any]] = {}


def _load_goldset_cached() -> Any:
    """Load the goldset from the configured path, with file-mtime caching."""
    settings = _get_settings()
    path = Path(settings.GOLDSET_PATH)

    if not path.exists():
        raise FileNotFoundError(f"Goldset file not found: {path}")

    mtime = path.stat().st_mtime
    cache_key = str(path)

    if cache_key in _goldset_cache and _goldset_cache[cache_key][0] == mtime:
        return _goldset_cache[cache_key][1]

    # Import here to avoid importing eval modules at module level (circular deps)
    from eval.goldset_loader import load_goldset

    doc = load_goldset(path)
    _goldset_cache[cache_key] = (mtime, doc)
    logger.info(
        "Goldset loaded: %s v%s — %d cases (path=%s)",
        doc.goldset.id,
        doc.goldset.version,
        len(doc.cases),
        path,
    )
    return doc


# ---------------------------------------------------------------------------
# Serialization — goldset → frontend JSON
# ---------------------------------------------------------------------------


def _case_to_summary(case: Any) -> dict[str, Any]:
    """Convert a GoldsetCase to a gallery-card summary dict (no input text)."""
    assessment_info = _assessment_info(case.expected.overall_assessment)
    return {
        "id": case.id,
        "version": case.version,
        "title": case.title,
        "category": case.category,
        "category_label": _category_label(case.category),
        "difficulty": case.difficulty,
        "difficulty_label": _DIFFICULTY_LABELS.get(case.difficulty, case.difficulty),
        "overall_assessment": case.expected.overall_assessment,
        "assessment_label": assessment_info["label"],
        "assessment_color": assessment_info["color"],
        "issue_count": len(case.expected.legal_issues),
        "citation_count": len(case.expected.citations),
    }


def _case_to_detail(case: Any) -> dict[str, Any]:
    """Convert a GoldsetCase to a full detail dict (including input text)."""
    summary = _case_to_summary(case)

    # Serialize legal issues (findings)
    findings = []
    for issue in case.expected.legal_issues:
        findings.append(
            {
                "id": issue.id,
                "issue": issue.issue,
                "assessment": issue.assessment,
                "norm_chain": issue.norm_chain,
                "sub_issues": issue.sub_issues,
            }
        )

    # Serialize citations (§ chips)
    citations = []
    for cite in case.expected.citations:
        citations.append({"norm": cite.norm, "rolle": cite.rolle})

    # Serialize calculation diff
    calc = case.expected.calculation
    calc_rows = []
    if calc:
        jc = calc.get("jobcenter_ergebnis", {})
        ek = calc.get("expected_korrekt", {})

        # Build diff rows from the available keys — the goldset has varying
        # structures per case, so we extract what's comparable.
        # We look for matching line items between jobcenter_ergebnis and expected_korrekt.
        all_keys = sorted(set(list(jc.keys()) + list(ek.keys())))
        for key in all_keys:
            jc_val = jc.get(key)
            ek_val = ek.get(key)
            if isinstance(jc_val, int | float) and isinstance(ek_val, int | float):
                calc_rows.append(
                    {
                        "label": key.replace("_", " "),
                        "jobcenter": jc_val,
                        "correct": ek_val,
                        "delta": round(ek_val - jc_val, 2),
                    }
                )
            elif isinstance(ek_val, int | float) and jc_val is None:
                calc_rows.append(
                    {
                        "label": key.replace("_", " "),
                        "jobcenter": None,
                        "correct": ek_val,
                        "delta": None,
                    }
                )
            elif isinstance(jc_val, int | float) and ek_val is None:
                calc_rows.append(
                    {
                        "label": key.replace("_", " "),
                        "jobcenter": jc_val,
                        "correct": None,
                        "delta": None,
                    }
                )

    return {
        **summary,
        "input_document": {
            "type": case.input_document.type,
            "text": case.input_document.text,
        },
        "summary": case.expected.summary if hasattr(case.expected, "summary") else "",
        "findings": findings,
        "citations": citations,
        "calculation": calc,
        "calc_diff_rows": calc_rows,
        "widerspruchsfrist": _serialize_frist(case.expected.widerspruchsfrist),
        "known_traps": case.expected.known_traps,
        "actionable_next_steps": case.expected.actionable_next_steps,
    }


# ---------------------------------------------------------------------------
# SSE helper
# ---------------------------------------------------------------------------


def _sse_format(data: dict[str, Any]) -> str:
    """Serialize *data* as an SSE data line."""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/goldset")
async def get_goldset() -> dict[str, Any]:
    """Return the goldset manifest + case list as structured JSON.

    No YAML raw text is included in the response. Each case is summarized
    (no input document text) to keep the response lightweight for the
    gallery view.
    """
    try:
        doc = _load_goldset_cached()
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Goldset nicht gefunden: {exc}",
        ) from exc
    except Exception as exc:
        logger.exception("Failed to load goldset")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Goldset konnte nicht geladen werden: {exc}",
        ) from exc

    g = doc.goldset
    return {
        "goldset": {
            "id": g.id,
            "version": g.version,
            "schema_version": g.schema_version,
            "created": g.created.isoformat() if g.created else None,
            "rechtsstand": g.rechtsstand.isoformat() if g.rechtsstand else None,
            "evaluation_reference_date": (
                g.evaluation_reference_date.isoformat() if g.evaluation_reference_date else None
            ),
            "legal_area": g.legal_area,
            "jurisdiction": g.jurisdiction,
            "bundesland_feiertage": g.bundesland_feiertage,
            "language": g.language,
            "case_count": g.case_count,
            "provenance": g.provenance,
            "legal_baseline": g.legal_baseline.model_dump() if g.legal_baseline else {},
            "open_questions": (
                [q.model_dump() for q in g.open_questions] if g.open_questions else []
            ),
            "evaluation_guide": (g.evaluation_guide.model_dump() if g.evaluation_guide else None),
        },
        "cases": [_case_to_summary(c) for c in doc.cases],
    }


@router.get("/goldset/{case_id}")
async def get_goldset_case(case_id: str) -> dict[str, Any]:
    """Return a single goldset case as structured JSON (full detail).

    Includes the input document text, findings, citations, calculation,
    widerspruchsfrist, known traps, and next steps.
    """
    try:
        doc = _load_goldset_cached()
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Goldset nicht gefunden: {exc}",
        ) from exc
    except Exception as exc:
        logger.exception("Failed to load goldset")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Goldset konnte nicht geladen werden: {exc}",
        ) from exc

    for case in doc.cases:
        if case.id == case_id:
            return _case_to_detail(case)

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Fall '{case_id}' nicht im Goldset gefunden.",
    )


@router.post("/goldset/{case_id}/analyze")
async def analyze_goldset_case(case_id: str) -> StreamingResponse:
    """Trigger the full analysis pipeline on a goldset case's input text.

    Loads the goldset case, extracts its ``input_document.text``, and runs
    the standard pipeline (same as ``POST /api/v1/analyze``). Returns an
    SSE stream with stage progress and final output.

    The demo mode does NOT persist a CaseRun — it's a transient analysis
    for comparison purposes only.
    """
    try:
        doc = _load_goldset_cached()
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Goldset nicht gefunden: {exc}",
        ) from exc
    except Exception as exc:
        logger.exception("Failed to load goldset")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Goldset konnte nicht geladen werden: {exc}",
        ) from exc

    case = None
    for c in doc.cases:
        if c.id == case_id:
            case = c
            break

    if case is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Fall '{case_id}' nicht im Goldset gefunden.",
        )

    raw_text = case.input_document.text
    if not raw_text or not raw_text.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Fall '{case_id}' hat keinen Eingabetext.",
        )

    input_text = normalize_text(raw_text)
    session_id = str(uuid.uuid4())

    # Goldset cases are all sozialrecht — set legal_areas accordingly.
    state = PipelineState(
        input_text=input_text,
        legal_areas=["sozialrecht"],
    )

    logger.info(
        "Prüfstand demo analysis started: case=%s, session=%s",
        case_id,
        session_id,
    )

    async def event_generator() -> AsyncGenerator[str, None]:
        """Yield SSE events from the pipeline, then a final summary event."""
        try:
            async for sse_event in run_pipeline(state):
                yield sse_event

            # Final event — include the goldset case_id for the comparison view.
            final_payload = {
                "session_id": session_id,
                "goldset_case_id": case_id,
                "sections": list(state.final_output.keys()),
                "final_output": state.final_output,
            }
            yield _sse_format(final_payload)

        except Exception as exc:
            logger.exception("Prüfstand demo pipeline failed for case %s", case_id)
            error_payload = {
                "error": "pipeline_failed",
                "detail": str(exc),
                "session_id": session_id,
                "goldset_case_id": case_id,
            }
            yield _sse_format(error_payload)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
        },
    )
