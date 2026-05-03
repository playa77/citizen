"""Tests for WP-014: Disclaimer Middleware & Meta Endpoints.

Tests cover:
- Disclaimer middleware blocking requests without proper header
- Disclaimer middleware allowing requests with correct header
- Meta endpoints returning version and text
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app


# -------------------------------------------------------------------
# TestClient fixture
# -------------------------------------------------------------------


@pytest.fixture
def client() -> TestClient:
    """Return a synchronous TestClient for the FastAPI app."""
    return TestClient(app)


# -------------------------------------------------------------------
# Disclaimer Middleware Tests
# -------------------------------------------------------------------


class TestDisclaimerMiddleware:
    """Tests for the disclaimer middleware enforcement."""

    def test_disclaimer_required_without_header(self, client: TestClient) -> None:
        """Request without X-Disclaimer-Ack header returns 403."""
        response = client.post("/api/v1/ingest", files={"file": ("test.pdf", b"dummy", "application/pdf")})

        assert response.status_code == 403
        data = response.json()
        assert data["error"] == "disclaimer_required"
        assert "required_version" in data
        assert data["required_version"] == "v1.0.0"

    def test_disclaimer_wrong_version(self, client: TestClient) -> None:
        """Request with wrong version returns 403 with version mismatch."""
        response = client.post(
            "/api/v1/ingest",
            files={"file": ("test.pdf", b"dummy", "application/pdf")},
            headers={"X-Disclaimer-Ack": "v0.9.0"},
        )

        assert response.status_code == 403
        data = response.json()
        assert data["error"] == "disclaimer_version_mismatch"
        assert data["required_version"] == "v1.0.0"
        assert data["acknowledged_version"] == "v0.9.0"

    def test_disclaimer_passes_with_correct_header(self, client: TestClient) -> None:
        """Request with correct header proceeds (will fail at OCR, but that's expected)."""
        # Note: This will fail at the OCR stage but the middleware should pass
        response = client.post(
            "/api/v1/ingest",
            files={"file": ("test.pdf", b"dummy", "application/pdf")},
            headers={"X-Disclaimer-Ack": "v1.0.0"},
        )

        # Should NOT be 403 from middleware - could be 400 from OCR or other
        assert response.status_code != 403

    def test_health_endpoint_bypasses_disclaimer(self, client: TestClient) -> None:
        """Health endpoint works without disclaimer header."""
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    def test_static_files_bypass_disclaimer(self, client: TestClient) -> None:
        """Static file requests bypass disclaimer check."""
        response = client.get("/static/style.css")

        # Could be 200 or 404 depending on file existence
        # But should NOT be 403 from middleware
        assert response.status_code != 403


# -------------------------------------------------------------------
# Meta Endpoints Tests
# -------------------------------------------------------------------


class TestMetaEndpoints:
    """Tests for the /api/v1/meta/* endpoints."""

    def test_disclaimer_version_endpoint(self, client: TestClient) -> None:
        """GET /api/v1/meta/disclaimer/version returns current version."""
        response = client.get("/api/v1/meta/disclaimer/version")

        assert response.status_code == 200
        data = response.json()
        assert data["version"] == "v1.0.0"

    def test_disclaimer_text_endpoint(self, client: TestClient) -> None:
        """GET /api/v1/meta/disclaimer/text returns disclaimer text."""
        response = client.get("/api/v1/meta/disclaimer/text")

        assert response.status_code == 200
        data = response.json()
        assert "text" in data
        assert "version" in data
        assert "Haftungsausschluss" in data["text"] or "Rechtlicher Hinweis" in data["text"]

    def test_api_version_endpoint(self, client: TestClient) -> None:
        """GET /api/v1/meta/version returns API and disclaimer versions."""
        response = client.get("/api/v1/meta/version")

        assert response.status_code == 200
        data = response.json()
        assert data["api_version"] == "1.0.0"
        assert data["disclaimer_version"] == "v1.0.0"

    def test_meta_endpoints_bypass_disclaimer(self, client: TestClient) -> None:
        """Meta endpoints work without X-Disclaimer-Ack header."""
        response = client.get("/api/v1/meta/disclaimer/version")

        assert response.status_code == 200
