"""Unit tests for WP-31: Inference profile loading and AVV gate.

Covers
------
- ``app.services.inference_profiles.load_profiles`` — YAML parsing
- ``app.services.inference_profiles.get_active_profile`` — profile resolution
- AVV gate: non-signed profiles refused without override, allowed with override
- Disabled profile rejection
- ``validate_profile`` warnings
"""

# Semantic Version: 0.1.0 | 2026-07-12

from __future__ import annotations

from pathlib import Path

import pytest

import app.services.inference_profiles as _ip_mod
from app.services.inference_profiles import (
    InferenceProfile,
    get_active_profile,
    load_profiles,
    reset_profile_cache,
    validate_profile,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_PROFILES_YAML = Path(__file__).resolve().parents[2] / "config" / "inference_profiles.yaml"


@pytest.fixture(autouse=True)
def _reset_cache_and_settings() -> None:
    """Reset the profile cache and restore settings defaults before each test.

    Must modify the module-level ``settings`` object (the one used by
    ``get_active_profile`` and ``validate_profile``) instead of creating
    a new one via ``_get_settings()``, because import-time resolution in
    ``inference_profiles.py`` pins an old reference that becomes stale
    when ``_SETTINGS`` is destroyed by other test modules (e.g. test_config).
    """
    reset_profile_cache()
    _ip_mod.settings.INFERENCE_PROFILE = "eu-avv"
    _ip_mod.settings.AVV_OVERRIDE = False
    _ip_mod.settings.PSEUDONYMIZATION_ENABLED = True
    yield
    reset_profile_cache()


# ===========================================================================
# 1. Profile loading from YAML
# ===========================================================================


class TestProfileLoading:
    def test_loads_all_profiles(self) -> None:
        profiles = load_profiles(_PROFILES_YAML)
        assert "eu-avv" in profiles
        assert "extern-openrouter" in profiles
        assert "on-prem" in profiles

    def test_eu_avv_has_correct_defaults(self) -> None:
        profiles = load_profiles(_PROFILES_YAML)
        profile = profiles["eu-avv"]
        assert profile.label == "EU-AVV (Default — NGO Build)"
        assert profile.data_residency == "eu-only"
        assert profile.avv_status == "signed"
        assert profile.pseudonymization == "required"
        assert "openrouter.ai" in profile.host_allowlist
        assert profile.enabled is True

    def test_extern_openrouter_not_signed(self) -> None:
        profiles = load_profiles(_PROFILES_YAML)
        profile = profiles["extern-openrouter"]
        assert profile.avv_status == "not-signed"
        assert profile.enabled is True

    def test_on_prem_disabled(self) -> None:
        # WP-124: configured for a local runtime, still disabled until it
        # passes the goldset gate; only loopback hosts are allowed.
        profiles = load_profiles(_PROFILES_YAML)
        profile = profiles["on-prem"]
        assert profile.enabled is False
        assert set(profile.host_allowlist) <= {"127.0.0.1", "localhost", "::1"}
        assert profile.chat_endpoint is not None
        assert profile.chat_endpoint.startswith("http://127.0.0.1:")

    def test_chat_endpoint_defaults_to_openrouter(self) -> None:
        profiles = load_profiles(_PROFILES_YAML)
        assert profiles["eu-avv"].chat_endpoint is None
        assert profiles["extern-openrouter"].chat_endpoint is None

    def test_raises_on_missing_file(self) -> None:
        with pytest.raises(FileNotFoundError):
            load_profiles(Path("/nonexistent/profiles.yaml"))

    def test_config_file_loads_without_error(self) -> None:
        """The actual config file must load without exception."""
        profiles = load_profiles(_PROFILES_YAML)
        assert len(profiles) == 3


# ===========================================================================
# 2. get_active_profile
# ===========================================================================


class TestGetActiveProfile:
    def test_default_is_eu_avv(self) -> None:
        """Without explicit override, the default profile must be 'eu-avv'."""
        s = _ip_mod.settings
        s.INFERENCE_PROFILE = "eu-avv"
        s.AVV_OVERRIDE = False
        profile = get_active_profile()
        assert profile.name == "eu-avv"
        assert profile.avv_status == "signed"

    def test_explicit_profile_name(self) -> None:
        profile = get_active_profile("eu-avv")
        assert profile.name == "eu-avv"

    def test_raises_on_unknown_profile(self) -> None:
        with pytest.raises(ValueError, match="not found"):
            get_active_profile("nonexistent-profile")

    def test_raises_on_disabled_profile(self) -> None:
        with pytest.raises(ValueError, match="disabled"):
            get_active_profile("on-prem")

    def test_avv_gate_blocks_non_signed(self) -> None:
        """Non-signed profile must raise without AVV_OVERRIDE."""
        s = _ip_mod.settings
        s.AVV_OVERRIDE = False
        with pytest.raises(ValueError, match="avv_status"):
            get_active_profile("extern-openrouter")

    def test_avv_gate_allows_with_override(self) -> None:
        """Non-signed profile must be allowed with AVV_OVERRIDE=True."""
        s = _ip_mod.settings
        s.AVV_OVERRIDE = True
        profile = get_active_profile("extern-openrouter")
        assert profile.name == "extern-openrouter"
        assert profile.avv_status == "not-signed"

    def test_avv_gate_eu_avv_allows_without_override(self) -> None:
        """Signed profile eu-avv must pass even without AVV_OVERRIDE."""
        s = _ip_mod.settings
        s.AVV_OVERRIDE = False
        profile = get_active_profile("eu-avv")
        assert profile.name == "eu-avv"


# ===========================================================================
# 3. validate_profile warnings
# ===========================================================================


class TestValidateProfile:
    def test_eu_avv_no_warnings(self) -> None:
        s = _ip_mod.settings
        s.PSEUDONYMIZATION_ENABLED = True
        s.AVV_OVERRIDE = False
        profile = get_active_profile("eu-avv")
        warnings = validate_profile(profile)
        assert warnings == []

    def test_empty_host_allowlist_warning(self) -> None:
        profile = InferenceProfile(
            name="test",
            label="Test",
            data_residency="any",
            avv_status="signed",
            pseudonymization="optional",
            host_allowlist=[],
        )
        warnings = validate_profile(profile)
        assert any("host_allowlist is empty" in w for w in warnings)

    def test_non_signed_warning(self) -> None:
        s = _ip_mod.settings
        s.AVV_OVERRIDE = False
        profile = InferenceProfile(
            name="test",
            label="Test",
            data_residency="any",
            avv_status="not-signed",
            pseudonymization="optional",
            host_allowlist=["example.com"],
        )
        warnings = validate_profile(profile)
        assert any("avv_status" in w for w in warnings)

    def test_pseudonymization_required_but_disabled(self) -> None:
        s = _ip_mod.settings
        s.PSEUDONYMIZATION_ENABLED = False
        profile = InferenceProfile(
            name="test",
            label="Test",
            data_residency="any",
            avv_status="signed",
            pseudonymization="required",
            host_allowlist=["example.com"],
        )
        warnings = validate_profile(profile)
        assert any("pseudonymization" in w for w in warnings)


# ===========================================================================
# 4. InferenceProfile dataclass
# ===========================================================================


class TestProfileDataclass:
    def test_default_enabled(self) -> None:
        profile = InferenceProfile(
            name="test",
            label="Test",
            data_residency="any",
            avv_status="signed",
            pseudonymization="optional",
            host_allowlist=["example.com"],
        )
        assert profile.enabled is True
        assert profile.per_stage == {}
        assert profile.capability_manifest == {}

    def test_all_fields(self) -> None:
        profile = InferenceProfile(
            name="custom",
            label="Custom Profile",
            data_residency="eu-only",
            avv_status="signed",
            pseudonymization="required",
            host_allowlist=["openrouter.ai"],
            per_stage={"classification": {"model": "gpt-4", "temperature": 0.0}},
            capability_manifest={"streaming": True, "max_tokens": 128000},
            enabled=True,
        )
        assert profile.name == "custom"
        assert profile.per_stage["classification"]["model"] == "gpt-4"
        assert profile.capability_manifest["streaming"] is True


# ===========================================================================
# WP-124: chat endpoint follows the active profile
# ===========================================================================


def test_router_chat_url_follows_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    from dataclasses import replace

    import app.core.router as router_mod

    local = replace(
        load_profiles(_PROFILES_YAML)["on-prem"],
        enabled=True,
        chat_endpoint="http://127.0.0.1:8080/v1/chat/completions",
    )
    monkeypatch.setattr(_ip_mod, "get_active_profile", lambda name=None: local)
    assert router_mod._chat_url() == "http://127.0.0.1:8080/v1/chat/completions"
    # The egress guard checks the same URL against the profile allowlist.
    router_mod._egress_check(router_mod._chat_url(), {"messages": []})

    remote = replace(load_profiles(_PROFILES_YAML)["eu-avv"])
    monkeypatch.setattr(_ip_mod, "get_active_profile", lambda name=None: remote)
    assert router_mod._chat_url() == router_mod._API_URL
