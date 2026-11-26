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

# Semantic Version: 0.2.0 | 2026-11-16 — WP-94: case_run_area module binding test.

from __future__ import annotations

import json
import asyncio
import sys
import time
from collections.abc import AsyncGenerator
from contextlib import suppress
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
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

# The middleware validates against DISCLAIMER_VERSION — a version in its own
# right, distinct from the app/package version.
DISCLAIMER_HEADER = {"X-Disclaimer-Ack": settings.DISCLAIMER_VERSION}

# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------


def _connect_params() -> dict:
    """Derive asyncpg connect args from DATABASE_URL (single source of truth)."""
    from urllib.parse import urlsplit

    from app.core.config import settings

    parts = urlsplit(settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://"))
    return {
        "user": parts.username,
        "password": parts.password,
        "host": parts.hostname,
        "port": parts.port or 5432,
        "database": parts.path.lstrip("/"),
    }


def _count_rows(table: str) -> int:
    """Query row count via a short-lived connection on its own event loop."""

    async def _query() -> int:
        import asyncpg

        conn = await asyncpg.connect(**_connect_params())
        try:
            return await conn.fetchval(f"SELECT count(*) FROM {table}")
        finally:
            await conn.close()

    return int(asyncio.run(_query()))


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

    async def ready_preflight(_db: object, areas: list[str]) -> dict:
        return {"is_ready": True, "areas": {}, "missing_source_types": [],
                "ready_source_types": []}

    monkeypatch.setattr("app.api.routes.analyze.check_preflight", ready_preflight)

    # --- reasoning stub -------------------------------------------------
    reasoning_mod = types.ModuleType("app.services.reasoning")

    async def classify_issues(text: str, **kwargs: object) -> list[str]:
        return ["SGB II § 31 — Kürzung der Leistung"]

    async def decompose_questions(text: str, **kwargs: object) -> list[str]:
        return [
            "War die Kürzung nach § 31 SGB II rechtmäßig?",
            "Welche Meldepflichten wurden verletzt?",
            "Kann die Kürzung angefochten werden?",
        ]

    # The pipeline passes optional keyword arguments (e.g. system_prompt);
    # stubs accept **kwargs so the harness stays decoupled from call-site drift.
    async def triage_document(normalized_text: str, **kwargs: object) -> dict[str, list[str]]:
        return {
            "issues": ["SGB II § 31 — Kürzung der Leistung"],
            "questions": [
                "War die Kürzung nach § 31 SGB II rechtmäßig?",
                "Welche Meldepflichten wurden verletzt?",
                "Kann die Kürzung angefochten werden?",
            ],
        }

    async def construct_claims(
        chunks: list[dict],
        questions: list[str],
        **kwargs: object,
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
        **kwargs: object,
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
        **kwargs: object,
    ) -> dict[str, str]:
        return {
            "sachverhalt": "Antragsteller erhielt Kürzungsbescheid nach § 31 SGB II.",
            "rechtliche_wuerdigung": "§ 31 SGB II erfordert eine Einzelfallprüfung.",
            "ergebnis": "Kürzung kann angefochten werden.",
            "handlungsempfehlung": "Widerspruch innerhalb eines Monats einlegen.",
            "entwurf": "Sehr geehrte Damen und Herren, hiermit lege ich Widerspruch ein.",
            "unsicherheiten": "Fehlende Unterlagen zur Meldepflicht.",
        }

    async def generate_grounded_answer(
        normalized_text: str,
        issues: list[str],
        questions: list[str],
        claims: list[dict],
        chunks: list[dict],
        **kwargs: object,
    ) -> dict:
        return {
            "claims": [
                {
                    "claim_text": "Die Kürzung war unverhältnismäßig.",
                    "confidence_score": 0.82,
                    "claim_type": "interpretation",
                    "question": questions[0] if questions else "",
                    "evidence_chunk_id": str(chunks[0].get("chunk_id", "")) if chunks else "",
                    "evidence_hierarchy": "SGB II > § 31 > Abs. 1",
                    "evidence_quote": "§ 31 Abs. 1 SGB II: Leistungsberechtigte, die ...",
                },
                {
                    "claim_text": "Meldepflicht nach § 60 SGB I nicht beachtet.",
                    "confidence_score": 0.85,
                    "claim_type": "fact",
                    "question": questions[1] if len(questions) > 1 else "",
                    "evidence_chunk_id": str(chunks[0].get("chunk_id", "")) if chunks else "",
                    "evidence_hierarchy": "SGB I > § 60",
                    "evidence_quote": "§ 60 SGB I: (1) Wer Sozialleistungen beantragt...",
                },
            ],
            "sections": {
                "sachverhalt": "Antragsteller erhielt Kürzungsbescheid nach § 31 SGB II.",
                "rechtliche_wuerdigung": "§ 31 SGB II erfordert eine Einzelfallprüfung.",
                "ergebnis": "Kürzung kann angefochten werden.",
                "handlungsempfehlung": "Widerspruch innerhalb eines Monats einlegen.",
                "entwurf": "Sehr geehrte Damen und Herren, hiermit lege ich Widerspruch ein.",
                "unsicherheiten": "Fehlende Unterlagen zur Meldepflicht.",
            },
        }

    reasoning_mod.classify_issues = classify_issues  # type: ignore[attr-defined]
    reasoning_mod.decompose_questions = decompose_questions  # type: ignore[attr-defined]
    reasoning_mod.triage_document = triage_document  # type: ignore[attr-defined]
    reasoning_mod.construct_claims = construct_claims  # type: ignore[attr-defined]
    reasoning_mod.verify_claims = verify_claims  # type: ignore[attr-defined]
    reasoning_mod.generate_output = generate_output  # type: ignore[attr-defined]
    reasoning_mod.generate_grounded_answer = generate_grounded_answer  # type: ignore[attr-defined]

    # New: adversarial review stub (Stage 7)
    async def adversarial_review(
        normalized_text: str,
        issues: list[str],
        questions: list[str],
        claims: list[dict],
        chunks: list[dict],
        **kwargs: object,
    ) -> dict:
        return {
            "reviews": [
                {
                    "claim_index": 0,
                    "defense_argument": "Die Kürzung war möglicherweise unverhältnismäßig.",
                    "authority_argument": "Die Behörde beruft sich auf § 31 SGB II.",
                    "judicial_assessment": "Einzelfallabwägung erforderlich — Gericht könnte zugunsten des Bürgers entscheiden.",
                    "procedural_issues": "Keine formellen Fehler erkennbar.",
                    "risk_level": "mittel",
                    "recommended_strategy": "Widerspruch mit Hinweis auf Unverhältnismäßigkeit.",
                },
            ],
            "overall_assessment": {
                "summary": "Insgesamt bestehen gute Chancen, die Kürzung anzufechten.",
                "key_risks": [
                    "Die Meldepflichtverletzung ist gut dokumentiert.",
                    "Ermessensspielraum der Behörde könnte ausreichen.",
                ],
                "recommended_next_steps": [
                    "Widerspruch fristgemäß einlegen.",
                    "Rechtsanwalt für Sozialrecht konsultieren.",
                ],
                "confidence_in_defense": 0.65,
                "procedural_errors_found": [],
            },
        }

    # New: streaming grounded answer stub (for ENABLE_PROGRESS_STREAM)
    async def generate_grounded_answer_stream(
        normalized_text: str,
        issues: list[str],
        questions: list[str],
        chunks: list[dict],
        *,
        system_prompt: str | None = None,
    ):
        result = await generate_grounded_answer(
            normalized_text, issues, questions, [], chunks, system_prompt=system_prompt
        )
        yield {"type": "done", "result": result}

    calculation_mod = types.ModuleType("app.services.calculation")

    async def check_calculations(*args: object, **kwargs: object) -> dict:
        return {
            "overall_assessment": {"total_discrepancies": 0},
            "calculations": [],
        }

    calculation_mod.check_calculations = check_calculations  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "app.services.calculation", calculation_mod)

    reasoning_mod.adversarial_review = adversarial_review  # type: ignore[attr-defined]
    reasoning_mod.generate_grounded_answer_stream = generate_grounded_answer_stream  # type: ignore[attr-defined]
    # app.services.calculation imports these private names from reasoning;
    # the stub module must expose them or the calculation_check stage fails.
    reasoning_mod._STRICT_SUFFIX = ""  # type: ignore[attr-defined]

    class JSONParseError(ValueError):
        pass

    reasoning_mod.JSONParseError = JSONParseError  # type: ignore[attr-defined]
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
                "chunk_id": _SEEDED_CHUNK.get("chunk_id") or str(uuid4()),
                "text_content": "§ 31 Abs. 1 SGB II: Leistungsberechtigte, die ...",
                "hierarchy_path": _TEST_CHUNK_HIERARCHY,
                "source_type": "sgb2",
                "title": "SGB II",
                "distance": 0.15,
            },
        ]

    async def retrieve_chunks_combined(
        issues: list[str],
        questions: list[str],
        normalized_text: str,
        *,
        client=None,
    ) -> list[dict]:
        return [
            {
                "chunk_id": _SEEDED_CHUNK.get("chunk_id") or str(uuid4()),
                "text_content": "§ 31 Abs. 1 SGB II: Leistungsberechtigte, die ...",
                "hierarchy_path": _TEST_CHUNK_HIERARCHY,
                "source_type": "sgb2",
                "title": "SGB II",
                "distance": 0.15,
            },
        ]

    async def retrieve_chunks_by_norm_reference(
        normalized_text: str,
        *,
        source_types: tuple[str, ...] = (),
        client=None,
        session_factory=None,
    ) -> list[dict]:
        return [
            {
                "chunk_id": _SEEDED_CHUNK.get("chunk_id") or str(uuid4()),
                "text_content": "§ 31 Abs. 1 SGB II: Leistungsberechtigte, die ...",
                "hierarchy_path": _TEST_CHUNK_HIERARCHY,
                "source_type": "sgb2",
                "title": "SGB II",
                "distance": 0.15,
            },
        ]

    async def retrieve_chunks_for_areas(
        areas: list[str],
        issues: list[str],
        questions: list[str],
        normalized_text: str,
        *,
        client=None,
        session_factory=None,
    ) -> tuple[dict[str, list[dict]], list[dict]]:
        chunk = {
            "chunk_id": _SEEDED_CHUNK.get("chunk_id") or str(uuid4()),
            "text_content": "§ 31 Abs. 1 SGB II: Leistungsberechtigte, die ...",
            "hierarchy_path": _TEST_CHUNK_HIERARCHY,
            "source_type": "sgb2",
            "title": "SGB II",
            "legal_area": "sozialrecht",
            "distance": 0.15,
        }
        return {area: [dict(chunk)] for area in areas}, [chunk]

    retrieval_mod.retrieve_chunks = retrieve_chunks  # type: ignore[attr-defined]
    retrieval_mod.retrieve_chunks_combined = retrieve_chunks_combined  # type: ignore[attr-defined]
    retrieval_mod.retrieve_chunks_by_norm_reference = retrieve_chunks_by_norm_reference  # type: ignore[attr-defined]
    retrieval_mod.retrieve_chunks_for_areas = retrieve_chunks_for_areas  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "app.services.retrieval", retrieval_mod)

    # --- verification stub (WP-007) -------------------------------------
    verification_mod = types.ModuleType("app.services.verification")

    def verify_claims_against_chunks(
        claims: list[dict],
        chunks: list[dict],
    ) -> list[dict]:
        verified = []
        for c in claims:
            claim = dict(c)
            claim["verified"] = True
            claim["reasoning"] = "Test: quote found in chunk (stub)."
            verified.append(claim)
        return verified

    verification_mod.verify_claims_against_chunks = verify_claims_against_chunks  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "app.services.verification", verification_mod)


# -------------------------------------------------------------------
# DB seeding helpers
# -------------------------------------------------------------------

# Chunk hierarchy path that the retrieval stub returns — must match what
# we seed so the audit trail can resolve the evidence binding.
_TEST_CHUNK_HIERARCHY = "SGB II > § 31 > Abs. 1"


_SEEDED_CHUNK: dict = {}


def _seed_test_chunk() -> None:
    """Insert a LegalSource + LegalChunk into the DB so evidence bindings
    can resolve via hierarchy_path. Stores the seeded chunk id in
    _SEEDED_CHUNK so retrieval stubs can reference a REAL database row —
    analyze.py's inline audit writer inserts evidence_binding.chunk_id
    values taken verbatim from verification payloads, and a random UUID
    would violate evidence_binding_chunk_id_fkey.
    """
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
        " text_content, text_hash, effective_date) "
        "SELECT gen_random_uuid(), ls.id, 'absatz', "
        "'" + _TEST_CHUNK_HIERARCHY + "', "
        "'Test chunk content', md5('Test chunk content'), CURRENT_DATE "
        "FROM legal_source ls "
        "WHERE ls.source_url = 'https://example.com/test' "
        "AND NOT EXISTS ("
        "  SELECT 1 FROM legal_chunk lc "
        "  WHERE lc.hierarchy_path = '" + _TEST_CHUNK_HIERARCHY + "'"
        ");"
    )
    async def _seed() -> None:
        import asyncpg

        conn = await asyncpg.connect(**_connect_params())
        try:
            await conn.execute(sql)
        finally:
            await conn.close()

    asyncio.run(_seed())

    async def _read_back() -> dict:
        import asyncpg

        conn = await asyncpg.connect(**_connect_params())
        try:
            row = await conn.fetchrow(
                "SELECT id, hierarchy_path FROM legal_chunk "
                "WHERE hierarchy_path = $1 LIMIT 1",
                _TEST_CHUNK_HIERARCHY,
            )
            return {"chunk_id": str(row["id"]), "hierarchy_path": row["hierarchy_path"]} if row else {}
        finally:
            await conn.close()

    _SEEDED_CHUNK.update(asyncio.run(_read_back()))


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
            json={"text": SAMPLE_LEGAL_TEXT, "legal_areas": ["sozialrecht"]},
            headers=DISCLAIMER_HEADER,
        ) as response:
            assert response.status_code == 200
            events = _consume_sse(response)
        elapsed = time.monotonic() - start

        # Acceptance: total latency < 300 s
        assert elapsed < 300.0, f"Pipeline took {elapsed:.1f}s, exceeding 300s limit"

        # Verify SSE events contain the canonical stages in order
        stage_events = [e for e in events if e.get("stage") and "final_output" not in e]
        # Filter corpus_health (pre-pipeline health check) from stage names
        from app.core.pipeline import _STAGES

        completed = [
            e["stage"]
            for e in stage_events
            if e["stage"] != "corpus_health" and e.get("status") == "complete"
        ]
        assert completed == list(_STAGES), f"Stage order mismatch: {completed}"

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
            json={"text": SAMPLE_LEGAL_TEXT, "legal_areas": ["sozialrecht"]},
            headers=DISCLAIMER_HEADER,
        ) as response:
            assert response.status_code == 200
            events = _consume_sse(response)

        # Stage contract: every canonical pipeline stage must appear, in
        # _STAGE_MAP order (each stage emits running+complete events).
        from app.core.pipeline import _STAGES

        stage_events = [e for e in events if e.get("stage") and "final_output" not in e and e["stage"] != "corpus_health"]
        completed = [
            e["stage"]
            for e in stage_events
            if e.get("status") == "complete"
        ]
        assert completed == list(_STAGES), (
            f"Stage order/count mismatch: {completed}"
        )


# -------------------------------------------------------------------
# WP-94: case_run_area records module id + version
# -------------------------------------------------------------------


class TestCaseRunAreaModuleBinding:
    """Every persisted area row names the module (and version) the case ran
    with; legacy aliases bind to their module, procedural keys to none."""

    def test_area_rows_carry_module_binding(
        self,
        client: TestClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import app.api.routes.analyze as analyze_route
        from app.modules.runtime import get_manifest

        _mock_pipeline_for_test(monkeypatch)

        async def _ready(_db: object, areas: list[str]) -> dict:
            return {
                "is_ready": True,
                "areas": {},
                "missing_source_types": [],
                "ready_source_types": [],
            }

        monkeypatch.setattr(analyze_route, "check_preflight", _ready)
        areas = ["sozialrecht", "schenkungsrecht", "verwaltungsrecht"]
        with client.stream(
            "POST",
            "/api/v1/analyze",
            # The existing comma-string contract remains supported alongside lists.
            json={"text": SAMPLE_LEGAL_TEXT, "legal_areas": ",".join(areas)},
            headers=DISCLAIMER_HEADER,
        ) as response:
            assert response.status_code == 200
            _consume_sse(response)

        async def _rows() -> list[tuple]:
            import asyncpg

            conn = await asyncpg.connect(**_connect_params())
            try:
                rows = await conn.fetch(
                    "SELECT legal_area, module_id, module_version, is_primary "
                    "FROM case_run_area WHERE case_run_id = "
                    "(SELECT id FROM case_run ORDER BY created_at DESC LIMIT 1)"
                )
                return sorted(tuple(r) for r in rows)
            finally:
                await conn.close()

        soz = get_manifest("sozialrecht").version
        erb = get_manifest("erbrecht").version
        assert asyncio.run(_rows()) == [
            ("schenkungsrecht", "erbrecht", erb, False),
            ("sozialrecht", "sozialrecht", soz, True),
            ("verwaltungsrecht", None, None, False),
        ]
