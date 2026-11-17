"""WP-110 — module semver, errata and changelog discipline (ARCHITECTURE.md § 6.2).

Covers ``app.modules.semver``, ``app.modules.errata`` (format, rules,
``check_versioning``), the in-tree guard (every installed module's
changelog and errata are consistent), and the API surface: ``errata`` on
``GET /modules/{id}`` and ``GET /modules/{id}/errata/{erratum_id}/cases``.
"""

# Semantic Version: 1.0.0 | 2026-11-17 — WP-110

from __future__ import annotations

import contextlib
import uuid
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml
from sqlalchemy import delete

from app.core.config import settings
from app.db.models import CaseRun, CaseRunArea
from app.db.session import async_session_factory, engine
from app.main import app
from app.modules.errata import check_versioning, module_errata, parse_errata
from app.modules.registry import (
    ModuleManifestError,
    default_modules_root,
    discover_modules,
)
from app.modules.semver import VersionRangeError, in_range, parse_version, validate_range

HEADERS = {"X-Disclaimer-Ack": settings.DISCLAIMER_VERSION}
INSTALLED = discover_modules(default_modules_root())
DEFAULT = settings.DEFAULT_MODULE


def _erratum(**overrides: Any) -> dict[str, Any]:
    entry = {
        "id": "E-2026-901",
        "published": "2026-11-17",
        "affected_versions": ">=1.0.0,<1.2.1",
        "fixed_in": "1.2.1",
        "severity": "major",
        "component": "parameter",
        "summary_de": "Falscher Wert.",
        "summary_en": "Wrong value.",
        "action_de": "Neu berechnen.",
    }
    entry.update(overrides)
    return entry


def _doc(*entries: dict[str, Any]) -> dict[str, Any]:
    return {"format": "citizen-module-errata-v1.0", "errata": list(entries)}


class TestSemver:
    def test_parse(self) -> None:
        assert parse_version("1.4.0") == (1, 4, 0)
        for bad in ("1.4", "01.2.3", "1.2.3-rc1", "v1.2.3"):
            with pytest.raises(VersionRangeError):
                parse_version(bad)

    @pytest.mark.parametrize(
        ("version", "spec", "expected"),
        [
            ("1.2.0", ">=1.0.0,<1.3.0", True),
            ("1.3.0", ">=1.0.0,<1.3.0", False),
            ("0.9.9", ">=1.0.0,<1.3.0", False),
            ("3.1.0", ">=3.0,<4.0", True),  # patch may be omitted in bounds
            ("4.0.0", ">=3.0,<4.0", False),
            ("1.2.3", "=1.2.3", True),
            ("1.2.3", "1.2.3", True),  # bare version = exact pin
            ("1.2.4", "<=1.2.3", False),
        ],
    )
    def test_in_range(self, version: str, spec: str, expected: bool) -> None:
        assert in_range(version, spec) is expected

    def test_bad_range(self) -> None:
        with pytest.raises(VersionRangeError):
            validate_range(">=1.0.0;<2")


class TestErrataFormat:
    def test_valid_entry_and_affects(self) -> None:
        (erratum,) = parse_errata(_doc(_erratum()), "t")
        assert erratum.affects("1.2.0") and erratum.affects("1.0.0")
        assert not erratum.affects("1.2.1")
        assert not erratum.affects(None)
        assert not erratum.affects("garbage")  # unattributable, never "affected"

    def test_yaml_dates_accepted(self) -> None:
        data = yaml.safe_load(
            "format: citizen-module-errata-v1.0\nerrata:\n"
            + yaml.safe_dump([_erratum(published=None)]).replace("null", "2026-11-17")
        )
        (erratum,) = parse_errata(data, "t")
        assert erratum.published == "2026-11-17"

    @pytest.mark.parametrize(
        ("entry", "message"),
        [
            (_erratum(id="E-1"), "id"),
            (_erratum(severity="low"), "severity"),
            (_erratum(fixed_in="1.2.0"), "inside affected_versions"),
            (_erratum(affected_versions="garbage"), "unparsable"),
            ({**_erratum(), "extra": 1}, "Additional properties"),
        ],
    )
    def test_invalid(self, entry: dict[str, Any], message: str) -> None:
        with pytest.raises(ModuleManifestError, match=message):
            parse_errata(_doc(entry), "t")

    def test_duplicate_ids(self) -> None:
        with pytest.raises(ModuleManifestError, match="duplicate"):
            parse_errata(_doc(_erratum(), _erratum()), "t")


def _module(tmp_path: Path, version: str, changelog: str, errata: list[Any] | None) -> Any:
    module_dir = tmp_path / "demo_versions"
    module_dir.mkdir()
    manifest: dict[str, Any] = {
        "id": "demo_versions",
        "version": version,
        "core_api": ">=3.1,<4.0",
        "title": {"de": "D", "en": "D"},
        "tier": "experimental",
    }
    if errata is not None:
        manifest["errata"] = "errata.yaml"
        (module_dir / "errata.yaml").write_text(yaml.safe_dump(_doc(*errata)), encoding="utf-8")
    (module_dir / "module.yaml").write_text(yaml.safe_dump(manifest), encoding="utf-8")
    (module_dir / "CHANGELOG.md").write_text(changelog, encoding="utf-8")
    return discover_modules(tmp_path)["demo_versions"]


class TestCheckVersioning:
    def test_clean(self, tmp_path: Path) -> None:
        changelog = "# C\n\n## 1.2.1 — x\n\n## 1.2.0 — y\n"
        assert check_versioning(_module(tmp_path, "1.2.1", changelog, [_erratum()])) == []

    def test_manifest_ahead_of_changelog(self, tmp_path: Path) -> None:
        problems = check_versioning(_module(tmp_path, "1.3.0", "## 1.2.1\n", None))
        assert any("newest CHANGELOG.md entry is 1.2.1" in p for p in problems)

    def test_not_descending(self, tmp_path: Path) -> None:
        problems = check_versioning(_module(tmp_path, "1.2.0", "## 1.2.0\n## 1.3.0\n", None))
        assert any("strictly descending" in p for p in problems)

    def test_fixed_in_newer_than_module(self, tmp_path: Path) -> None:
        problems = check_versioning(_module(tmp_path, "1.2.0", "## 1.2.0\n", [_erratum()]))
        assert any("newer than the module version" in p for p in problems)

    def test_fixed_in_without_changelog_entry(self, tmp_path: Path) -> None:
        problems = check_versioning(_module(tmp_path, "1.2.2", "## 1.2.2\n", [_erratum()]))
        assert any("has no CHANGELOG.md entry" in p for p in problems)


@pytest.mark.parametrize("module_id", sorted(INSTALLED))
def test_installed_modules_follow_versioning_rules(module_id: str) -> None:
    """Guard: every in-tree module's changelog matches its manifest version."""
    assert check_versioning(INSTALLED[module_id]) == []


def test_default_module_publishes_d065_erratum() -> None:
    errata = {e.id: e for e in module_errata(INSTALLED[DEFAULT])}
    erratum = errata["E-2026-001"]
    assert erratum.component == "deadline" and erratum.severity == "critical"
    assert erratum.affects("1.2.0") and not erratum.affects(erratum.fixed_in)
    assert not erratum.affects(INSTALLED[DEFAULT].version)


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
async def _dispose_engine_per_test() -> AsyncGenerator[None, None]:
    yield
    with contextlib.suppress(Exception):
        await engine.dispose()


@pytest.fixture
async def client() -> AsyncGenerator[httpx.AsyncClient, None]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


async def test_module_detail_serves_errata(client: httpx.AsyncClient) -> None:
    body = (await client.get(f"/api/v1/modules/{DEFAULT}", headers=HEADERS)).json()
    assert [e["id"] for e in body["errata"]] == [e.id for e in module_errata(INSTALLED[DEFAULT])]
    assert set(body["errata"][0]) >= {"affected_versions", "fixed_in", "action_de"}
    assert body["origin"] == "in_tree"


async def test_erratum_cases_matches_recorded_module_versions(client: httpx.AsyncClient) -> None:
    erratum = module_errata(INSTALLED[DEFAULT])[0]
    cases = {"affected": uuid.uuid4(), "fixed": uuid.uuid4(), "unrecorded": uuid.uuid4()}
    versions = {"affected": "1.2.0", "fixed": erratum.fixed_in, "unrecorded": None}
    async with async_session_factory() as session:
        for name, case_id in cases.items():
            session.add(
                CaseRun(id=case_id, session_id="wp110", input_text="synthetic", status="completed")
            )
            await session.flush()
            session.add(
                CaseRunArea(
                    case_run_id=case_id,
                    legal_area=DEFAULT,
                    module_id=DEFAULT if versions[name] else None,
                    module_version=versions[name],
                    is_primary=True,
                )
            )
        await session.commit()
    try:
        resp = await client.get(
            f"/api/v1/modules/{DEFAULT}/errata/{erratum.id}/cases", headers=HEADERS
        )
        assert resp.status_code == 200
        body = resp.json()
        found = {c["case_id"] for c in body["cases"]}
        assert str(cases["affected"]) in found
        assert str(cases["fixed"]) not in found and str(cases["unrecorded"]) not in found
        assert body["erratum"]["id"] == erratum.id and body["count"] == len(body["cases"])
    finally:
        async with async_session_factory() as session:
            await session.execute(delete(CaseRun).where(CaseRun.id.in_(list(cases.values()))))
            await session.commit()


async def test_erratum_cases_404s(client: httpx.AsyncClient) -> None:
    resp = await client.get(f"/api/v1/modules/{DEFAULT}/errata/E-1999-999/cases", headers=HEADERS)
    assert resp.status_code == 404 and resp.json()["detail"]["error"] == "erratum_unknown"
    resp = await client.get("/api/v1/modules/nope_mod/errata/E-1999-999/cases", headers=HEADERS)
    assert resp.status_code == 404 and resp.json()["detail"]["error"] == "MODULE_UNKNOWN"


@pytest.mark.parametrize("module_id", sorted(INSTALLED))
def test_errata_users_exclude_core_api_3_0(module_id: str) -> None:
    """The `errata` key is core_api 3.1: a 3.0 core rejects the manifest, so a
    module declaring it must not claim 3.0 compatibility."""
    manifest = INSTALLED[module_id]
    if "errata" in manifest.raw:
        assert not in_range("3.0.0", manifest.core_api.replace(">=3.1", ">=3.1.0"))
