"""Integration tests for WP-013: FastAPI Routes & Payload Validation.

Tests cover:
- ``POST /api/v1/ingest`` — file upload, OCR size/MIME validation, JSON response
- ``POST /api/v1/analyze`` — pipeline execution (mocked), SSE streaming, final 6-part JSON
- ``POST /api/v1/corpus/update`` — background job scheduling, 202 response

These tests use FastAPI's ``TestClient`` (sync) and mock heavy external
dependencies (OCR, LLM, DB) to ensure deterministic, fast execution while
still validating HTTP layer behavior, response codes, and payload shapes.
"""

from __future__ import annotations

import json
import logging
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from starlette.background import BackgroundTask

from app.main import app

# -------------------------------------------------------------------
# TestClient fixture
# -------------------------------------------------------------------


@pytest.fixture
def client() -> TestClient:
    """Return a synchronous TestClient for the FastAPI app."""
    return TestClient(app)


# -------------------------------------------------------------------
# Ingest endpoint tests
# -------------------------------------------------------------------


class TestIngestEndpoint:
    """Tests for POST /api/v1/ingest."""

    def test_ingest_returns_200_with_text(self, client: TestClient) -> None:
        """Valid PDF upload returns 200 with a JSON body containing extracted text."""
        fake_pdf = b"%PDF-1.4\n1 0 obj<<>>endobj 2 0 obj<<>>endobj xref 0 3 trailer<</Root 1 0 R>> startxref 8 %%EOF"

        with patch("app.api.routes.ingest.process_document", new_callable=AsyncMock) as mock_proc:
            mock_proc.return_value = "Normalized text from mocked PDF."
            response = client.post(
                "/api/v1/ingest",
                files={"file": ("test.pdf", fake_pdf, "application/pdf")},
            )

        assert response.status_code == 200
        data = response.json()
        assert "text" in data
        assert data["text"] == "Normalized text from mocked PDF."

    def test_ingest_rejects_unsupported_mime(self, client: TestClient) -> None:
        """Upload with an unsupported MIME type returns 415."""
        fake_txt = b"Plain text content."
        response = client.post(
            "/api/v1/ingest",
            files={"file": ("test.txt", fake_txt, "text/plain")},
        )
        assert response.status_code == 415
        body = response.json()
        assert "detail" in body
        assert "Unsupported media type" in body["detail"]

    def test_ingest_oversized_file_returns_400(self, client: TestClient) -> None:
        """File exceeding MAX_FILE_SIZE_MB raises HTTP 400."""
        large_content = b"x" * (26 * 1024 * 1024)  # 26 MB
        with patch(
            "app.api.routes.ingest.process_document",
            side_effect=ValueError("File size 26.0 MB exceeds the 25 MB limit."),
        ):
            response = client.post(
                "/api/v1/ingest",
                files={"file": ("huge.pdf", large_content, "application/pdf")},
            )
        assert response.status_code == 400
        body = response.json()
        assert "detail" in body
        assert "exceeds" in body["detail"].lower()

    def test_ingest_ocr_failure_returns_400(self, client: TestClient) -> None:
        """When OCR yields no text, endpoint returns 400."""
        fake_pdf = b"dummy"
        from app.services.ocr import OCRFailedError

        with patch("app.api.routes.ingest.process_document", side_effect=OCRFailedError("empty")):
            response = client.post(
                "/api/v1/ingest",
                files={"file": ("blank.pdf", fake_pdf, "application/pdf")},
            )
        assert response.status_code == 400
        body = response.json()
        assert "OCR processing failed" in body["detail"]


# -------------------------------------------------------------------
# Analyze endpoint tests
# -------------------------------------------------------------------


class TestAnalyzeEndpoint:
    """Tests for POST /api/v1/analyze (SSE streaming)."""

    def _consume_sse(self, response) -> list[dict]:
        """Consume the entire streaming response and parse SSE events into dicts."""
        content_bytes = b"".join(response.iter_bytes())
        content = content_bytes.decode("utf-8")
        events: list[dict] = []
        for line in content.splitlines():
            line = line.strip()
            if line.startswith("data: "):
                payload_str = line[6:].strip()
                if payload_str:
                    try:
                        events.append(json.loads(payload_str))
                    except json.JSONDecodeError:
                        pass
        return events

    @patch("app.api.routes.analyze.run_pipeline")
    def test_analyze_returns_200_and_streams_events(
        self, mock_run_pipeline, client: TestClient
    ) -> None:
        """Valid text input streams SSE events and ends with final 6-part JSON."""

        def make_sse(data: dict) -> str:
            return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

        async def mock_generator(state):
            yield make_sse(
                {"stage": "normalization", "status": "complete", "payload": {"text_length": 123}}
            )
            yield make_sse(
                {
                    "stage": "classification",
                    "status": "complete",
                    "payload": {"issues": ["SGB II"]},
                }
            )
            # Populate final_output so route's terminal event has content
            state.final_output = {
                "sachverhalt": "Sachverhalt Text.",
                "rechtliche_wuerdigung": "Rechtliche Würdigung.",
                "ergebnis": "Ergebnis.",
                "handlungsempfehlung": "Handlungsempfehlung.",
                "entwurf": "Entwurf eines Schreibens.",
                "unsicherheiten": "Unsicherheiten.",
            }
            # Final event is added by the route itself, not from run_pipeline

        mock_run_pipeline.side_effect = lambda state: mock_generator(state)

        # Act — use streaming context manager
        with client.stream(
            "POST",
            "/api/v1/analyze",
            json={"text": "Dies ist ein Testdokument vom Jobcenter."},
        ) as response:
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/event-stream")
            events = self._consume_sse(response)

        # Should have at least two stage events + one final summary
        stage_events = [e for e in events if e.get("stage")]
        assert len(stage_events) >= 2
        assert stage_events[0]["stage"] == "normalization"

        # Final event should contain final_output with all 6 sections
        final_payloads = [e for e in events if "final_output" in e]
        assert len(final_payloads) == 1
        final = final_payloads[0]["final_output"]
        required_keys = [
            "sachverhalt",
            "rechtliche_wuerdigung",
            "ergebnis",
            "handlungsempfehlung",
            "entwurf",
            "unsicherheiten",
        ]
        for key in required_keys:
            assert key in final
            assert isinstance(final[key], str)

    def test_analyze_missing_text_returns_400(self, client: TestClient) -> None:
        """Request body without 'text' field is rejected."""
        response = client.post("/api/v1/analyze", json={})
        assert response.status_code == 400
        body = response.json()
        assert "detail" in body
        assert "non-empty 'text' field" in body["detail"]

    def test_analyze_empty_text_returns_400(self, client: TestClient) -> None:
        """Request body with empty string is rejected."""
        response = client.post("/api/v1/analyze", json={"text": "   "})
        assert response.status_code == 400

    @patch("app.api.routes.analyze.run_pipeline")
    def test_analyze_pipeline_failure_returns_error_event(
        self, mock_run_pipeline, client: TestClient
    ) -> None:
        """When the pipeline raises an exception, an error SSE event is yielded."""
        mock_run_pipeline.side_effect = RuntimeError("Pipeline exploded")

        with client.stream(
            "POST",
            "/api/v1/analyze",
            json={"text": "trigger failure"},
        ) as response:
            assert response.status_code == 200
            events = self._consume_sse(response)

        error_events = [e for e in events if e.get("error") == "pipeline_failed"]
        assert len(error_events) == 1
        err = error_events[0]
        assert err["detail"] == "Pipeline exploded"
        assert "session_id" in err


# -------------------------------------------------------------------
# Corpus update endpoint tests
# -------------------------------------------------------------------


class TestCorpusUpdateEndpoint:
    """Tests for POST /api/v1/corpus/update."""

    @patch("app.api.routes.corpus._run_corpus_update")
    def test_corpus_update_returns_202_and_job_id(self, mock_bg_task, client: TestClient) -> None:
        """Endpoint accepts request and immediately returns a job identifier."""
        response = client.post("/api/v1/corpus/update")
        assert response.status_code == 202
        data = response.json()
        assert "job_id" in data
        assert data["status"] == "queued"
        mock_bg_task.assert_called_once()

    def test_corpus_update_background_task_failure_returns_500(self, client: TestClient) -> None:
        """If the background task cannot be scheduled, endpoint returns 500."""
        with patch("fastapi.BackgroundTasks.add_task", side_effect=RuntimeError("scheduler down")):
            response = client.post("/api/v1/corpus/update")
            assert response.status_code == 500
            body = response.json()
            assert "detail" in body
            assert "Failed to schedule" in body["detail"]
