"""Unit tests for the WP-61 purpose-drift lint (scripts/check_purpose_drift.py)."""

# Version: 1.0.0 | 2026-08-07

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_purpose_drift.py"

CLEAN_README = """# Citizen

Antragstellerseitige Selbsthilfe: Widersprüche gegen Jobcenter-Bescheide werden
geprüft, jede Aussage an den Gesetzestext gebunden.
"""

DRIFT_LINE = "Citizen hilft für Jobcenter bei der Prüfung von Bescheiden."


def _run(repo_root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--repo-root", str(repo_root), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_clean_document_passes(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(CLEAN_README, encoding="utf-8")
    (tmp_path / "STATEMENT.md").write_text("Statement.\n", encoding="utf-8")
    (tmp_path / "COMPLIANCE.md").write_text("Compliance.\n", encoding="utf-8")
    result = _run(tmp_path)
    assert result.returncode == 0
    assert "OK" in result.stdout


def test_drift_is_reported_with_file_line_and_phrase(tmp_path: Path) -> None:
    readme = tmp_path / "README.md"
    readme.write_text("Zeile 1\nZeile 2: " + DRIFT_LINE + "\n", encoding="utf-8")
    result = _run(tmp_path)
    assert result.returncode == 1
    assert "README.md:2" in result.stdout
    assert "für Jobcenter" in result.stdout
    assert "ZWECKDRIFT" in result.stderr


def test_missing_explicit_file_is_operational_error(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("ok\n", encoding="utf-8")
    result = _run(tmp_path, "--files", "README.md,NOPE.md")
    assert result.returncode == 2
    assert "NOPE.md" in result.stderr


def test_english_deny_phrase_is_detected(tmp_path: Path) -> None:
    (tmp_path / "README-EN.md").write_text(
        "Citizen is a tool for job centers to evaluate eligibility.\n",
        encoding="utf-8",
    )
    result = _run(tmp_path)
    assert result.returncode == 1
    assert "README-EN.md:1" in result.stdout
    assert "for job centers" in result.stdout


def test_extra_deny_phrase_is_applied_in_addition(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("Tool für Amtsgerichte.\n", encoding="utf-8")
    # Without the extra phrase the document is clean...
    assert _run(tmp_path).returncode == 0
    # ... with it, drift is detected.
    result = _run(tmp_path, "--extra-deny", "für Amtsgerichte")
    assert result.returncode == 1
    assert "für Amtsgerichte" in result.stdout


def test_matching_is_case_insensitive(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("Werkzeug FÜR Jobcenter.\n", encoding="utf-8")
    result = _run(tmp_path)
    assert result.returncode == 1
    assert "README.md:1" in result.stdout


def test_invalid_deny_phrase_file_is_operational_error(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("ok\n", encoding="utf-8")
    bad = tmp_path / "deny.json"
    bad.write_text("{ not json", encoding="utf-8")
    result = _run(tmp_path, "--deny-phrase-file", str(bad))
    assert result.returncode == 2
    assert "deny.json" in result.stderr
