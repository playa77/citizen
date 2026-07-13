"""Eval report endpoints — Prüfstand (WP-14, Deliverable B).

Provides:
    GET /api/v1/eval/reports          — list versioned eval runs (empty allowed)
    GET /api/v1/eval/reports/{report_id} — full report JSON

Eval reports are versioned JSON files produced by the eval harness
(``eval/runner.py``) and stored in ``eval/results/``. The API reads them
on demand — no database involved.

When no reports exist, the list endpoint returns an empty array. The
frontend renders a clean empty state ("Noch keine Prüfläufe") — never
fake numbers.
"""

# Semantic Version: 1.0.0 | 2026-07-12

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, status

from app.core.config import _get_settings

logger = logging.getLogger(__name__)

router = APIRouter()


def _eval_results_dir() -> Path:
    """Return the configured eval results directory."""
    return Path(_get_settings().EVAL_RESULTS_DIR)


def _is_valid_report(data: Any) -> bool:
    """Check if a parsed JSON object looks like an EvalReport."""
    if not isinstance(data, dict):
        return False
    required = {"goldset_version", "run_timestamp", "cases"}
    return required.issubset(data.keys())


@router.get("/eval/reports")
async def list_eval_reports() -> dict[str, Any]:
    """List all eval report files in the results directory.

    Returns a list of report summaries (no per-case detail). Each summary
    includes the report_id (filename stem), goldset_version, run_timestamp,
    git_sha, case count, and aggregate metrics.

    Returns an empty list if the directory doesn't exist or has no reports.
    """
    results_dir = _eval_results_dir()

    if not results_dir.exists():
        logger.info("Eval results directory does not exist: %s", results_dir)
        return {"reports": []}

    reports: list[dict[str, Any]] = []

    for json_path in sorted(results_dir.glob("*.json"), reverse=True):
        try:
            raw = json_path.read_text(encoding="utf-8")
            data = json.loads(raw)

            if not _is_valid_report(data):
                logger.warning("Skipping invalid eval report: %s", json_path.name)
                continue

            reports.append(
                {
                    "report_id": json_path.stem,
                    "goldset_version": data.get("goldset_version"),
                    "goldset_path": data.get("goldset_path"),
                    "git_sha": data.get("git_sha"),
                    "run_timestamp": data.get("run_timestamp"),
                    "case_count": len(data.get("cases", [])),
                    "aggregate": data.get("aggregate", {}),
                }
            )
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to read eval report %s: %s", json_path.name, exc)
            continue

    logger.info("Listed %d eval reports from %s", len(reports), results_dir)
    return {"reports": reports}


@router.get("/eval/reports/{report_id}")
async def get_eval_report(report_id: str) -> dict[str, Any]:
    """Return a full eval report by ID (filename stem).

    The report includes per-case metrics: issue_recall,
    citation_precision, calculation_exact_match, frist_exact_match,
    assessment_match, quote_verification_rate, latency_ms, and errors.
    """
    # Sanitize report_id — only allow alphanumeric, dash, underscore
    # to prevent path traversal.
    safe_chars = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_")
    if not all(c in safe_chars for c in report_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ungültige Report-ID.",
        )

    results_dir = _eval_results_dir()
    report_path = results_dir / f"{report_id}.json"

    if not report_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Prüfbericht '{report_id}' nicht gefunden.",
        )

    try:
        raw = report_path.read_text(encoding="utf-8")
        data: dict[str, Any] = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.error("Invalid JSON in eval report %s: %s", report_path, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Prüfbericht '{report_id}' ist beschädigt.",
        ) from exc

    if not _is_valid_report(data):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Prüfbericht '{report_id}' hat ungültiges Format.",
        )

    return data
