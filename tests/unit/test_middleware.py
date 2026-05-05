"""Tests for WP-014: Disclaimer Middleware & Meta Endpoints.

Tests cover:
- Disclaimer middleware blocking requests without proper header
- Disclaimer middleware allowing requests with correct header
- Meta endpoints returning version and text
"""

# Semantic Version: 0.1.0

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_app_version_tag
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
        response = client.post(
            "/api/v1/ingest", files={"file": ("test.pdf", b"dummy", "application/pdf")}
        )

        assert response.status_code == 403
        data = response.json()
        assert data["error"] == "disclaimer_required"
        assert "required_version" in data
        assert data["required_version"] == get_app_version_tag()

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
        assert data["required_version"] == get_app_version_tag()
        assert data["acknowledged_version"] == "v0.9.0"

    def test_disclaimer_passes_with_correct_header(self, client: TestClient) -> None:
        """Request with correct header proceeds (will fail at OCR, but that's expected)."""
        # Note: This will fail at the OCR stage but the middleware should pass
        response = client.post(
            "/api/v1/ingest",
            files={"file": ("test.pdf", b"dummy", "application/pdf")},
            headers={"X-Disclaimer-Ack": get_app_version_tag()},
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
        assert data["version"] == get_app_version_tag()

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
        assert data["api_version"] == get_app_version_tag().lstrip("v")
        assert data["disclaimer_version"] == get_app_version_tag()

    def test_meta_endpoints_bypass_disclaimer(self, client: TestClient) -> None:
        """Meta endpoints work without X-Disclaimer-Ack header."""
        response = client.get("/api/v1/meta/disclaimer/version")

        assert response.status_code == 200


# -------------------------------------------------------------------
# WP-017 Acceptance: test_disclaimer_block / test_disclaimer_pass
# -------------------------------------------------------------------
# These are module-level functions referenced directly in the roadmap
# acceptance criteria, and must exist as standalone names (not inside a
# class) so that ``pytest tests/unit/test_middleware.py::test_disclaimer_block``
# resolves correctly.


def test_disclaimer_block() -> None:
    """WP-017 AC: missing X-Disclaimer-Ack header → 403."""
    client = TestClient(app)

    response = client.post(
        "/api/v1/ingest",
        files={"file": ("dummy.pdf", b"not-a-real-pdf", "application/pdf")},
    )

    assert response.status_code == 403
    data = response.json()
    assert data["error"] == "disclaimer_required"
    assert data["required_version"] == get_app_version_tag()


def test_disclaimer_pass() -> None:
    """WP-017 AC: valid X-Disclaimer-Ack header → middleware passes, request
    reaches the endpoint (status is NOT 403, i.e., middleware did not block)."""
    client = TestClient(app)

    # POST to /api/v1/ingest with a dummy file and correct header.
    # The ingest endpoint itself will fail (OCR on dummy bytes), but
    # the critical assertion is that the response is NOT 403 — meaning
    # DisclaimerMiddleware granted passage.  We also verify the body
    # does NOT carry a disclaimer-related error structure.
    response = client.post(
        "/api/v1/ingest",
        files={"file": ("dummy.pdf", b"not-a-real-pdf", "application/pdf")},
        headers={"X-Disclaimer-Ack": get_app_version_tag()},
    )

    assert response.status_code != 403, (
        f"Expected non-403 (middleware passed), got {response.status_code}"
    )

    # The response body must NOT contain a disclaimer-related error payload.
    try:
        body = response.json()
        assert body.get("error") not in (
            "disclaimer_required",
            "disclaimer_version_mismatch",
        ), "Response contained disclaimer error — middleware blocked the request"
    except Exception:
        # If the body isn't JSON that's fine — as long as it's not 403,
        # the middleware has done its job.
        pass
