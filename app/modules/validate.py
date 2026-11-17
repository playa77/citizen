"""Module validator (WP-115 authoring kit; ARCHITECTURE.md § 2).

One function answers "would the core accept this module, and is it
reviewable?" for an in-tree module, a scaffolded candidate or an out-of-tree
package directory. It runs every check the registry and the content loaders
apply at startup, plus authoring discipline the startup path does not need:

errors (the module must not ship)
    manifest schema + declared files; ``core_api`` admits this core; module
    code imports only ``app.modules.sdk``; changelog/errata discipline
    (WP-110); deadline specs, parameter files, dossier content, prompt
    profile, document templates and plain-language copy load (WP-122: schema
    and duty of care); code references resolve to the SDK
    types; area keys fit the installed set (ownership, unique ``order``,
    synonyms, presets — the same assembly the core performs); own-matter
    scope (D-035); a ``verified`` module declares a goldset; compliance
    files are well-formed.
warnings (allowed, but a reviewer should look)
    unknown corpus source types; no goldset; no changelog-declared errata
    file; no disclaimer addendum; parameters still ``proposed``.

The CLI wrapper is ``python -m scripts.validate_module``.
"""

# Semantic Version: 1.1.0 | 2026-11-17 — WP-122: plain-language copy is validated
# (schema, duty of care); verified modules without copy get a warning.
# 1.0.0 | 2026-11-17 — WP-115: initial version.

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.modules.registry import (
    ModuleContractError,
    ModuleManifest,
    ModuleManifestError,
    _parse_manifest,
    assert_core_api_compatible,
    default_modules_root,
    discover_installed_modules,
)


@dataclass
class ValidationReport:
    """Findings for one module directory."""

    path: str
    module_id: str | None = None
    version: str | None = None
    tier: str | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "module_id": self.module_id,
            "version": self.version,
            "tier": self.tier,
            "ok": self.ok,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
        }


def _check(report: ValidationReport, label: str, fn: Any) -> Any:
    """Run one check; record any exception as an error and return ``None``."""
    try:
        return fn()
    except (ModuleManifestError, ModuleContractError, ValueError, KeyError, TypeError) as exc:
        report.errors.append(f"{label}: {exc}")
    except Exception as exc:  # importing module code may raise anything
        report.errors.append(f"{label}: {type(exc).__name__}: {exc}")
    return None


def _content_checks(manifest: ModuleManifest, report: ValidationReport) -> None:
    from app.fristen.specs import load_specs
    from app.modules.content import load_code_ref, load_section, module_path
    from app.modules.errata import check_versioning
    from app.modules.lint import lint_module_dir
    from app.modules.parameters import load_parameter_rows
    from app.modules.sdk import Calculator, RegimeProvider

    raw = manifest.raw
    report.errors.extend(lint_module_dir(manifest.path))
    report.errors.extend(check_versioning(manifest))

    if isinstance(raw.get("fristen"), str):
        _check(report, "fristen", lambda: load_specs(module_path(manifest, raw["fristen"])))
    rows = _check(report, "parameters", lambda: load_parameter_rows(manifest))
    if rows:
        proposed = [r.key for r in rows if r.review_status != "verified"]
        if proposed:
            report.warnings.append(
                f"parameters: {len(proposed)} row(s) not verified yet "
                f"(e.g. {proposed[0]}) — a parameter steward must review them"
            )
    if isinstance(raw.get("dossier"), str):
        from app.dossier.module_content import validate_module_dossier

        _check(
            report,
            "dossier",
            lambda: validate_module_dossier(
                load_section(manifest, "dossier"), context=f"module {manifest.id!r}"
            ),
        )
    plain_files = (
        raw.get("plain_language", {}).get("files", {})
        if isinstance(raw.get("plain_language"), dict)
        else {}
    )
    for language, rel in plain_files.items():
        # WP-122: schema + duty of care here; coverage and the plain goldset
        # need the installed registry → python -m eval.plain_eval.
        from app.modules.content import load_yaml
        from app.plain.checks import discouraging_hits, iter_texts
        from app.plain.copy import validate_copy

        doc = _check(report, f"plain_language.{language}", lambda rel=rel: load_yaml(manifest, rel))
        if doc is None:
            continue
        report.errors.extend(
            f"plain_language.{language}: {e}" for e in validate_copy(doc, manifest, language)
        )
        for path, text in iter_texts(doc):
            for hit in discouraging_hits(text):
                report.errors.append(
                    f"plain_language.{language}:{path}: discouraging phrase {hit!r}"
                )
    if manifest.tier == "verified" and not plain_files:
        report.warnings.append(
            "plain_language: a verified module should ship plain-language copy "
            "(de + en; de-LS for critical deadlines — roadmap WP-122)"
        )
    for key in ("prompts", "document_templates", "corpus", "intake"):
        data = _check(report, key, lambda key=key: load_section(manifest, key))
        if data is not None and not isinstance(data, dict):
            report.errors.append(f"{key}: file is not a YAML mapping")

    if isinstance(raw.get("calculators"), str):

        def _calculators() -> None:
            for item in load_code_ref(manifest, raw["calculators"]):
                if not isinstance(item, Calculator):
                    raise TypeError(f"{raw['calculators']} must contain sdk.Calculator instances")

        _check(report, "calculators", _calculators)
    regimes = raw.get("regimes")
    if isinstance(regimes, dict):

        def _regimes() -> None:
            if not isinstance(load_code_ref(manifest, regimes["provider"]), RegimeProvider):
                raise TypeError(f"{regimes['provider']} must be an sdk.RegimeProvider")

        _check(report, "regimes", _regimes)

    goldset = raw.get("goldset")
    if isinstance(goldset, dict):

        def _goldset() -> None:
            from app.modules.content import load_yaml

            doc = load_yaml(manifest, goldset["path"])
            if not isinstance(doc, dict) or not isinstance(doc.get("cases"), list):
                raise ValueError(f"{goldset['path']} needs a top-level `cases` list")

        _check(report, "goldset", _goldset)
    elif manifest.tier == "verified":
        report.errors.append("tier verified requires a goldset (roadmap § 7 definition of done)")
    else:
        report.warnings.append("no goldset declared — the module cannot be promoted to verified")

    compliance = raw.get("compliance") or {}
    deny = compliance.get("purpose_drift_deny_file")
    if isinstance(deny, str):

        def _deny() -> None:
            phrases = json.loads(module_path(manifest, deny).read_text(encoding="utf-8"))
            if not isinstance(phrases, list) or not all(isinstance(p, str) for p in phrases):
                raise ValueError(f"{deny} must be a JSON list of strings")

        _check(report, "compliance.purpose_drift_deny_file", _deny)
    addendum = compliance.get("disclaimer_addendum")
    if isinstance(addendum, str):
        text = module_path(manifest, addendum).read_text(encoding="utf-8")
        for heading in ("## DE", "## EN"):
            if heading not in text.splitlines():
                report.errors.append(f"{addendum}: missing `{heading}` section")
    else:
        report.warnings.append(
            "no disclaimer addendum — area-specific limits are not stated (ARCHITECTURE.md § 7)"
        )

    def _case_law() -> None:
        from app.services.case_law import parse_case_law_section

        specs = parse_case_law_section(manifest, load_section(manifest, "corpus"))
        if specs and manifest.tier != "verified":
            report.warnings.append(
                "corpus.yaml case_law is ignored until the module is tier verified (WP-113)"
            )

    _check(report, "corpus.yaml case_law", _case_law)
    if not isinstance(raw.get("errata"), str):
        report.warnings.append("no errata file declared (WP-110) — fine until the first erratum")

    scope = raw.get("scope")
    if not isinstance(scope, dict):
        report.errors.append("scope: missing — every module states its scope (D-035)")
    elif scope.get("own_matter_only") is not True:
        report.errors.append("scope.own_matter_only must be true (citizen-side purpose, D-035)")


def _corpus_source_warnings(manifest: ModuleManifest, report: ValidationReport) -> None:
    # The DB CHECK list, not the corpus service catalog: importing the
    # service needs a configured app, and the validator runs offline.
    from app.db.models import SOURCE_TYPE_ALLOWED
    from app.modules.content import load_section

    corpus = load_section(manifest, "corpus")
    if not isinstance(corpus, dict):
        return
    for key, entry in (corpus.get("areas") or {}).items():
        for source_type in (entry or {}).get("source_types") or ():
            if source_type not in SOURCE_TYPE_ALLOWED:
                report.warnings.append(
                    f"corpus: area {key!r} names source type {source_type!r} that the core "
                    "does not store (legal_source CHECK) — no retrieval until it is catalogued"
                )


def _default_module() -> str:
    """``DEFAULT_MODULE`` from the configuration, or its documented default.

    The validator runs offline (no ``.env``, no API key); an unconfigured
    process falls back to the environment variable, then the settings default.
    """
    import os

    try:
        from app.core.config import settings

        return settings.DEFAULT_MODULE
    except Exception:  # pydantic ValidationError without configuration
        from app.core.config import Settings

        default = str(Settings.model_fields["DEFAULT_MODULE"].default)
        return os.environ.get("DEFAULT_MODULE", default)


def _integration_check(
    manifest: ModuleManifest, report: ValidationReport, modules_root: Path
) -> None:
    """Assemble the area tables over the installed set plus this module."""
    from app.modules.areas import build_area_tables_from

    def _tables() -> None:
        installed, _rejected = discover_installed_modules(modules_root)
        installed = {
            mid: m
            for mid, m in installed.items()
            if mid != manifest.id and m.path.resolve() != manifest.path.resolve()
        }
        installed[manifest.id] = manifest
        default = _default_module()
        if default not in installed:
            default = manifest.id
        build_area_tables_from(installed, default)

    _check(report, "area keys (with the installed modules)", _tables)


def validate_module_dir(module_dir: Path, modules_root: Path | None = None) -> ValidationReport:
    """Validate the module in *module_dir* against this core and the installed set."""
    report = ValidationReport(path=str(module_dir))
    manifest = _check(report, "manifest", lambda: _parse_manifest(module_dir, module_dir.parent))
    if manifest is None:
        return report
    report.module_id, report.version, report.tier = manifest.id, manifest.version, manifest.tier
    _check(report, "core_api", lambda: assert_core_api_compatible(manifest))
    _content_checks(manifest, report)
    _check(report, "corpus", lambda: _corpus_source_warnings(manifest, report))
    _integration_check(manifest, report, modules_root or default_modules_root())
    return report


__all__ = ["ValidationReport", "validate_module_dir"]
