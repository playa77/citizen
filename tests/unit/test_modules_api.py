"""WP-95 — module API additions (ARCHITECTURE.md § 5, D-039, D-058).

Covers:
- ``resolve_request_areas``: module ids, legacy aliases, core-procedural keys,
  ``MODULE_UNKNOWN`` (precedence) and ``MODULE_NOT_ENABLED``
- ``GET /api/v1/modules``, ``/modules/{id}``, ``/modules/{id}/goldset``
  (shape, public parts only, 404 codes, enablement, goldset version)
- ``/meta/version`` ``modules`` key (enabled modules only)
- ``POST /analyze``: JSON-list ``legal_areas``, 422 codes before any pipeline
  work, ``resolved_modules`` only when ``legal_areas`` is non-empty
- ``resolved_modules`` on presets/intake responses
- ``eval.runner --module`` goldset resolution

Event-loop discipline as in ``test_disclosure.py``: the app runs on each
test's loop via httpx ASGITransport; the engine pool is disposed after every
test.
"""

# Semantic Version: 1.1.0 | 2026-11-16 — P10: Sozialrecht dossier content.
# 1.0.0 | 2026-11-16 — WP-95

from __future__ import annotations

import contextlib
import json
from collections.abc import AsyncGenerator, Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import yaml
from sqlalchemy import delete as sa_delete

from app.api.routes.intake import _with_modules
from app.api.routes.modules import _installed_at
from app.core.config import _get_settings, settings
from app.db.models import CaseRun
from app.db.session import async_session_factory, engine
from app.main import app
from app.modules.areas import area_tables
from app.modules.registry import default_modules_root, discover_modules
from app.modules.runtime import (
    MODULE_NOT_ENABLED,
    MODULE_UNKNOWN,
    ModuleRequestError,
    module_registry,
    resolve_request_areas,
    resolved_modules,
)
from app.modules.sync import manifest_sha256
from eval.runner import resolve_goldset_path

HEADERS = {"X-Disclaimer-Ack": settings.DISCLAIMER_VERSION}
INSTALLED = discover_modules(default_modules_root())
SOZIALRECHT = "sozialrecht"

#: An installed module other than Sozialrecht that owns its own area key
#: (all stubs qualify; pick deterministically).
OTHER = sorted(m for m in INSTALLED if m != SOZIALRECHT and m in area_tables().owner)[0]
#: A legacy alias key and the module that owns it (D-038).
ALIAS, ALIAS_OWNER = next(
    (alias, mid) for mid, man in sorted(INSTALLED.items()) for alias in man.legacy_aliases
)
#: An area key served by the core procedural library.
PROCEDURAL_KEY = next(k for k, owner in area_tables().owner.items() if owner == "core:procedural")


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


@pytest.fixture
def only_sozialrecht_enabled(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Run with ENABLED_MODULES = ["sozialrecht"] (provider-like posture).

    Patches the *live* settings singleton: other tests may reset it, so the
    object imported at collection time can be stale.
    """
    monkeypatch.setattr(_get_settings(), "ENABLED_MODULES", [SOZIALRECHT])
    module_registry.cache_clear()
    yield
    module_registry.cache_clear()


async def _sse_events(response: httpx.Response) -> list[dict[str, Any]]:
    content = (await response.aread()).decode("utf-8")
    return [
        json.loads(line[len("data: ") :])
        for line in content.splitlines()
        if line.startswith("data: ")
    ]


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------


class TestResolveRequestAreas:
    def test_module_alias_and_procedural_keys(self) -> None:
        resolved = resolve_request_areas([SOZIALRECHT, ALIAS, PROCEDURAL_KEY])
        assert [r.as_dict() for r in resolved] == [
            {
                "legal_area": SOZIALRECHT,
                "module_id": SOZIALRECHT,
                "module_version": INSTALLED[SOZIALRECHT].version,
                "legacy_alias": False,
                "enabled": True,
            },
            {
                "legal_area": ALIAS,
                "module_id": ALIAS_OWNER,
                "module_version": INSTALLED[ALIAS_OWNER].version,
                "legacy_alias": True,
                "enabled": True,
            },
            {
                "legal_area": PROCEDURAL_KEY,
                "module_id": None,
                "module_version": None,
                "legacy_alias": False,
                "enabled": True,
            },
        ]

    def test_empty_request_resolves_to_nothing(self) -> None:
        assert resolve_request_areas([]) == []

    def test_unknown_keys_are_all_listed(self) -> None:
        with pytest.raises(ModuleRequestError) as excinfo:
            resolve_request_areas([SOZIALRECHT, "nope", "gibtsnicht"])
        assert excinfo.value.code == MODULE_UNKNOWN
        assert excinfo.value.legal_areas == ["nope", "gibtsnicht"]

    def test_not_enabled(self, only_sozialrecht_enabled: None) -> None:
        with pytest.raises(ModuleRequestError) as excinfo:
            resolve_request_areas([SOZIALRECHT, OTHER, ALIAS])
        assert excinfo.value.code == MODULE_NOT_ENABLED
        assert excinfo.value.legal_areas == [OTHER, ALIAS]

    def test_unknown_takes_precedence_over_not_enabled(self, only_sozialrecht_enabled: None) -> None:
        with pytest.raises(ModuleRequestError) as excinfo:
            resolve_request_areas([OTHER, "nope"])
        assert excinfo.value.code == MODULE_UNKNOWN
        assert excinfo.value.legal_areas == ["nope"]

    def test_procedural_key_needs_no_enabled_module(self, only_sozialrecht_enabled: None) -> None:
        (entry,) = resolve_request_areas([PROCEDURAL_KEY])
        assert entry.module_id is None and entry.enabled

    def test_lenient_report_skips_unknown_and_flags_disabled(
        self, only_sozialrecht_enabled: None
    ) -> None:
        entries = resolved_modules([SOZIALRECHT, "nope", OTHER])
        assert [(e["legal_area"], e["enabled"]) for e in entries] == [
            (SOZIALRECHT, True),
            (OTHER, False),
        ]


# ---------------------------------------------------------------------------
# /modules
# ---------------------------------------------------------------------------


class TestModulesList:
    async def test_lists_every_installed_module(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/api/v1/modules", headers=HEADERS)
        assert response.status_code == 200
        body = response.json()
        assert "default_module" not in body
        assert "is_default" not in body
        ids = [m["id"] for m in body["modules"]]
        assert sorted(ids) == sorted(INSTALLED)
        assert ids[0] == area_tables().owner[area_tables().keys[0]]
        by_id = {m["id"]: m for m in body["modules"]}
        for module_id, manifest in INSTALLED.items():
            entry = by_id[module_id]
            assert entry["version"] == manifest.version
            assert entry["tier"] == manifest.tier
            assert entry["title"] == manifest.title
            assert "is_default" not in entry
            assert "default_module" not in entry
            assert entry["enabled"] is module_registry().is_enabled(module_id)
        assert ALIAS in by_id[ALIAS_OWNER]["area_keys"]
        assert by_id[ALIAS_OWNER]["area_keys"][0] == ALIAS_OWNER

    async def test_corpus_readiness_shape(self, client: httpx.AsyncClient) -> None:
        body = (await client.get("/api/v1/modules", headers=HEADERS)).json()
        module = next(m for m in body["modules"] if m["id"] == SOZIALRECHT)
        corpus = module["corpus"]
        assert set(corpus) == {
            "chunk_count",
            "source_types",
            "present_source_types",
            "missing_source_types",
            "is_ready",
        }
        assert corpus["source_types"] == list(area_tables().source_types[SOZIALRECHT])
        assert corpus["is_ready"] is (not corpus["missing_source_types"])

    async def test_database_down_degrades_to_null(self, client: httpx.AsyncClient) -> None:
        with patch(
            "app.api.routes.modules.chunk_counts_by_source_type",
            new=AsyncMock(side_effect=OSError("db down")),
        ):
            body = (await client.get("/api/v1/modules", headers=HEADERS)).json()
        assert all(m["corpus"] is None and m["installed_at"] is None for m in body["modules"])

    async def test_enablement_follows_registry(
        self, client: httpx.AsyncClient, only_sozialrecht_enabled: None
    ) -> None:
        body = (await client.get("/api/v1/modules", headers=HEADERS)).json()
        assert {m["id"]: m["enabled"] for m in body["modules"]} == {
            mid: mid == SOZIALRECHT for mid in INSTALLED
        }

    async def test_requires_disclaimer_ack(self, client: httpx.AsyncClient) -> None:
        assert (await client.get("/api/v1/modules")).status_code == 403


class TestInstalledAt:
    def test_only_a_row_of_the_running_manifest_dates_it(self) -> None:
        manifest = INSTALLED[SOZIALRECHT]
        stamp = SimpleNamespace(isoformat=lambda: "2026-11-16T10:00:00+00:00")
        current = SimpleNamespace(manifest_sha256=manifest_sha256(manifest), installed_at=stamp)
        stale = SimpleNamespace(manifest_sha256=None, installed_at=stamp)
        assert _installed_at(manifest, {SOZIALRECHT: current}) == "2026-11-16T10:00:00+00:00"  # type: ignore[dict-item]
        assert _installed_at(manifest, {SOZIALRECHT: stale}) is None  # type: ignore[dict-item]
        assert _installed_at(manifest, {}) is None
        assert _installed_at(manifest, None) is None


class TestModuleDetail:
    async def test_sozialrecht_detail(self, client: httpx.AsyncClient) -> None:
        response = await client.get(f"/api/v1/modules/{SOZIALRECHT}", headers=HEADERS)
        assert response.status_code == 200
        body = response.json()
        manifest = INSTALLED[SOZIALRECHT]
        assert body["id"] == SOZIALRECHT
        assert "default_module" not in body
        assert "is_default" not in body
        assert body["core_api"] == manifest.core_api
        assert body["scope"]["summary_de"] == manifest.raw["scope"]["summary_de"]
        assert body["capabilities"]["deadlines"] is True
        assert body["capabilities"]["goldset"] is True
        # P10 (WP-102): Sozialrecht ships dossier content.
        assert body["capabilities"]["dossier"] is True
        assert body["dossier_checklist"]["format"] == "citizen-module-dossier-v1.0"

        fristen = yaml.safe_load((manifest.path / manifest.raw["fristen"]).read_text("utf-8"))
        assert [d["id"] for d in body["deadlines"]] == [f["id"] for f in fristen]
        first = body["deadlines"][0]
        assert first["basis"] == fristen[0]["basis"]
        assert set(first["duration"]) == {"days", "months", "years"}

        assert [d["id"] for d in body["document_types"]] == manifest.raw["documents"]
        assert all(d["title"] for d in body["document_types"])

    async def test_no_file_paths_or_code_refs_leak(self, client: httpx.AsyncClient) -> None:
        text = (await client.get(f"/api/v1/modules/{SOZIALRECHT}", headers=HEADERS)).text
        raw = INSTALLED[SOZIALRECHT].raw
        for secret in (
            raw["calculators"],
            raw["regimes"]["provider"],
            raw["corpus"],
            raw["document_templates"],
            raw["goldset"]["path"],
            str(INSTALLED[SOZIALRECHT].path),
        ):
            assert secret not in text

    async def test_stub_module_has_empty_catalogs(self, client: httpx.AsyncClient) -> None:
        body = (await client.get(f"/api/v1/modules/{OTHER}", headers=HEADERS)).json()
        if "fristen" not in INSTALLED[OTHER].raw:
            assert body["deadlines"] == []
        if "documents" not in INSTALLED[OTHER].raw:
            assert body["document_types"] == []

    async def test_unknown_module_404(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/api/v1/modules/nope", headers=HEADERS)
        assert response.status_code == 404
        assert response.json()["detail"]["error"] == MODULE_UNKNOWN

    async def test_disabled_module_is_served(
        self, client: httpx.AsyncClient, only_sozialrecht_enabled: None
    ) -> None:
        response = await client.get(f"/api/v1/modules/{OTHER}", headers=HEADERS)
        assert response.status_code == 200
        assert response.json()["enabled"] is False


class TestModuleGoldset:
    async def test_declared_goldset(self, client: httpx.AsyncClient) -> None:
        response = await client.get(f"/api/v1/modules/{SOZIALRECHT}/goldset", headers=HEADERS)
        assert response.status_code == 200
        body = response.json()
        declared = INSTALLED[SOZIALRECHT].raw["goldset"]
        doc = yaml.safe_load((INSTALLED[SOZIALRECHT].path / declared["path"]).read_text("utf-8"))
        assert body["module_id"] == SOZIALRECHT
        assert body["module_version"] == INSTALLED[SOZIALRECHT].version
        assert body["gate"] == declared["gate"]
        assert body["goldset"]["version"] == doc["goldset"]["version"]
        assert len(body["cases"]) == len(doc["cases"])
        assert "input_document" not in body["cases"][0]

    async def test_same_listing_shape_as_goldset_alias(self, client: httpx.AsyncClient) -> None:
        alias = (await client.get("/api/v1/goldset", headers=HEADERS)).json()
        module = (await client.get(f"/api/v1/modules/{SOZIALRECHT}/goldset", headers=HEADERS)).json()
        assert set(alias["goldset"]) == set(module["goldset"])
        assert set(alias["cases"][0]) == set(module["cases"][0])

    async def test_module_without_goldset_404(self, client: httpx.AsyncClient) -> None:
        no_goldset = sorted(m for m, man in INSTALLED.items() if "goldset" not in man.raw)[0]
        response = await client.get(f"/api/v1/modules/{no_goldset}/goldset", headers=HEADERS)
        assert response.status_code == 404
        assert response.json()["detail"]["error"] == "goldset_not_declared"

    async def test_unknown_module_404(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/api/v1/modules/nope/goldset", headers=HEADERS)
        assert response.status_code == 404
        assert response.json()["detail"]["error"] == MODULE_UNKNOWN


# ---------------------------------------------------------------------------
# /meta/version
# ---------------------------------------------------------------------------


class TestMetaVersionModules:
    async def test_enabled_modules_with_versions(self, client: httpx.AsyncClient) -> None:
        body = (await client.get("/api/v1/meta/version", headers=HEADERS)).json()
        enabled = module_registry().enabled
        assert body["modules"] == {mid: INSTALLED[mid].version for mid in sorted(enabled)}
        assert list(body["modules"]) == sorted(body["modules"])

    async def test_restricted_enablement(
        self, client: httpx.AsyncClient, only_sozialrecht_enabled: None
    ) -> None:
        body = (await client.get("/api/v1/meta/version", headers=HEADERS)).json()
        assert body["modules"] == {SOZIALRECHT: INSTALLED[SOZIALRECHT].version}


# ---------------------------------------------------------------------------
# /analyze
# ---------------------------------------------------------------------------

_READY = {"is_ready": True, "areas": {}, "missing_source_types": [], "ready_source_types": []}


def _fake_pipeline(state: Any) -> Any:
    async def gen() -> AsyncGenerator[str, None]:
        state.final_output = {"ergebnis": "Ergebnis."}
        yield 'data: {"stage": "normalization", "status": "complete", "payload": {}}\n\n'

    return gen()


async def _delete_case_run(session_id: str) -> None:
    async with async_session_factory() as db:
        await db.execute(sa_delete(CaseRun).where(CaseRun.session_id == session_id))
        await db.commit()


class TestAnalyzeModuleGate:
    @patch("app.api.routes.analyze.run_pipeline")
    async def test_unknown_area_422_before_pipeline(
        self, mock_run: MagicMock, client: httpx.AsyncClient
    ) -> None:
        response = await client.post(
            "/api/v1/analyze",
            json={"text": "Bescheid.", "legal_areas": [SOZIALRECHT, "nope"]},
            headers=HEADERS,
        )
        assert response.status_code == 422
        detail = response.json()["detail"]
        assert detail["error"] == MODULE_UNKNOWN
        assert detail["legal_areas"] == ["nope"]
        mock_run.assert_not_called()

    @patch("app.api.routes.analyze.run_pipeline")
    async def test_not_enabled_422(
        self, mock_run: MagicMock, client: httpx.AsyncClient, only_sozialrecht_enabled: None
    ) -> None:
        response = await client.post(
            "/api/v1/analyze",
            json={"text": "Bescheid.", "legal_areas": f"{SOZIALRECHT},{OTHER}"},
            headers=HEADERS,
        )
        assert response.status_code == 422
        assert response.json()["detail"]["error"] == MODULE_NOT_ENABLED
        assert response.json()["detail"]["legal_areas"] == [OTHER]
        mock_run.assert_not_called()

    @patch("app.api.routes.analyze.check_preflight", new_callable=AsyncMock)
    @patch("app.api.routes.analyze.run_pipeline")
    async def test_json_list_accepted_and_resolved_modules_reported(
        self, mock_run: MagicMock, mock_preflight: AsyncMock, client: httpx.AsyncClient
    ) -> None:
        mock_run.side_effect = _fake_pipeline
        mock_preflight.return_value = _READY
        async with client.stream(
            "POST",
            "/api/v1/analyze",
            json={"text": "Bescheid.", "legal_areas": [ALIAS, PROCEDURAL_KEY]},
            headers=HEADERS,
        ) as response:
            assert response.status_code == 200
            events = await _sse_events(response)
        final = next(e for e in events if "final_output" in e)
        await _delete_case_run(final["session_id"])
        assert final["resolved_modules"] == [
            r.as_dict() for r in resolve_request_areas([ALIAS, PROCEDURAL_KEY])
        ]
        assert mock_run.call_args.args[0].legal_areas == [ALIAS, PROCEDURAL_KEY]

    @pytest.mark.parametrize(
        "areas",
        [
            [],
            [PROCEDURAL_KEY],
            ["andere"],
            ["strafrecht"],
            ["arbeitsrecht"],
            [SOZIALRECHT, "arbeitsrecht"],
        ],
    )
    @patch("app.api.routes.analyze.check_preflight", new_callable=AsyncMock)
    @patch("app.api.routes.analyze.run_pipeline")
    async def test_selection_required_scope_skips_corpus_preflight(
        self,
        mock_run: MagicMock,
        mock_preflight: AsyncMock,
        client: httpx.AsyncClient,
        areas: list[str],
    ) -> None:
        mock_run.side_effect = _fake_pipeline
        mock_preflight.side_effect = AssertionError("preparation must not check legal corpus")
        async with client.stream(
            "POST",
            "/api/v1/analyze",
            json={"text": "Synthetischer Bescheid.", "legal_areas": areas},
            headers=HEADERS,
        ) as response:
            assert response.status_code == 200
            events = await _sse_events(response)
        final = next(e for e in events if "final_output" in e)
        await _delete_case_run(final["session_id"])
        assert final["final_output"]["ergebnis"] == "Ergebnis."
        assert mock_run.call_args.args[0].legal_areas == areas
        mock_preflight.assert_not_awaited()
        if areas:
            assert final["resolved_modules"] == [
                entry.as_dict() for entry in resolve_request_areas(areas)
            ]
        else:
            assert "resolved_modules" not in final

    @patch("app.api.routes.analyze.run_pipeline")
    async def test_no_legal_areas_no_resolved_modules(
        self, mock_run: MagicMock, client: httpx.AsyncClient
    ) -> None:
        mock_run.side_effect = _fake_pipeline
        async with client.stream(
            "POST", "/api/v1/analyze", json={"text": "Bescheid."}, headers=HEADERS
        ) as response:
            events = await _sse_events(response)
        final = next(e for e in events if "final_output" in e)
        await _delete_case_run(final["session_id"])
        assert "resolved_modules" not in final


# ---------------------------------------------------------------------------
# presets / intake
# ---------------------------------------------------------------------------


class TestResolvedModulesOnPresetsAndIntake:
    async def test_presets_apply(self, client: httpx.AsyncClient) -> None:
        preset = area_tables().presets[0]
        body = (
            await client.post(
                "/api/v1/presets/apply", json={"preset_id": preset["id"]}, headers=HEADERS
            )
        ).json()
        assert [e["legal_area"] for e in body["resolved_modules"]] == body["legal_areas"]

    async def test_presets_suggest(self, client: httpx.AsyncClient) -> None:
        suggestion = {"preset_id": "x", "primary_area": ALIAS, "secondary_areas": [SOZIALRECHT]}
        with patch(
            "app.api.routes.presets._call_llm_suggest", new=AsyncMock(return_value=suggestion)
        ):
            body = (
                await client.post("/api/v1/presets/suggest", json={"text": "t"}, headers=HEADERS)
            ).json()
        assert [(e["legal_area"], e["module_id"]) for e in body["resolved_modules"]] == [
            (ALIAS, ALIAS_OWNER),
            (SOZIALRECHT, SOZIALRECHT),
        ]

    def test_no_keyword_match_suggests_no_preset(self) -> None:
        from app.api.routes.presets import _keyword_suggest

        suggestion = _keyword_suggest("xyzzy")
        assert suggestion["preset_id"] == ""
        assert suggestion["secondary_areas"] == []
        assert suggestion["suggestions"] == []

    async def test_no_preset_match_resolves_no_modules(self, client: httpx.AsyncClient) -> None:
        from app.api.routes.presets import _keyword_suggest

        suggestion = _keyword_suggest("xyzzy")
        with patch(
            "app.api.routes.presets._call_llm_suggest", new=AsyncMock(return_value=suggestion)
        ):
            response = await client.post(
                "/api/v1/presets/suggest", json={"text": "xyzzy"}, headers=HEADERS
            )
        assert response.status_code == 200
        body = response.json()
        assert body["preset_id"] == ""
        assert body["suggestions"] == []
        assert body["resolved_modules"] == []

    def test_tied_keyword_matches_suggest_all_candidates_without_selecting(self) -> None:
        from app.api.routes.presets import _keyword_suggest

        suggestion = _keyword_suggest("jobcenter testament")
        assert suggestion["preset_id"] == ""
        assert suggestion["primary_area"] == area_tables().catch_all
        assert suggestion["secondary_areas"] == []
        assert len(suggestion["suggestions"]) == 2
        assert {
            (entry["preset_id"], entry["primary_area"], tuple(entry["secondary_areas"]))
            for entry in suggestion["suggestions"]
        } == {
            ("sozialrecht-allgemein", SOZIALRECHT, ()),
            ("erbe-mit-testament", "erbrecht", ()),
        }

    def test_unique_keyword_match_preserves_scalar_suggestion(self) -> None:
        from app.api.routes.presets import _keyword_suggest

        suggestion = _keyword_suggest("jobcenter")
        assert suggestion["preset_id"] == "sozialrecht-allgemein"
        assert suggestion["primary_area"] == SOZIALRECHT
        assert suggestion["secondary_areas"] == []

    async def test_tied_preset_suggestions_resolve_all_candidate_modules(
        self, client: httpx.AsyncClient
    ) -> None:
        from app.api.routes.presets import _keyword_suggest

        suggestion = _keyword_suggest("jobcenter testament")
        with patch(
            "app.api.routes.presets._call_llm_suggest", new=AsyncMock(return_value=suggestion)
        ):
            response = await client.post(
                "/api/v1/presets/suggest",
                json={"text": "jobcenter testament"},
                headers=HEADERS,
            )
        assert response.status_code == 200
        body = response.json()
        assert body["preset_id"] == ""
        assert body["primary_area"] == area_tables().catch_all
        assert body["secondary_areas"] == []
        assert body["suggestions"] == suggestion["suggestions"]
        assert len(body["resolved_modules"]) == 2
        assert {
            (entry["legal_area"], entry["module_id"])
            for entry in body["resolved_modules"]
        } == {(SOZIALRECHT, SOZIALRECHT), ("erbrecht", "erbrecht")}

    def test_intake_session_without_areas(self) -> None:
        session = {"id": "x", "primary_area": None, "secondary_areas": []}
        assert _with_modules(session) == {**session, "resolved_modules": []}

    def test_intake_session_primary_first_deduplicated(self) -> None:
        session = {"primary_area": ALIAS, "secondary_areas": [SOZIALRECHT, ALIAS]}
        assert [e["legal_area"] for e in _with_modules(session)["resolved_modules"]] == [
            ALIAS,
            SOZIALRECHT,
        ]


# ---------------------------------------------------------------------------
# eval.runner --module
# ---------------------------------------------------------------------------


class TestEvalRunnerModule:
    def test_module_resolves_declared_goldset(self) -> None:
        path = Path(resolve_goldset_path(None, SOZIALRECHT))
        manifest = INSTALLED[SOZIALRECHT]
        assert path == (manifest.path / manifest.raw["goldset"]["path"]).resolve()
        assert path.is_file()

    def test_explicit_path_passes_through(self) -> None:
        assert resolve_goldset_path("some/goldset.yaml", None) == "some/goldset.yaml"

    @pytest.mark.parametrize(
        ("goldset", "module_id", "message"),
        [
            (None, None, "either"),
            ("x.yaml", "y", "either"),
            (None, "nope", "not installed"),
        ],
    )
    def test_usage_errors(self, goldset: str | None, module_id: str | None, message: str) -> None:
        with pytest.raises(ValueError, match=message):
            resolve_goldset_path(goldset, module_id)

    def test_module_without_goldset(self) -> None:
        no_goldset = sorted(m for m, man in INSTALLED.items() if "goldset" not in man.raw)[0]
        with pytest.raises(ValueError, match="declares no goldset"):
            resolve_goldset_path(None, no_goldset)
