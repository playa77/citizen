"""Art. 50 EU AI Act disclosure & provenance tests (D-032).

Covers the guarded invariants G-50-A..G-50-G from DECISIONS.md:
- GET /api/v1/meta/disclosure shape, texts, and X-Disclaimer-Ack enforcement
- GET /api/v1/meta/version includes disclosure_version
- analyze SSE terminal event embeds disclosure + provenance (error events do not)
- conversation chat done event embeds both objects
- POST /api/v1/documents/generate embeds provenance (and no disclosure)
- build_disclosure_and_provenance validity and never-raise fallback behavior
- Pydantic serialization round-trips and openapi.json reflection

Event-loop discipline: the app is driven via httpx ASGITransport inside each
async test, so endpoint DB access, seeding, and cleanup all share ONE event
loop. asyncpg connections are loop-bound and the process-global engine pools
them; an autouse fixture disposes the engine after every test so no pooled
connection can ever be handed to a later test's fresh loop.
"""

# Semantic Version: 1.0.0

from __future__ import annotations

import asyncio
import contextlib
import json
import uuid
from collections.abc import AsyncGenerator
from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from sqlalchemy import delete as sa_delete

from app.core.config import get_app_version, settings
from app.db.models import CaseRun
from app.db.session import async_session_factory, engine
from app.main import app
from app.services.disclosure import (
    DISCLOSURE_TEXT_DE,
    DISCLOSURE_TEXT_EN,
    DISCLOSURE_VERSION,
    PROVENANCE_SPEC_VERSION,
    DisclosureInfo,
    ProvenanceMarker,
    build_disclosure_and_provenance,
)

# -------------------------------------------------------------------
# Fixtures / helpers
# -------------------------------------------------------------------

DISCLAIMER_HEADERS = {"X-Disclaimer-Ack": settings.DISCLAIMER_VERSION}

FROZEN_UTC_NOW = "2026-08-25T12:00:00Z"


@pytest.fixture(autouse=True)
async def _dispose_engine_per_test() -> AsyncGenerator[None, None]:
    """Drop all pooled connections after each test.

    Every test runs on a fresh pytest-asyncio loop; pooled connections from
    the previous loop are unusable there (asyncpg binds them to their creating
    loop). Disposal keeps the pool empty at every test boundary.
    """
    yield
    with contextlib.suppress(Exception):
        await engine.dispose()


@pytest.fixture
async def client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """ASGI transport client — the app runs on the test's own event loop."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


def make_sse(data: dict[str, Any]) -> str:
    """Format *data* as an SSE data line (mirrors the route helpers)."""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


async def consume_sse(response: httpx.Response) -> list[dict[str, Any]]:
    """Read a streaming response fully and parse every SSE payload."""
    content = (await response.aread()).decode("utf-8")
    events: list[dict[str, Any]] = []
    for line in content.splitlines():
        line = line.strip()
        if line.startswith("data: "):
            with contextlib.suppress(json.JSONDecodeError):
                events.append(json.loads(line[6:].strip()))
    return events


async def drain_background_tasks(timeout: float = 10.0) -> None:
    """Wait for fire-and-forget tasks (e.g. background audit persistence).

    The analyze endpoint schedules audit persistence with
    ``asyncio.create_task``; on a short-lived test loop those tasks must be
    awaited before loop shutdown or their DB sessions leak connections.
    """
    pending = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    if pending:
        await asyncio.wait(pending, timeout=timeout)


def assert_valid_provenance(provenance: Any) -> None:
    """Assert the Art. 50(2) marker shape and field types (all strings)."""
    assert isinstance(provenance, dict)
    expected_keys = {
        "spec_version",
        "generator",
        "app_version",
        "model_profile",
        "timestamp_utc",
        "deployment_mode",
    }
    assert set(provenance.keys()) == expected_keys
    for value in provenance.values():
        assert isinstance(value, str)
    assert provenance["spec_version"] == PROVENANCE_SPEC_VERSION
    assert provenance["generator"] == "citizen"
    # ISO 8601 UTC timestamp, parseable and explicitly UTC.
    parsed = datetime.fromisoformat(provenance["timestamp_utc"].replace("Z", "+00:00"))
    assert parsed.tzinfo is not None
    assert parsed.utcoffset().total_seconds() == 0


def assert_valid_disclosure(disclosure: Any) -> None:
    """Assert the Art. 50(1) notification shape and canonical texts."""
    assert isinstance(disclosure, dict)
    assert set(disclosure.keys()) == {"version", "must_display_before", "texts"}
    assert disclosure["version"] == DISCLOSURE_VERSION
    assert disclosure["must_display_before"] == "results"
    assert set(disclosure["texts"].keys()) == {"de", "en"}
    assert disclosure["texts"]["de"] == DISCLOSURE_TEXT_DE
    assert disclosure["texts"]["en"] == DISCLOSURE_TEXT_EN


# -------------------------------------------------------------------
# G-50-A — GET /api/v1/meta/disclosure
# -------------------------------------------------------------------


class TestMetaDisclosureEndpoint:
    """GET /api/v1/meta/disclosure — shape, texts, ack enforcement."""

    async def test_returns_canonical_disclosure_with_valid_ack(
        self, client: httpx.AsyncClient
    ) -> None:
        response = await client.get("/api/v1/meta/disclosure", headers=DISCLAIMER_HEADERS)

        assert response.status_code == 200
        assert_valid_disclosure(response.json())

    async def test_missing_ack_header_returns_403(self, client: httpx.AsyncClient) -> None:
        # The disclaimer middleware excludes /api/v1/meta entirely, so this
        # exercises the route-level dependency added in D-032.
        response = await client.get("/api/v1/meta/disclosure")

        assert response.status_code == 403
        assert response.json()["detail"]["error"] == "disclaimer_required"
        assert response.json()["detail"]["required_version"] == settings.DISCLAIMER_VERSION

    async def test_wrong_ack_version_returns_403(self, client: httpx.AsyncClient) -> None:
        response = await client.get(
            "/api/v1/meta/disclosure", headers={"X-Disclaimer-Ack": "v0.0.1"}
        )

        assert response.status_code == 403
        detail = response.json()["detail"]
        assert detail["error"] == "disclaimer_version_mismatch"
        assert detail["acknowledged_version"] == "v0.0.1"


# -------------------------------------------------------------------
# G-50-B — GET /api/v1/meta/version
# -------------------------------------------------------------------


class TestMetaVersionEndpoint:
    """GET /api/v1/meta/version — additive disclosure_version key."""

    async def test_includes_disclosure_version_and_keeps_existing_keys(
        self, client: httpx.AsyncClient
    ) -> None:
        response = await client.get("/api/v1/meta/version")

        assert response.status_code == 200
        data = response.json()
        assert data["disclosure_version"] == DISCLOSURE_VERSION
        # Existing contract keys must be present and unchanged.
        assert data["api_version"] == get_app_version()
        assert data["disclaimer_version"] == settings.DISCLAIMER_VERSION


# -------------------------------------------------------------------
# G-50-C — analyze SSE terminal event
# -------------------------------------------------------------------


class TestAnalyzeTerminalEvent:
    """POST /api/v1/analyze terminal event embeds disclosure + provenance."""

    @patch("app.api.routes.analyze.run_pipeline")
    async def test_terminal_event_contains_both_objects(
        self, mock_run_pipeline: MagicMock, client: httpx.AsyncClient
    ) -> None:
        async def mock_generator(state: Any):
            yield make_sse(
                {"stage": "normalization", "status": "complete", "payload": {"text_length": 42}}
            )
            state.final_output = {
                "sachverhalt": "Sachverhalt.",
                "rechtliche_wuerdigung": "Würdigung.",
                "ergebnis": "Ergebnis.",
                "handlungsempfehlung": "Empfehlung.",
                "entwurf": "Entwurf.",
                "unsicherheiten": "Unsicherheiten.",
            }

        mock_run_pipeline.side_effect = lambda state: mock_generator(state)

        async with client.stream(
            "POST",
            "/api/v1/analyze",
            json={"text": "Testbescheid."},
            headers=DISCLAIMER_HEADERS,
        ) as response:
            assert response.status_code == 200
            events = await consume_sse(response)

        await drain_background_tasks()

        finals = [e for e in events if "final_output" in e]
        assert len(finals) == 1
        final = finals[0]

        # Existing fields remain present and unchanged.
        assert "session_id" in final
        assert "sections" in final
        assert "final_output" in final

        assert_valid_disclosure(final["disclosure"])
        assert_valid_provenance(final["provenance"])
        assert final["provenance"]["model_profile"] == settings.INFERENCE_PROFILE
        assert final["provenance"]["deployment_mode"] == settings.DEPLOYMENT_MODE
        assert final["provenance"]["app_version"] == get_app_version()

    @patch("app.api.routes.analyze.run_pipeline")
    async def test_error_event_carries_neither_object(
        self, mock_run_pipeline: MagicMock, client: httpx.AsyncClient
    ) -> None:
        """Error events carry no AI-generated text — no disclosure/provenance."""
        mock_run_pipeline.side_effect = RuntimeError("Pipeline exploded")

        async with client.stream(
            "POST",
            "/api/v1/analyze",
            json={"text": "trigger failure"},
            headers=DISCLAIMER_HEADERS,
        ) as response:
            assert response.status_code == 200
            events = await consume_sse(response)

        await drain_background_tasks()

        errors = [e for e in events if e.get("error") == "pipeline_failed"]
        assert len(errors) == 1
        assert "disclosure" not in errors[0]
        assert "provenance" not in errors[0]


# -------------------------------------------------------------------
# G-50-D — conversation chat done event
# -------------------------------------------------------------------


class TestChatDoneEvent:
    """generate_chat_response done event embeds disclosure + provenance."""

    async def test_done_event_contains_both_objects(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.services.chat_reasoning import generate_chat_response

        mock_client = MagicMock()
        mock_client.chat_completion = AsyncMock(return_value="Das ist die Antwort.")
        monkeypatch.setattr("app.services.chat_reasoning.get_shared_client", lambda: mock_client)
        monkeypatch.setattr(
            "app.services.chat_reasoning.retrieve_chunks_combined",
            AsyncMock(return_value=[]),
        )

        events: list[dict[str, Any]] = []
        async for event in generate_chat_response(
            messages=[{"role": "user", "content": "Welche Frist gilt?"}],
            document_texts=None,
            conversation_id="conv-1",
        ):
            assert event.startswith("data: ")
            events.append(json.loads(event[6:].strip()))

        dones = [e for e in events if e.get("type") == "done"]
        assert len(dones) == 1
        done = dones[0]
        assert done["full_response"] == "Das ist die Antwort."

        assert_valid_disclosure(done["disclosure"])
        assert_valid_provenance(done["provenance"])


# -------------------------------------------------------------------
# G-50-E — POST /api/v1/documents/generate
# -------------------------------------------------------------------


class TestDocumentsGenerateProvenance:
    """Document generation response carries provenance (never disclosure)."""

    async def test_generate_response_contains_provenance(
        self, client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Freeze the clock so the endpoint's marker is byte-identical to a
        # direct helper call in this test (acceptance criterion: identical
        # provenance across surfaces for the same request).
        monkeypatch.setattr("app.services.disclosure._utc_now_iso", lambda: FROZEN_UTC_NOW)

        # Seed on the SAME loop the app will run on (ASGI transport).
        async with async_session_factory() as db:
            case_run = CaseRun(
                session_id=str(uuid.uuid4()),
                input_text="Testbescheid für Dokumentgenerierung.",
                status="completed",
                latency_ms=1,
                title="Testfall",
            )
            db.add(case_run)
            await db.flush()
            case_run_id = case_run.id
            await db.commit()

        try:
            response = await client.post(
                "/api/v1/documents/generate",
                json={"case_run_id": str(case_run_id)},
                headers=DISCLAIMER_HEADERS,
            )
        finally:
            async with async_session_factory() as db:
                await db.execute(sa_delete(CaseRun).where(CaseRun.id == case_run_id))
                await db.commit()

        assert response.status_code == 200, response.text
        body = response.json()

        assert "provenance" in body
        assert_valid_provenance(body["provenance"])
        assert body["provenance"]["timestamp_utc"] == FROZEN_UTC_NOW

        # Identical provenance content as a direct helper call at the same
        # instant proves the shared-helper requirement end-to-end.
        _, expected_provenance = build_disclosure_and_provenance(settings)
        assert body["provenance"] == expected_provenance.model_dump(mode="json")

        # Deliberately NO disclosure field on documents (see D-032).
        assert "disclosure" not in body


# -------------------------------------------------------------------
# G-50-F — build_disclosure_and_provenance robustness
# -------------------------------------------------------------------


class BrokenSettings:
    """Settings stand-in whose every attribute access explodes."""

    def __getattr__(self, name: str) -> str:
        raise RuntimeError(f"broken settings: {name}")


class TestBuildDisclosureAndProvenance:
    """Shared helper returns valid instances and never raises."""

    def test_returns_valid_instances_from_live_settings(self) -> None:
        disclosure, provenance = build_disclosure_and_provenance(settings)

        assert isinstance(disclosure, DisclosureInfo)
        assert isinstance(provenance, ProvenanceMarker)
        assert_valid_disclosure(disclosure.model_dump(mode="json"))
        assert_valid_provenance(provenance.model_dump(mode="json"))
        assert provenance.deployment_mode == settings.DEPLOYMENT_MODE

    def test_never_raises_on_broken_settings(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Force every extraction path into its fallback branch.
        monkeypatch.setattr(
            "app.services.disclosure.get_app_version",
            lambda: (_ for _ in ()).throw(RuntimeError("no package metadata")),
        )
        monkeypatch.setattr(
            "app.services.disclosure._utc_now_iso",
            lambda: (_ for _ in ()).throw(RuntimeError("no clock")),
        )

        disclosure, provenance = build_disclosure_and_provenance(BrokenSettings())  # type: ignore[arg-type]

        assert isinstance(disclosure, DisclosureInfo)
        assert isinstance(provenance, ProvenanceMarker)
        # Constants survive; undeterminable fields degrade to the fallback.
        assert disclosure.texts["de"] == DISCLOSURE_TEXT_DE
        assert provenance.app_version == "unknown"
        assert provenance.model_profile == "unknown"
        assert provenance.timestamp_utc == "unknown"
        assert provenance.deployment_mode == "unknown"
        assert provenance.spec_version == PROVENANCE_SPEC_VERSION


# -------------------------------------------------------------------
# G-50-G — serialization and OpenAPI reflection
# -------------------------------------------------------------------


class TestModelSerialization:
    """Both models serialize to valid JSON without errors."""

    def test_disclosure_info_json_round_trip(self) -> None:
        model = DisclosureInfo(
            version="1.0",
            must_display_before="results",
            texts={"de": DISCLOSURE_TEXT_DE, "en": DISCLOSURE_TEXT_EN},
        )
        parsed = json.loads(model.model_dump_json())
        assert parsed == model.model_dump(mode="json")
        assert DisclosureInfo.model_validate(parsed) == model

    def test_provenance_marker_json_round_trip(self) -> None:
        model = ProvenanceMarker(
            spec_version=PROVENANCE_SPEC_VERSION,
            generator="citizen",
            app_version="2.0.0",
            model_profile="eu-avv",
            timestamp_utc=FROZEN_UTC_NOW,
            deployment_mode="dev",
        )
        parsed = json.loads(model.model_dump_json())
        assert parsed == model.model_dump(mode="json")
        assert ProvenanceMarker.model_validate(parsed) == model


class TestOpenApiReflection:
    """openapi.json stays parseable and reflects the new surface."""

    async def test_openapi_contains_disclosure_path_and_schema(
        self, client: httpx.AsyncClient
    ) -> None:
        response = await client.get("/openapi.json")
        assert response.status_code == 200

        spec = response.json()
        path_item = spec["paths"]["/api/v1/meta/disclosure"]
        assert "get" in path_item

        ok_schema = path_item["get"]["responses"]["200"]["content"]["application/json"]["schema"]
        assert ok_schema.get("$ref", "").endswith("/DisclosureInfo")

        component = spec["components"]["schemas"]["DisclosureInfo"]
        assert set(component["properties"].keys()) == {
            "version",
            "must_display_before",
            "texts",
        }
