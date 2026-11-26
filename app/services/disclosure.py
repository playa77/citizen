"""Art. 50 EU AI Act disclosure and provenance objects (D-032).

Regulation (EU) 2024/1689, Article 50 imposes two transparency duties once the
service operates as an AI system whose output reaches natural persons:

- Art. 50(1): every natural person must be informed, at first exposure, that
  they are dealing with AI-generated content. Consuming clients MUST display
  :attr:`DisclosureInfo.texts` to the person before presenting any
  AI-generated result — hence ``must_display_before = "results"``.
- Art. 50(2): AI-generated text must carry a machine-readable marker that it
  was artificially generated. :class:`ProvenanceMarker` is that marker.

All consumers are thin clients or agentic systems; the objects are therefore
embedded directly in every API response carrying AI-generated text (analyze
SSE terminal event, conversation chat ``done`` event, generated documents), so
each consumer receives what it must display/persist regardless of whether it
is human-operated. The disclaimer system (``X-Disclaimer-Ack``,
``/meta/disclaimer/*``) is separate and covers no-legal-advice framing only —
it is intentionally untouched here.

Since ``citizen-provenance-v1.1`` (WP-96) the marker also names the legal-area
modules that produced the content (``modules[{id, version, parameter_set}]``,
ARCHITECTURE.md § 5/§ 6.3) — additive to v1.0 — and the two surfaces D-032
left uncovered (conversation first-message pipeline terminal event, case-chat
``done``) carry both objects too (C-4 closed, D-059).

No database call, no LLM call. Module entries come from the module registry's
data; a module's parameter files are read once per process and cached
(``app.modules.runtime.module_provenance``), and startup warms that cache.
Disclosure texts are canonical constants; a text change requires a
``DISCLOSURE_VERSION`` bump and must never happen silently.
"""

# Semantic Version: 1.1.0 | 2026-11-16 — WP-96: citizen-provenance-v1.1
# (`modules` list), legal_areas parameter on build_disclosure_and_provenance.
# 1.0.0 | 2026-08-25 — D-032 initial.

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.core.config import Settings, get_app_version

logger = logging.getLogger(__name__)

# Version of the disclosure text below (Art. 50(1) notification). Bump on any
# wording change — consumers cache this endpoint's payload keyed by version.
DISCLOSURE_VERSION = "1.0"
# Marker schema identifier for the provenance object (Art. 50(2)).
# v1.1 (WP-96) adds `modules`; every v1.0 field is unchanged.
PROVENANCE_SPEC_VERSION = "citizen-provenance-v1.1"
# Generator identifier embedded in every provenance marker.
DISCLOSURE_GENERATOR = "citizen"
# Fallback substituted for any provenance field that cannot be determined.
# A missing field must never break a response carrying AI-generated content.
_PROVENANCE_FALLBACK = "unknown"

# Canonical Art. 50(1) notification strings. Consuming clients must display
# one of these (language-appropriate) before presenting results to the person.
DISCLOSURE_TEXT_DE = (
    "Diese Analyse wurde von einem KI-System erstellt "
    "(Art. 50 VO (EU) 2024/1689).\n"
    "Ergebnisse sind nicht rechtsverbindlich und müssen vor Verwendung "
    "geprüft werden."
)
DISCLOSURE_TEXT_EN = (
    "This analysis was produced by an AI system "
    "(Art. 50 of Regulation (EU) 2024/1689).\n"
    "Outputs are not legally binding and must be verified before use."
)


class DisclosureInfo(BaseModel):
    """Versioned AI-system notification for Art. 50(1) EU AI Act.

    Consuming clients MUST display ``texts[lang]`` to the natural person
    before presenting any AI-generated result or document.
    """

    version: str
    must_display_before: str
    texts: dict[str, str]


class ModuleProvenance(BaseModel):
    """One legal-area module that produced the content (provenance v1.1).

    ``parameter_set`` pins the module's versioned legal parameters
    (``"<module version>+<latest valid_from>"``, ARCHITECTURE.md § 6.3);
    ``None`` for a module without parameters.
    """

    id: str
    version: str
    parameter_set: str | None


class ProvenanceMarker(BaseModel):
    """Machine-readable marker for AI-generated output per Art. 50(2) EU AI Act.

    Embedded in every response carrying AI-generated text so downstream
    systems can persist/propagate provenance alongside the content.
    """

    # `model_profile` is the field name mandated by the marker spec; disable
    # pydantic's default "model_" protected namespace rather than rename it.
    model_config = ConfigDict(protected_namespaces=())

    spec_version: str
    generator: str
    app_version: str
    model_profile: str
    timestamp_utc: str
    deployment_mode: str
    # v1.1: modules in request order; [] when only the core procedural
    # library served the request (e.g. legal_areas=["verwaltungsrecht"]).
    modules: list[ModuleProvenance]


def _utc_now_iso() -> str:
    """Return the current UTC time as ISO 8601 with second precision.

    Factored out so tests can freeze the clock and prove identical provenance
    across surfaces for the same request.
    """
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _field_or_fallback(field_name: str, extractor: Callable[[], Any]) -> str:
    """Extract a provenance field, substituting a safe fallback on failure.

    The helper contract is "must not raise": a partially broken settings
    object degrades the marker's diagnostic value but never breaks the
    response that carries it.
    """
    try:
        value = extractor()
        if not isinstance(value, str) or not value:
            raise ValueError(f"non-string or empty value: {value!r}")
        return value
    except Exception as exc:
        logger.warning(
            "Provenance field %r unavailable (%s: %s) — using fallback %r",
            field_name,
            type(exc).__name__,
            exc,
            _PROVENANCE_FALLBACK,
        )
        return _PROVENANCE_FALLBACK


def _modules_or_fallback(legal_areas: Sequence[str] | None) -> list[ModuleProvenance]:
    """Resolve the provenance ``modules`` list; never raises.

    A module whose entry cannot be built is kept with ``"unknown"`` fields
    (its id is still diagnostic); if the area keys cannot be resolved at all,
    a single all-unknown entry is returned rather than ``[]`` — an empty list
    has a meaning of its own (procedural-only request).
    """
    try:
        from app.modules.runtime import module_provenance, provenance_modules

        module_ids = provenance_modules(legal_areas)
    except Exception as exc:
        logger.warning(
            "Provenance modules unresolvable for %r (%s: %s) — using fallback",
            legal_areas,
            type(exc).__name__,
            exc,
        )
        return [
            ModuleProvenance(
                id=_PROVENANCE_FALLBACK,
                version=_PROVENANCE_FALLBACK,
                parameter_set=_PROVENANCE_FALLBACK,
            )
        ]
    entries: list[ModuleProvenance] = []
    for module_id in module_ids:
        try:
            mid, version, parameter_set = module_provenance(module_id)
            entries.append(ModuleProvenance(id=mid, version=version, parameter_set=parameter_set))
        except Exception as exc:
            logger.warning(
                "Provenance entry for module %r unavailable (%s: %s) — using fallback",
                module_id,
                type(exc).__name__,
                exc,
            )
            entries.append(
                ModuleProvenance(
                    id=module_id,
                    version=_PROVENANCE_FALLBACK,
                    parameter_set=_PROVENANCE_FALLBACK,
                )
            )
    return entries


def build_disclosure() -> DisclosureInfo:
    """Build the Art. 50(1) disclosure object from canonical constants."""
    return DisclosureInfo(
        version=DISCLOSURE_VERSION,
        must_display_before="results",
        texts={"de": DISCLOSURE_TEXT_DE, "en": DISCLOSURE_TEXT_EN},
    )


def build_disclosure_and_provenance(
    settings: Settings,
    legal_areas: Sequence[str] | None = None,
) -> tuple[DisclosureInfo, ProvenanceMarker]:
    """Build the Art. 50 disclosure and provenance objects from application state.

    Called once per response that carries AI-generated content, with the area
    keys the content was produced for (``None``/empty → no legal module,
    the same rule the engines follow). No DB or LLM calls. This function must
    not raise: if any field cannot be determined (e.g. app version
    unavailable), a safe fallback string is substituted and a warning logged —
    never let a missing provenance field break a response.
    """
    disclosure = build_disclosure()
    # Attribute access on the lazy settings proxy; a broken or partial
    # settings object raises inside the extractor and lands in the fallback
    # path instead of propagating.
    provenance = ProvenanceMarker(
        spec_version=PROVENANCE_SPEC_VERSION,
        generator=DISCLOSURE_GENERATOR,
        app_version=_field_or_fallback("app_version", get_app_version),
        model_profile=_field_or_fallback("model_profile", lambda: settings.INFERENCE_PROFILE),
        timestamp_utc=_field_or_fallback("timestamp_utc", _utc_now_iso),
        deployment_mode=_field_or_fallback("deployment_mode", lambda: settings.DEPLOYMENT_MODE),
        modules=_modules_or_fallback(legal_areas),
    )
    return disclosure, provenance
