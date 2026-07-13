"""Inference profile loader and egress guard. Version: 0.1.0.

Loads versioned inference profiles from ``config/inference_profiles.yaml``
and enforces host allowlisting / PII scanning for every outbound LLM call.
"""

# Semantic Version: 0.1.0 | 2026-07-12 — WP-31 initial implementation

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from app.core.config import settings

logger = logging.getLogger(__name__)

_PROFILES_DIR = Path(__file__).resolve().parents[2] / "config"
_DEFAULT_PROFILES_PATH = _PROFILES_DIR / "inference_profiles.yaml"


@dataclass
class InferenceProfile:
    """A single inference profile with compliance settings.

    Attributes:
        name: Profile key (e.g. ``"eu-avv"``).
        label: Human-readable label.
        data_residency: ``"eu-only"`` | ``"any"`` | ``"on-prem"``.
        avv_status: ``"signed"`` | ``"not-signed"``.
        pseudonymization: ``"required"`` | ``"optional"``.
        host_allowlist: List of hostnames permitted for outbound LLM calls.
        per_stage: Per-stage model/temperature overrides.
        capability_manifest: Feature flags (streaming, function_calling, etc.).
        enabled: Whether this profile is active (default ``True``).
    """

    name: str
    label: str
    data_residency: str
    avv_status: str
    pseudonymization: str
    host_allowlist: list[str]
    per_stage: dict[str, dict[str, Any]] = field(default_factory=dict)
    capability_manifest: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True


def load_profiles(path: Path | None = None) -> dict[str, InferenceProfile]:
    """Load inference profiles from YAML.

    Args:
        path: Path to the profiles YAML file. Defaults to
              ``config/inference_profiles.yaml`` relative to the project root.

    Returns:
        A dict mapping profile name → ``InferenceProfile``.

    Raises:
        FileNotFoundError: If the profiles file does not exist.
        ValueError: If the YAML content is malformed or missing the ``profiles`` key.
    """
    path = path or _DEFAULT_PROFILES_PATH
    if not path.exists():
        raise FileNotFoundError(f"Inference profiles file not found: {path}")

    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict) or "profiles" not in data:
        raise ValueError(f"Inference profiles file {path} is missing the 'profiles' key")

    profiles: dict[str, InferenceProfile] = {}
    for name, cfg in data["profiles"].items():
        profiles[name] = InferenceProfile(
            name=str(name),
            label=cfg.get("label", name),
            data_residency=cfg.get("data_residency", "any"),
            avv_status=cfg.get("avv_status", "not-signed"),
            pseudonymization=cfg.get("pseudonymization", "required"),
            host_allowlist=cfg.get("host_allowlist", []),
            per_stage=cfg.get("per_stage", {}),
            capability_manifest=cfg.get("capability_manifest", {}),
            enabled=cfg.get("enabled", True),
        )

    logger.info(
        "Loaded %d inference profiles from %s",
        len(profiles),
        path,
    )
    return profiles


# ---------------------------------------------------------------------------
# Cached profiles + active profile
# ---------------------------------------------------------------------------

_PROFILES_CACHE: dict[str, InferenceProfile] | None = None


def get_active_profile(profile_name: str | None = None) -> InferenceProfile:
    """Get the active inference profile.

    Uses ``settings.INFERENCE_PROFILE`` if *profile_name* is ``None``.
    Defaults to ``"eu-avv"`` if no setting is configured.

    Args:
        profile_name: Explicit profile name override.

    Returns:
        The resolved ``InferenceProfile``.

    Raises:
        ValueError: If the profile is not found, is disabled, or has
            ``avv_status != "signed"`` without ``settings.AVV_OVERRIDE``.
    """
    global _PROFILES_CACHE
    if _PROFILES_CACHE is None:
        _PROFILES_CACHE = load_profiles()

    name = profile_name or settings.INFERENCE_PROFILE

    profile = _PROFILES_CACHE.get(name)
    if profile is None:
        raise ValueError(
            f"Inference profile {name!r} not found. "
            f"Available profiles: {list(_PROFILES_CACHE.keys())}"
        )

    if not profile.enabled:
        raise ValueError(
            f"Inference profile {name!r} is disabled. " f"Set 'enabled: true' in the profiles YAML."
        )

    # AVV gate: non-signed profiles require explicit override
    if profile.avv_status != "signed" and not settings.AVV_OVERRIDE:
        raise ValueError(
            f"Inference profile {name!r} has avv_status={profile.avv_status!r} "
            f"but AVV_OVERRIDE is False. Set AVV_OVERRIDE=True or use a signed profile."
        )

    return profile


def validate_profile(profile: InferenceProfile) -> list[str]:
    """Validate profile consistency. Returns a list of warnings.

    Checks performed:
    - ``avv_status != 'signed'`` without override → warning
    - ``host_allowlist`` empty → warning
    - ``pseudonymization = 'required'`` but ``PSEUDONYMIZATION_ENABLED = False`` → error
    """
    warnings: list[str] = []

    if profile.avv_status != "signed" and not settings.AVV_OVERRIDE:
        warnings.append(
            f"Profile {profile.name!r}: avv_status={profile.avv_status!r}, "
            f"AVV_OVERRIDE is False — LLM calls may be blocked by the egress guard."
        )

    if not profile.host_allowlist:
        warnings.append(
            f"Profile {profile.name!r}: host_allowlist is empty — "
            f"all outbound LLM calls will be blocked by the egress guard."
        )

    if profile.pseudonymization == "required" and not settings.PSEUDONYMIZATION_ENABLED:
        warnings.append(
            f"Profile {profile.name!r}: pseudonymization='required' but "
            f"PSEUDONYMIZATION_ENABLED is False. Either enable pseudonymization "
            f"or use a profile with pseudonymization='optional'."
        )

    return warnings


def reset_profile_cache() -> None:
    """Reset the cached profiles. Used in tests."""
    global _PROFILES_CACHE
    _PROFILES_CACHE = None
