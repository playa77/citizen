"""WP-97 golden SSE transcript — requests without ``legal_areas``.

The P9 exit gate (roadmap v3.0.0, WP-97) requires that a request that names
no legal areas still behaves **byte-identically** after the module refactor:
the core/module split must not change the transport contract for the default
path. This module pins that contract.

How the pin works
-----------------
``run_pipeline`` is replaced by a deterministic stub that emits the same
event shapes the real pipeline produces (one ``complete`` event per stage
plus the route's terminal summary event). The raw response bytes are then
compared against ``tests/integration/golden/analyze_transcript_no_areas.txt``
— event order, JSON key order, formatting (``ensure_ascii=False``, two-space
SSE framing) and every deterministic value are part of the comparison.

Deliberately volatile values are normalised to a placeholder and asserted
separately:

===========================  ==================  ==========================
field                        placeholder         asserted by
===========================  ==================  ==========================
``session_id`` (uuid4)       ``<uuid>``          UUID syntax + uniqueness
``case_run_id`` (uuid4)      ``<uuid>``          UUID syntax
``provenance.timestamp_utc`` ``<timestamp_utc>`` ISO 8601 UTC, per request
``provenance.app_version``   ``<app_version>``   equals ``get_app_version()``
module ``version``           ``<module_version>``manifest version
module ``parameter_set``     ``<parameter_set>`` ``<version>+<valid_from>``
===========================  ==================  ==========================

Re-baselining
-------------
The golden file is written with ``UPDATE_GOLDEN=1 pytest
tests/integration/test_analyze_transcript.py``. Re-baseline **only** for a
deliberate contract change (a new key on the terminal event, a changed stage
payload shape) and record it in ``DECISIONS.md`` — the transcript is the
WP-97 behaviour gate, so a silent re-baseline defeats it.

Run this file as part of an integration-only pytest invocation, like CI does.
A combined ``pytest tests/unit/ tests/integration/`` process reuses one async
engine across event loops; the resulting asyncpg "another operation is in
progress" error makes the route's audit write fail, which drops
``case_run_id`` from the terminal event and (correctly) fails the pin.
"""

# Semantic Version: 1.0.0 | 2026-11-16 — WP-97 P9 exit gate.

from __future__ import annotations

import json
import os
import re
import uuid
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_app_version, settings
from app.main import app
from app.modules.registry import default_modules_root, discover_modules

GOLDEN_PATH = Path(__file__).parent / "golden" / "analyze_transcript_no_areas.txt"

_HEADERS = {
    "X-Disclaimer-Ack": settings.DISCLAIMER_VERSION,
    "X-Document-Tag": "synthetic",
}

_INPUT_TEXT = (
    "Bescheid vom 02.09.2026 — Jobcenter Musterstadt, Aktenzeichen 123/456. "
    "Der Regelbedarf wurde um 87,00 EUR gekürzt."
)

# Deterministic pipeline output: one event per stage, in the order the real
# pipeline emits them, with payload keys mirroring ``_stage_payload`` in
# ``app/core/pipeline.py`` (duration_ms, counts, per-stage content).
_STUB_EVENTS: list[dict[str, Any]] = [
    {
        "stage": "normalization",
        "status": "complete",
        "payload": {"duration_ms": 0, "text_length": len(_INPUT_TEXT)},
    },
    {
        "stage": "classification",
        "status": "complete",
        "payload": {
            "duration_ms": 1200,
            "issues": ["Regelbedarf", "Kürzung ohne Ermessensprüfung"],
            "issue_count": 2,
        },
    },
    {
        "stage": "decomposition",
        "status": "complete",
        "payload": {
            "duration_ms": 900,
            "questions": ["Ist die Kürzung des Regelbedarfs rechtmäßig?"],
            "legal_regime": {"regimes": ["n.F._2026"], "as_of": "2026-09-01"},
            "question_count": 1,
        },
    },
    {
        "stage": "retrieval",
        "status": "complete",
        "payload": {"duration_ms": 40, "chunk_count": 2},
    },
    {
        "stage": "construction",
        "status": "complete",
        "payload": {
            "duration_ms": 12000,
            "claim_count": 1,
            "claims": [
                {
                    "claim_text": "Eine Kürzung setzt eine wirksame Rechtsgrundlage voraus.",
                    "confidence_score": 0.8,
                    "claim_type": "interpretation",
                }
            ],
        },
    },
    {
        "stage": "verification",
        "status": "complete",
        "payload": {
            "duration_ms": 5,
            "verified_claim_count": 1,
            "verified_claims": [
                {
                    "claim_text": "Eine Kürzung setzt eine wirksame Rechtsgrundlage voraus.",
                    "verification_status": "verified",
                    "confidence_score": 0.8,
                    "evidence_quote": "§ 31 SGB II regelt die Leistungsminderung.",
                    "evidence_hierarchy": "sgb2/31",
                    "evidence_chunk_id": None,
                }
            ],
        },
    },
    {
        "stage": "adversarial_review",
        "status": "complete",
        "payload": {
            "duration_ms": 8000,
            "review_count": 1,
            "key_risks": ["Tatsachenvortrag zum Kürzungsgrund fehlt"],
        },
    },
    {
        "stage": "calculation_check",
        "status": "complete",
        "payload": {
            "duration_ms": 3000,
            "calculations_found": 1,
            "discrepancies": 0,
            "total_amount_eur": 563.0,
        },
    },
    {
        "stage": "generation",
        "status": "complete",
        "payload": {
            "duration_ms": 2,
            "sections": [
                "sachverhalt",
                "rechtliche_wuerdigung",
                "ergebnis",
                "handlungsempfehlung",
                "entwurf",
                "unsicherheiten",
            ],
        },
    },
]

_STUB_FINAL_OUTPUT: dict[str, str] = {
    "sachverhalt": "Das Jobcenter kürzte den Regelbedarf um 87,00 EUR.",
    "rechtliche_wuerdigung": "Die Kürzung bedarf einer Rechtsgrundlage (§ 31 SGB II).",
    "ergebnis": "Der Bescheid ist in der Kürzung angreifbar.",
    "handlungsempfehlung": "Widerspruch innerhalb eines Monats prüfen.",
    "entwurf": "Sehr geehrte Damen und Herren, ich lege Widerspruch ein.",
    "unsicherheiten": "Der Kürzungsgrund ist im Bescheid nicht benannt.",
}


def _stub_pipeline(state: Any) -> Any:
    """Yield the fixed stage events, then populate ``state.final_output``."""

    async def _generator() -> Any:
        for event in _STUB_EVENTS:
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        state.final_output = dict(_STUB_FINAL_OUTPUT)
        state.calculation_result = None

    return _generator()


def _capture_transcript() -> str:
    """POST a request without ``legal_areas`` and return the raw SSE text."""
    with (
        patch("app.api.routes.analyze.run_pipeline", side_effect=_stub_pipeline),
        TestClient(app) as client,
        client.stream(
            "POST",
            "/api/v1/analyze",
            json={"text": _INPUT_TEXT},
            headers=_HEADERS,
        ) as response,
    ):
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        return b"".join(response.iter_bytes()).decode("utf-8")


_UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
_TIMESTAMP_RE = re.compile(r'"timestamp_utc": "[^"]*"')
_APP_VERSION_RE = re.compile(r'"app_version": "[^"]*"')
_MODULE_ENTRY_RE = re.compile(
    r'\{"id": "(?P<id>[^"]+)", "version": "[^"]+", "parameter_set": [^}]+\}'
)


def _normalise(text: str) -> str:
    """Replace the deliberately volatile values with their placeholders."""
    text = _UUID_RE.sub("<uuid>", text)
    text = _TIMESTAMP_RE.sub('"timestamp_utc": "<timestamp_utc>"', text)
    text = _APP_VERSION_RE.sub('"app_version": "<app_version>"', text)
    return _MODULE_ENTRY_RE.sub(
        '{"id": "<module_id>", "version": "<module_version>", '
        '"parameter_set": "<parameter_set>"}',
        text,
    )


def _terminal_event(transcript: str) -> dict[str, Any]:
    """Return the last SSE payload — the route's terminal summary event."""
    payloads = [
        json.loads(line[len("data: ") :])
        for line in transcript.splitlines()
        if line.startswith("data: ")
    ]
    assert payloads, "transcript contained no SSE data lines"
    return payloads[-1]


@pytest.fixture(scope="module")
def transcript() -> str:
    """The raw SSE transcript for one request without ``legal_areas``."""
    return _capture_transcript()


def test_transcript_is_byte_identical_to_golden(transcript: str) -> None:
    """The pinned contract for a request that names no legal areas."""
    normalised = _normalise(transcript)

    if os.environ.get("UPDATE_GOLDEN") == "1":
        GOLDEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN_PATH.write_text(normalised, encoding="utf-8")
        pytest.skip(f"UPDATE_GOLDEN=1 — golden rewritten at {GOLDEN_PATH}")

    assert GOLDEN_PATH.exists(), (
        f"golden transcript missing at {GOLDEN_PATH}; create it with "
        f"UPDATE_GOLDEN=1 pytest {__file__}"
    )
    expected = GOLDEN_PATH.read_text(encoding="utf-8")
    if normalised != expected:
        import difflib

        diff = "".join(
            difflib.unified_diff(
                expected.splitlines(keepends=True),
                normalised.splitlines(keepends=True),
                fromfile="golden",
                tofile="current",
            )
        )
        pytest.fail(
            "analyze SSE transcript changed for requests without legal_areas "
            "(WP-97 gate — re-baseline only for a documented contract change):\n" + diff
        )


def test_no_resolved_modules_without_legal_areas(transcript: str) -> None:
    """``resolved_modules`` stays absent unless the request named areas (D-057)."""
    terminal = _terminal_event(transcript)
    assert "resolved_modules" not in terminal


def test_terminal_event_provenance_names_default_module(transcript: str) -> None:
    """Provenance v1.1 names the module the default request ran with."""
    terminal = _terminal_event(transcript)

    assert terminal["disclosure"]["version"] == "1.0"
    assert terminal["disclosure"]["must_display_before"] == "results"
    assert set(terminal["disclosure"]["texts"]) == {"de", "en"}

    provenance = terminal["provenance"]
    assert provenance["spec_version"] == "citizen-provenance-v1.1"
    assert provenance["generator"] == "citizen"
    assert provenance["app_version"] == get_app_version()
    assert provenance["timestamp_utc"].endswith("Z")

    default_module = settings.DEFAULT_MODULE
    manifest = discover_modules(default_modules_root())[default_module]
    modules = provenance["modules"]
    assert [entry["id"] for entry in modules] == [default_module]
    assert modules[0]["version"] == str(manifest.version)
    # "<module version>+<latest valid_from>" (ARCHITECTURE.md § 6.3).
    assert modules[0]["parameter_set"].startswith(f"{manifest.version}+")


def test_session_and_case_run_ids_are_uuids(transcript: str) -> None:
    """Both identifiers stay UUIDs on the terminal event."""
    terminal = _terminal_event(transcript)
    uuid.UUID(terminal["session_id"])
    uuid.UUID(terminal["case_run_id"])
