"""Module errata and changelog discipline (WP-110; ARCHITECTURE.md § 6.2).

A module PATCH that corrects a wrong parameter value, deadline or copy is
also an **erratum**: the module declares it in the file named by the
manifest key ``errata`` (format ``citizen-module-errata-v1.0``, schema
``errata.schema.json``). ``GET /api/v1/modules/{id}`` serves the entries and
``GET /api/v1/modules/{id}/errata/{erratum_id}/cases`` lists the stored cases
whose recorded ``module_version`` lies in the erratum's ``affected_versions``.

The changelog rules checked here (and by the module validator, WP-115):

* ``CHANGELOG.md`` exists and its version headings (``## X.Y.Z …``) are
  strictly descending, the first one equal to the manifest version;
* every erratum's ``fixed_in`` is a released changelog version not newer than
  the manifest, and ``fixed_in`` itself is outside ``affected_versions``.
"""

# Semantic Version: 1.0.0 | 2026-11-17 — WP-110: initial version.

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from itertools import pairwise
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from app.modules.content import load_section, module_path
from app.modules.registry import ModuleManifest, ModuleManifestError
from app.modules.semver import VersionRangeError, in_range, parse_version

ERRATA_FORMAT = "citizen-module-errata-v1.0"
ERRATA_SCHEMA_PATH = Path(__file__).with_name("errata.schema.json")

_CHANGELOG_HEADING = re.compile(r"^##\s+(\d+\.\d+\.\d+)\b", re.MULTILINE)


@dataclass(frozen=True)
class Erratum:
    id: str
    published: str
    affected_versions: str
    fixed_in: str
    severity: str
    component: str
    summary_de: str
    summary_en: str
    action_de: str
    action_en: str | None
    core_versions: str | None
    references: tuple[str, ...]

    def affects(self, module_version: str | None) -> bool:
        """Whether a case recorded with *module_version* is affected."""
        if not module_version:
            return False
        try:
            return in_range(module_version, self.affected_versions)
        except VersionRangeError:
            return False  # a malformed stored version cannot be attributed

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "published": self.published,
            "affected_versions": self.affected_versions,
            "fixed_in": self.fixed_in,
            "severity": self.severity,
            "component": self.component,
            "summary_de": self.summary_de,
            "summary_en": self.summary_en,
            "action_de": self.action_de,
            "action_en": self.action_en,
            "core_versions": self.core_versions,
            "references": list(self.references),
        }


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    schema = json.loads(ERRATA_SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _dates_to_iso(value: Any) -> Any:
    """YAML parses ``2026-11-17`` as a date; the schema speaks ISO strings."""
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _dates_to_iso(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_dates_to_iso(v) for v in value]
    return value


def parse_errata(data: Any, where: str) -> tuple[Erratum, ...]:
    """Validate an errata document; raise ``ModuleManifestError`` on any defect."""
    data = _dates_to_iso(data)
    errors = sorted(_validator().iter_errors(data), key=lambda e: list(e.path))
    if errors:
        details = "; ".join(
            f"{'/'.join(str(p) for p in e.path) or '<root>'}: {e.message}" for e in errors
        )
        raise ModuleManifestError(f"{where}: invalid errata file: {details}")
    entries: list[Erratum] = []
    seen: set[str] = set()
    for raw in data["errata"]:
        if raw["id"] in seen:
            raise ModuleManifestError(f"{where}: duplicate erratum id {raw['id']!r}")
        seen.add(raw["id"])
        try:
            parse_version(raw["fixed_in"])
            if in_range(raw["fixed_in"], raw["affected_versions"]):
                raise ModuleManifestError(
                    f"{where}: {raw['id']}: fixed_in {raw['fixed_in']} lies inside "
                    f"affected_versions {raw['affected_versions']!r}"
                )
            if raw.get("core_versions"):
                in_range("0.0.0", raw["core_versions"])  # parse check only
        except VersionRangeError as exc:
            raise ModuleManifestError(f"{where}: {raw['id']}: {exc}") from exc
        entries.append(
            Erratum(
                id=raw["id"],
                published=str(raw["published"]),
                affected_versions=raw["affected_versions"],
                fixed_in=raw["fixed_in"],
                severity=raw["severity"],
                component=raw["component"],
                summary_de=raw["summary_de"],
                summary_en=raw["summary_en"],
                action_de=raw["action_de"],
                action_en=raw.get("action_en"),
                core_versions=raw.get("core_versions"),
                references=tuple(raw.get("references") or ()),
            )
        )
    return tuple(entries)


def module_errata(manifest: ModuleManifest) -> tuple[Erratum, ...]:
    """Errata a module declares (``()`` when it declares no errata file)."""
    data = load_section(manifest, "errata")
    if data is None:
        return ()
    errata = parse_errata(data, f"module {manifest.id!r}")
    for erratum in errata:
        if parse_version(erratum.fixed_in) > parse_version(manifest.version):
            raise ModuleManifestError(
                f"module {manifest.id!r}: erratum {erratum.id} is fixed in "
                f"{erratum.fixed_in}, newer than the module version {manifest.version}"
            )
    return errata


def changelog_versions(manifest: ModuleManifest) -> list[str]:
    """Version headings of the module ``CHANGELOG.md``, in file order."""
    path = module_path(manifest, "CHANGELOG.md")
    if not path.is_file():
        raise ModuleManifestError(f"module {manifest.id!r}: CHANGELOG.md is missing")
    return _CHANGELOG_HEADING.findall(path.read_text(encoding="utf-8"))


def check_versioning(manifest: ModuleManifest) -> list[str]:
    """Changelog/errata discipline findings for *manifest* (empty = clean)."""
    problems: list[str] = []
    try:
        versions = changelog_versions(manifest)
    except ModuleManifestError as exc:
        return [str(exc)]
    if not versions:
        problems.append(f"module {manifest.id!r}: CHANGELOG.md has no '## X.Y.Z' heading")
    else:
        if versions[0] != manifest.version:
            problems.append(
                f"module {manifest.id!r}: newest CHANGELOG.md entry is {versions[0]}, "
                f"manifest version is {manifest.version}"
            )
        parsed = [parse_version(v) for v in versions]
        for newer, older in pairwise(parsed):
            if not newer > older:
                problems.append(
                    f"module {manifest.id!r}: CHANGELOG.md versions not strictly descending "
                    f"({'.'.join(map(str, newer))} before {'.'.join(map(str, older))})"
                )
    try:
        errata = module_errata(manifest)
    except ModuleManifestError as exc:
        problems.append(str(exc))
        return problems
    for erratum in errata:
        if erratum.fixed_in not in versions:
            problems.append(
                f"module {manifest.id!r}: erratum {erratum.id} fixed_in {erratum.fixed_in} "
                "has no CHANGELOG.md entry"
            )
    return problems


__all__ = [
    "ERRATA_FORMAT",
    "Erratum",
    "changelog_versions",
    "check_versioning",
    "module_errata",
    "parse_errata",
]
