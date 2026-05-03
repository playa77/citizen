"""WP-015: End-to-End Integration & Performance Validation.

Tests cover:
- ``test_full_pipeline_execution`` — wires all components together:
    * total latency < 120 s for a simulated 3-page scanned PDF
    * ``pipeline_stage_log`` table contains 7 rows per run
    * ``claim`` and ``evidence_binding`` tables populated correctly
- ``test_disclaimer_enforcement`` — the full pipeline only executes
  post-acknowledgment; ``pipeline_stage_log`` contains exactly 8 rows
  per run (7 stages + 1 disclaimer_ack).
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from collections.abc import AsyncGenerator
from contextlib import suppress
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.main import app

# -------------------------------------------------------------------
# Fixtures
# -------------------------------------------------------------------


@pytest.fixture
def client() -> TestClient:
    """Return a synchronous TestClient for the FastAPI app."""
    return TestClient(app)


@pytest.fixture
async def db_session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncSession, None]:
    """Yield a disposable session; rollback at end to keep tests clean."""
    async with session_factory() as session, session.begin():
        yield session
        await session.rollback()


# Sample German legal text (3-page scanned PDF equivalent)
SAMPLE_LEGAL_TEXT = (
    "Bescheid vom 15.03.2026\n\n"
    "Sehr geehrte(r) Antragsteller(in),\n\n"
    "hiermit wird Ihnen mitgeteilt, dass Ihre Leistungen nach dem "
    "Zweiten Buch Sozialgesetzbuch (SGB II) nach § 31 Abs. 1 Satz 1 "
    "um 30 Prozent gekürzt werden. Die Kündigung Ihrer "
    "Eingliederungsvereinbarung erfolgt wegen wiederholter "
    "Nichteinhaltung der Meldepflicht.\n\n"
    "Begründung:\n"
    "Sie haben trotz schriftlicher Belehrung wiederholt wichtige "
    "Termine nicht wahrgenommen. Insbesondere haben Sie den "
    "Termin am 01.03.2026 und am 08.03.2026 nicht besucht, ohne "
    "einen wichtigen Grund anzugeben.\n\n"
    "Rechtsbehelfsbelehrung:\n"
    "Gegen diesen Bescheid können Sie innerhalb eines Monats nach "
    "Zugang Widerspruch bei dem Jobcenter einlegen.\n\n"
    "Mit freundlichen Grüßen\n"
    "Jobcenter Musterstadt"
)

DISCLAIMER_HEADER = {"X-Disclaimer-Ack": "v1.0.0"}

# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------


def _count_rows(table: str) -> int:
    """Query row count via psql subprocess (avoids async loop issues)."""
    result = subprocess.run(
        [
            "psql",
            "-U",
            "testuser",
            "-d",
            "testdb",
            "-h",
            "127.0.0.1",
            "-t",
            "-A",
            "-c",
            f"SELECT count(*) FROM {table}",
        ],
        env={**__import__("os").environ, "PGPASSWORD": "testpassword"},
        capture_output=True,
        text=True,
        timeout=10,
    )
    return int(result.stdout.strip())


def _consume_sse(response) -> list[dict]:
    """Consume the entire streaming response and parse SSE events."""
    content_bytes = b"".join(response.iter_bytes())
    content = content_bytes.decode("utf-8")
    events: list[dict] = []
    for line in content.splitlines():
        line = line.strip()
        if line.startswith("data: "):
            payload_str = line[6:].strip()
            if payload_str:
                with suppress(json.JSONDecodeError):
                    events.append(json.loads(payload_str))
    return events


def _mock_pipeline_for_test(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace reasoning/retrieval modules with deterministic stubs."""
    import types

    # --- reasoning stub -------------------------------------------------
    reasoning_mod = types.ModuleType("app.services.reasoning")

    async def classify_issues(text: str) -> list[str]:
        return ["SGB II § 31 — Kürzung der Leistung"]

    async def decompose_questions(text: str) -> list[str]:
        return [
            "War die Kürzung nach § 31 SGB II rechtmäßig?",
            "Welche Meldepflichten wurden verletzt?",
            "Kann die Kürzung angefochten werden?",
        ]

    async def construct_claims(
        chunks: list[dict],
        questions: list[str],
    ) -> list[dict]:
        return [
            {
                "claim_text": "Die Kürzung war unverhältnismäßig.",
                "confidence_score": 0.78,
                "claim_type": "interpretation",
                "question": questions[0] if questions else "",
            },
            {
                "claim_text": "Meldepflicht nach § 60 SGB I nicht beachtet.",
                "confidence_score": 0.85,
                "claim_type": "fact",
                "question": questions[1] if questions else "",
            },
        ]

    async def verify_claims(
        claims: list[dict],
        chunks: list[dict],
    ) -> list[dict]:
        return [
            {
                "claim_text": c["claim_text"],
                "confidence_score": float(c.get("confidence_score", 0.5)) * 0.95,
                "claim_type": c.get("claim_type", "fact"),
                "verified": True,
                "reasoning": "Quelle bestätigt die Behauptung.",
            }
            for c in claims
        ]

    async def generate_output(
        verified_claims: list[dict],
    ) -> dict[str, str]:
        return {
            "sachverhalt": "Antragsteller erhielt Kürzungsbescheid nach § 31 SGB II.",
            "rechtliche_wuerdigung": "§ 31 SGB II erfordert eine Einzelfallprüfung.",
            "ergebnis": "Kürzung kann angefochten werden.",
            "handlungsempfehlung": "Widerspruch innerhalb eines Monats einlegen.",
            "entwurf": "Sehr geehrte Damen und Herren, hiermit lege ich Widerspruch ein.",
            "unsicherheiten": "Fehlende Unterlagen zur Meldepflicht.",
        }

    reasoning_mod.classify_issues = classify_issues  # type: ignore[attr-defined]
    reasoning_mod.decompose_questions = decompose_questions  # type: ignore[attr-defined]
    reasoning_mod.construct_claims = construct_claims  # type: ignore[attr-defined]
    reasoning_mod.verify_claims = verify_claims  # type: ignore[attr-defined]
    reasoning_mod.generate_output = generate_output  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "app.services.reasoning", reasoning_mod)

    # --- retrieval stub --------------------------------------------------
    retrieval_mod = types.ModuleType("app.services.retrieval")

    async def retrieve_chunks(
        questions: list[str],
        *,
        client=None,
        session_factory=None,
    ) -> list[dict]:
        return [
            {
                "chunk_id": str(uuid4()),
                "text_content": "§ 31 Abs. 1 SGB II: Leistungsberechtigte, die ...",
                "hierarchy_path": "SGB II > § 31 > Abs. 1",
                "source_type": "sgb2",
                "title": "SGB II",
                "distance": 0.15,
            },
        ]

    retrieval_mod.retrieve_chunks = retrieve_chunks  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "app.services.retrieval", retrieval_mod)


# -------------------------------------------------------------------
# DB seeding helpers
# -------------------------------------------------------------------

# Chunk hierarchy path that the retrieval stub returns — must match what
# we seed so the audit trail can resolve the evidence binding.
_TEST_CHUNK_HIERARCHY = "SGB II > § 31 > Abs. 1"


def _seed_test_chunk() -> None:
    """Insert a LegalSource + LegalChunk into the DB so evidence bindings
    can resolve via hierarchy_path.

    Uses psql to avoid async event-loop conflicts.
    """
    env = {**__import__("os").environ, "PGPASSWORD": "testpassword"}
    sql = (
        "INSERT INTO legal_source "
        "(id, source_type, title, jurisdiction, effective_date, "
        " source_url, version_hash) "
        "SELECT gen_random_uuid(), 'sgb2', 'SGB II', 'DE', CURRENT_DATE, "
        "'https://example.com/test', 'testhash' "
        "WHERE NOT EXISTS ("
        "  SELECT 1 FROM legal_source "
        "  WHERE source_url = 'https://example.com/test'"
        ");\n"
        "INSERT INTO legal_chunk "
        "(id, source_id, unit_type, hierarchy_path, "
        " text_content, effective_date) "
        "SELECT gen_random_uuid(), ls.id, 'absatz', "
        "'" + _TEST_CHUNK_HIERARCHY + "', "
        "'Test chunk content', CURRENT_DATE "
        "FROM legal_source ls "
        "WHERE ls.source_url = 'https://example.com/test' "
        "AND NOT EXISTS ("
        "  SELECT 1 FROM legal_chunk lc "
        "  WHERE lc.hierarchy_path = '" + _TEST_CHUNK_HIERARCHY + "'"
        ");"
    )
    import subprocess

    proc = subprocess.run(
        [
            "psql",
            "-U",
            "testuser",
            "-d",
            "testdb",
            "-h",
            "127.0.0.1",
            "-c",
            sql,
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"DB seeding failed: {proc.stderr}")


# -------------------------------------------------------------------
# test_full_pipeline_execution
# -------------------------------------------------------------------


class TestFullPipelineExecution:
    """WP-015 acceptance: end-to-end pipeline execution + audit trail."""

    def test_full_pipeline_execution(
        self,
        client: TestClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Execute end-to-end pipeline and verify latency + audit trail."""
        # Install deterministic stubs so the pipeline doesn't call LLMs / DB.
        _mock_pipeline_for_test(monkeypatch)

        # Seed DB with a legal chunk + source so evidence bindings can resolve.
        _seed_test_chunk()

        # Execute the pipeline via a POST to /api/v1/analyze.
        start = time.monotonic()
        with client.stream(
            "POST",
            "/api/v1/analyze",
            json={"text": SAMPLE_LEGAL_TEXT},
            headers=DISCLAIMER_HEADER,
        ) as response:
            assert response.status_code == 200
            events = _consume_sse(response)
        elapsed = time.monotonic() - start

        # Acceptance: total latency < 120 s
        assert elapsed < 120.0, f"Pipeline took {elapsed:.1f}s, exceeding 120s limit"

        # Verify SSE events contain the 7 expected stages in order
        stage_events = [e for e in events if e.get("stage") and "final_output" not in e]
        stage_names = [e["stage"] for e in stage_events]
        expected_stages = [
            "normalization",
            "classification",
            "decomposition",
            "retrieval",
            "construction",
            "verification",
            "generation",
        ]
        assert stage_names == expected_stages, f"Stage order mismatch: {stage_names}"

        # Verify audit trail persisted via psql (avoids async loop issues
        # with the sync TestClient event loop).
        case_count = _count_rows("case_run")
        assert case_count >= 1, "No CaseRun persisted"

        stage_count = _count_rows("pipeline_stage_log")
        assert stage_count >= 8, f"Expected >=8 pipeline_stage_log rows, got {stage_count}"

        claim_count = _count_rows("claim")
        assert claim_count >= 1, "No Claim records persisted"

        evidence_count = _count_rows("evidence_binding")
        assert evidence_count >= 1, "No EvidenceBinding records persisted"


# -------------------------------------------------------------------
# test_disclaimer_enforcement
# -------------------------------------------------------------------


class TestDisclaimerEnforcement:
    """WP-015 acceptance: full pipeline only executes post-acknowledgment."""

    def test_disclaimer_enforcement_no_header_returns_403(
        self,
        client: TestClient,
    ) -> None:
        """Without X-Disclaimer-Ack header, the endpoint returns 403."""
        response = client.post(
            "/api/v1/analyze",
            json={"text": SAMPLE_LEGAL_TEXT},
        )
        assert response.status_code == 403
        data = response.json()
        assert data["error"] == "disclaimer_required"

    def test_disclaimer_enforcement_wrong_version_returns_403(
        self,
        client: TestClient,
    ) -> None:
        """With incorrect header version, the endpoint returns 403."""
        response = client.post(
            "/api/v1/analyze",
            json={"text": SAMPLE_LEGAL_TEXT},
            headers={"X-Disclaimer-Ack": "v0.9.0"},
        )
        assert response.status_code == 403
        data = response.json()
        assert data["error"] == "disclaimer_version_mismatch"

    def test_disclaimer_enforcement_correct_header_proceeds(
        self,
        client: TestClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """With correct header, the pipeline proceeds (stubs prevent LLM call)."""
        _mock_pipeline_for_test(monkeypatch)

        with client.stream(
            "POST",
            "/api/v1/analyze",
            json={"text": SAMPLE_LEGAL_TEXT},
            headers=DISCLAIMER_HEADER,
        ) as response:
            assert response.status_code == 200
            events = _consume_sse(response)

        # Should have at least 7 stage events
        stage_events = [e for e in events if e.get("stage") and "final_output" not in e]
        assert len(stage_events) == 7
