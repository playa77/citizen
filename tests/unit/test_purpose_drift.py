"""Unit tests for the purpose-drift lint (scripts/check_purpose_drift.py).

WP-61 base behaviour plus the WP-96 extensions (D-059): extended scan set,
dead globs dropped (C-3), per-module deny phrases from manifests, same-line
allow marker, and a guard that the repository itself lints clean.
"""

# Version: 2.0.0 | 2026-11-16 — WP-96 extensions.
# 1.0.0 | 2026-08-07 — WP-61 initial.

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "check_purpose_drift.py"

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


# ---------------------------------------------------------------------------
# WP-96 — extended scan set, module deny phrases, allow marker
# ---------------------------------------------------------------------------


def _write(root: Path, relative: str, text: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _module(root: Path, module_id: str, compliance: str = "") -> Path:
    """Minimal module directory; *compliance* is a YAML block (or empty)."""
    return _write(
        root,
        f"modules/{module_id}/module.yaml",
        f"id: {module_id}\nversion: 0.1.0\n{compliance}",
    )


def test_core_documents_are_scanned(tmp_path: Path) -> None:
    _write(tmp_path, "README.md", "ok\n")
    for relative in ("DISCLAIMER_DE.md", "ARCHITECTURE.md", "docs/plan.md"):
        _write(tmp_path, relative, "ok\n" + DRIFT_LINE + "\n")
    result = _run(tmp_path)
    assert result.returncode == 1
    for relative in ("DISCLAIMER_DE.md:2", "ARCHITECTURE.md:2", "docs/plan.md:2"):
        assert relative in result.stdout


def test_module_copy_and_addendum_are_scanned(tmp_path: Path) -> None:
    _write(tmp_path, "README.md", "ok\n")
    _write(tmp_path, "modules/m1/copy/de/intro.yaml", "text: " + DRIFT_LINE + "\n")
    _write(tmp_path, "modules/m1/DISCLAIMER_ADDENDUM.md", DRIFT_LINE + "\n")
    result = _run(tmp_path)
    assert result.returncode == 1
    assert "modules/m1/copy/de/intro.yaml:1" in result.stdout
    assert "modules/m1/DISCLAIMER_ADDENDUM.md:1" in result.stdout


def test_dead_globs_dropped_and_module_patterns_optional(tmp_path: Path) -> None:
    """C-3: STATEMENT.md / COMPLIANCE*.md / docs/pitch* are no longer
    targets; module patterns without matches produce no warning, missing
    core documents do."""
    _write(tmp_path, "README.md", "ok\n")
    _write(tmp_path, "STATEMENT.md", DRIFT_LINE + "\n")
    result = _run(tmp_path)
    assert result.returncode == 0, result.stdout
    assert "modules/" not in result.stderr
    assert "STATEMENT.md" not in result.stderr
    assert "Muster ohne Treffer (übersprungen): DISCLAIMER_*.md" in result.stderr


def test_module_deny_phrases_from_manifest_apply_everywhere(tmp_path: Path) -> None:
    _write(tmp_path, "README.md", "Ein Werkzeug für die Polizei.\n")
    # Without a module declaring the phrase, the README is clean ...
    assert _run(tmp_path).returncode == 0
    # ... a module's deny file makes it drift in core documents too.
    _module(
        tmp_path, "strafrecht", "compliance:\n  purpose_drift_deny_file: compliance/deny.json\n"
    )
    _write(tmp_path, "modules/strafrecht/compliance/deny.json", '["für die Polizei"]')
    result = _run(tmp_path)
    assert result.returncode == 1
    assert "README.md:1" in result.stdout
    assert "für die Polizei" in result.stdout
    listed = _run(tmp_path, "--list-phrases")
    assert "für die Polizei" in listed.stdout.splitlines()


def test_module_deny_phrases_apply_to_explicit_files(tmp_path: Path) -> None:
    _write(tmp_path, "notes.md", "Ein Werkzeug für die Polizei.\n")
    _module(tmp_path, "strafrecht", "compliance:\n  purpose_drift_deny_file: deny.json\n")
    _write(tmp_path, "modules/strafrecht/deny.json", '["für die Polizei"]')
    assert _run(tmp_path, "--files", "notes.md").returncode == 1


def test_missing_module_deny_file_is_operational_error(tmp_path: Path) -> None:
    _write(tmp_path, "README.md", "ok\n")
    _module(tmp_path, "m1", "compliance:\n  purpose_drift_deny_file: nope.json\n")
    result = _run(tmp_path)
    assert result.returncode == 2
    assert "m1" in result.stderr


def test_module_deny_file_outside_module_is_operational_error(tmp_path: Path) -> None:
    _write(tmp_path, "README.md", "ok\n")
    _write(tmp_path, "deny.json", '["x"]')
    _module(tmp_path, "m1", "compliance:\n  purpose_drift_deny_file: ../../deny.json\n")
    result = _run(tmp_path)
    assert result.returncode == 2
    assert "außerhalb" in result.stderr


def test_invalid_module_deny_file_is_operational_error(tmp_path: Path) -> None:
    _write(tmp_path, "README.md", "ok\n")
    _module(tmp_path, "m1", "compliance:\n  purpose_drift_deny_file: deny.json\n")
    _write(tmp_path, "modules/m1/deny.json", '{"not": "a list"}')
    assert _run(tmp_path).returncode == 2


def test_allow_marker_exempts_only_its_line_and_is_counted(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "README.md",
        'Deny-Liste, z. B. "für Jobcenter" <!-- purpose-drift: allow -->\nsauber\n',
    )
    result = _run(tmp_path)
    assert result.returncode == 0, result.stdout
    assert "ausgenommene Zeilen: 1" in result.stdout
    # The marker does not leak to other lines.
    _write(
        tmp_path,
        "README.md",
        "zitiert <!-- purpose-drift: allow -->\n" + DRIFT_LINE + "\n",
    )
    result = _run(tmp_path)
    assert result.returncode == 1
    assert "README.md:2" in result.stdout


def test_repository_lints_clean_with_module_phrases() -> None:
    """The real scan set passes, and the shipped modules' deny files load."""
    result = _run(REPO_ROOT)
    assert result.returncode == 0, result.stdout + result.stderr
    for module_id in ("familienrecht", "sozialrecht", "strafrecht"):
        assert module_id in result.stdout
    assert "WARNUNG" not in result.stderr
