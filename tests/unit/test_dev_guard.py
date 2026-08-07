"""Unit tests for WP-62 — Dev-instance Art. 2(8) hardening guards.

Covers ``app.services.dev_guard`` (startup assertion + ingest guard), the
default deployment posture in ``app.core.config.Settings``, and the
route-level enforcement on ``POST /api/v1/ingest``.
"""

# Semantic Version: 1.0.0 | 2026-08-07

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.core.config import get_app_version_tag
from app.main import app
from app.services import dev_guard


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_settings(**overrides) -> SimpleNamespace:
    """Build a lightweight settings stub for the dev guard module."""
    base = {
        "DEPLOYMENT_MODE": "dev",
        "CITIZEN_SYNTHETIC_DATA_ONLY": False,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _make_request(headers: dict[str, str] | None = None, path: str = "/api/v1/ingest"):
    """Build a minimal request shim exposing headers and url.path."""
    return SimpleNamespace(
        headers=headers or {},
        url=SimpleNamespace(path=path),
    )


@pytest.fixture
def patch_dev_settings(monkeypatch):
    """Monkeypatch ``dev_guard._get_settings`` with a stub settings object."""

    def apply(**overrides) -> SimpleNamespace:
        stub = _make_settings(**overrides)
        monkeypatch.setattr(dev_guard, "_get_settings", lambda: stub)
        return stub

    return apply


# ---------------------------------------------------------------------------
# Startup assertion
# ---------------------------------------------------------------------------


class TestStartupAssertion:
    def test_raises_in_dev_without_flag(self, patch_dev_settings) -> None:
        patch_dev_settings(DEPLOYMENT_MODE="dev", CITIZEN_SYNTHETIC_DATA_ONLY=False)
        with pytest.raises(dev_guard.DevGuardError) as exc_info:
            dev_guard.check_dev_synthetic_data_startup()
        assert "CITIZEN_SYNTHETIC_DATA_ONLY" in str(exc_info.value)

    def test_passes_in_dev_with_flag(self, patch_dev_settings) -> None:
        patch_dev_settings(DEPLOYMENT_MODE="dev", CITIZEN_SYNTHETIC_DATA_ONLY=True)
        dev_guard.check_dev_synthetic_data_startup()  # must not raise

    def test_passes_in_self_without_flag(self, patch_dev_settings) -> None:
        patch_dev_settings(DEPLOYMENT_MODE="self", CITIZEN_SYNTHETIC_DATA_ONLY=False)
        dev_guard.check_dev_synthetic_data_startup()  # must not raise

    def test_passes_in_provider_without_flag(self, patch_dev_settings) -> None:
        patch_dev_settings(DEPLOYMENT_MODE="provider", CITIZEN_SYNTHETIC_DATA_ONLY=False)
        dev_guard.check_dev_synthetic_data_startup()  # must not raise


# ---------------------------------------------------------------------------
# Ingest guard
# ---------------------------------------------------------------------------


class TestIngestGuard:
    def test_passes_with_synthetic_tag(self, patch_dev_settings) -> None:
        patch_dev_settings(DEPLOYMENT_MODE="dev", CITIZEN_SYNTHETIC_DATA_ONLY=True)
        req = _make_request({"X-Document-Tag": "synthetic"})
        dev_guard.check_synthetic_data_request(req)  # must not raise

    def test_passes_with_goldset_tag(self, patch_dev_settings) -> None:
        patch_dev_settings(DEPLOYMENT_MODE="dev", CITIZEN_SYNTHETIC_DATA_ONLY=True)
        req = _make_request({"X-Document-Tag": "goldset"})
        dev_guard.check_synthetic_data_request(req)  # must not raise

    def test_rejects_missing_tag(self, patch_dev_settings) -> None:
        patch_dev_settings(DEPLOYMENT_MODE="dev", CITIZEN_SYNTHETIC_DATA_ONLY=True)
        req = _make_request({})
        with pytest.raises(HTTPException) as exc_info:
            dev_guard.check_synthetic_data_request(req)
        assert exc_info.value.status_code == 403
        assert exc_info.value.detail["error"] == "synthetic_data_only"

    def test_rejects_invalid_tag(self, patch_dev_settings) -> None:
        patch_dev_settings(DEPLOYMENT_MODE="dev", CITIZEN_SYNTHETIC_DATA_ONLY=True)
        req = _make_request({"X-Document-Tag": "real"})
        with pytest.raises(HTTPException) as exc_info:
            dev_guard.check_synthetic_data_request(req)
        assert exc_info.value.status_code == 403

    def test_uppercase_tag_is_normalized(self, patch_dev_settings) -> None:
        """Tags are compared case-insensitively."""
        patch_dev_settings(DEPLOYMENT_MODE="dev", CITIZEN_SYNTHETIC_DATA_ONLY=True)
        req = _make_request({"X-Document-Tag": "SYNTHETIC"})
        dev_guard.check_synthetic_data_request(req)  # must not raise

    def test_skips_outside_dev_mode(self, patch_dev_settings) -> None:
        patch_dev_settings(DEPLOYMENT_MODE="self", CITIZEN_SYNTHETIC_DATA_ONLY=True)
        req = _make_request({})
        dev_guard.check_synthetic_data_request(req)  # must not raise

    def test_skips_when_flag_off(self, patch_dev_settings) -> None:
        patch_dev_settings(DEPLOYMENT_MODE="dev", CITIZEN_SYNTHETIC_DATA_ONLY=False)
        req = _make_request({})
        dev_guard.check_synthetic_data_request(req)  # must not raise


# ---------------------------------------------------------------------------
# Config defaults
# ---------------------------------------------------------------------------


class TestConfigDefaults:
    def test_default_deployment_mode_is_dev(self, monkeypatch) -> None:
        monkeypatch.delenv("DEPLOYMENT_MODE", raising=False)
        monkeypatch.delenv("CITIZEN_SYNTHETIC_DATA_ONLY", raising=False)

        from app.core.config import Settings

        s = Settings()
        assert s.DEPLOYMENT_MODE == "dev"
        assert s.CITIZEN_SYNTHETIC_DATA_ONLY is False

    def test_settings_accept_explicit_values(self, monkeypatch) -> None:
        monkeypatch.setenv("DEPLOYMENT_MODE", "dev")
        monkeypatch.setenv("CITIZEN_SYNTHETIC_DATA_ONLY", "true")

        from app.core.config import Settings

        s = Settings()
        assert s.DEPLOYMENT_MODE == "dev"
        assert s.CITIZEN_SYNTHETIC_DATA_ONLY is True

    def test_invalid_mode_is_rejected(self, monkeypatch) -> None:
        monkeypatch.setenv("DEPLOYMENT_MODE", "invalid-mode")
        monkeypatch.setenv("CITIZEN_SYNTHETIC_DATA_ONLY", "false")

        from pydantic import ValidationError

        from app.core.config import Settings

        with pytest.raises(ValidationError):
            Settings()


# ---------------------------------------------------------------------------
# Route-level enforcement (POST /api/v1/ingest)
# ---------------------------------------------------------------------------


class TestIngestEndpointGuard:
    def test_ingest_rejects_untagged_upload(self, monkeypatch) -> None:
        # Force the dev posture regardless of environment.
        monkeypatch.setattr(
            dev_guard,
            "_get_settings",
            lambda: _make_settings(DEPLOYMENT_MODE="dev", CITIZEN_SYNTHETIC_DATA_ONLY=True),
        )
        client = TestClient(app)
        response = client.post(
            "/api/v1/ingest",
            files={"file": ("real.pdf", b"%PDF-1.4", "application/pdf")},
            headers={"X-Disclaimer-Ack": get_app_version_tag()},
        )
        assert response.status_code == 403
        data = response.json()
        assert data["detail"]["error"] == "synthetic_data_only"

    def test_ingest_passes_with_synthetic_tag(self, monkeypatch) -> None:
        monkeypatch.setattr(
            dev_guard,
            "_get_settings",
            lambda: _make_settings(DEPLOYMENT_MODE="dev", CITIZEN_SYNTHETIC_DATA_ONLY=True),
        )
        client = TestClient(app)
        response = client.post(
            "/api/v1/ingest",
            files={"file": ("synthetic.pdf", b"%PDF-1.4", "application/pdf")},
            headers={
                "X-Disclaimer-Ack": get_app_version_tag(),
                "X-Document-Tag": "synthetic",
            },
        )
        # Guard passes → request proceeds to OCR and fails there (expected);
        # the critical assertion is that it is NOT a 403 from the dev guard.
        assert response.status_code != 403
