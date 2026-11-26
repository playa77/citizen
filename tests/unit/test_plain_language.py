"""P12 — plain-language layer and consumer-compliance surfaces (WP-122/123/125, D-068).

Contracts pinned here:

* category keys and the closed-vocabulary classification of ``ergebnis``
  (off-vocabulary answers fall back to the open category, never to
  reassuring copy);
* dates spelled out deterministically, independent of host locale;
* the offline gate (``eval.plain_eval``) passes for ``sozialrecht`` and
  fails on each defect class it exists to catch;
* core copy is pinned to the running disclaimer/disclosure versions;
* the HTTP surfaces: ``/meta/disclaimer/plain`` and ``/meta/privacy`` are
  readable before the disclaimer ack, ``/modules/{id}/plain`` and
  ``/cases/{id}/plain`` follow the module/case error contract, and
  ``/analyze`` adds ``plain`` only when asked (terminal event otherwise
  unchanged).
"""

# Semantic Version: 1.0.0 | 2026-11-17 — P12

from __future__ import annotations

import asyncio
import contextlib
import json
import uuid
from collections.abc import AsyncGenerator
from datetime import date
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from sqlalchemy import delete as sa_delete

from app.core.config import Settings, settings
from app.db.models import CaseRun, CaseRunArea, PipelineStageLog
from app.db.session import async_session_factory, engine
from app.main import app
from app.modules.runtime import get_manifest
from app.plain import core_copy
from app.plain.checks import discouraging_hits, long_sentences, sentences
from app.plain.copy import category_key, finding_categories
from app.plain.languages import format_date
from app.plain.render import (
    classify_ergebnis,
    deadline_banner,
    render_deadline,
)
from app.services.disclosure import DISCLOSURE_VERSION
from eval import plain_eval

HEADERS = {"X-Disclaimer-Ack": settings.DISCLAIMER_VERSION}
SOZ = "sozialrecht"


# ---------------------------------------------------------------------------
# Units
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("term", "key"),
    [
        ("rechtswidrig", "rechtswidrig"),
        ("überwiegend rechtmäßig", "ueberwiegend_rechtmaessig"),
        ("Einordnung offen", "einordnung_offen"),
        ("kein Verwaltungsakt", "kein_verwaltungsakt"),
    ],
)
def test_category_key(term: str, key: str) -> None:
    assert category_key(term) == key


def test_sozialrecht_categories_follow_prompt_profile_plus_open() -> None:
    keys = [c.key for c in finding_categories(get_manifest(SOZ))]
    assert keys == [
        "rechtswidrig",
        "teilweise_rechtswidrig",
        "ueberwiegend_rechtmaessig",
        "kein_verwaltungsakt",
        "einordnung_offen",
    ]


@pytest.mark.parametrize(
    ("ergebnis", "key", "source"),
    [
        ("Vorläufige Einordnung: rechtswidrig. Begründung …", "rechtswidrig", "ergebnis"),
        (
            "Vorläufige Einordnung: Teilweise rechtswidrig (KdU).",
            "teilweise_rechtswidrig",
            "ergebnis",
        ),
        ("Vorläufige Einordnung: alles gut.", "einordnung_offen", "fallback"),
        ("Der Bescheid ist richtig.", "einordnung_offen", "fallback"),
        (None, "einordnung_offen", "fallback"),
    ],
)
def test_classify_ergebnis(ergebnis: str | None, key: str, source: str) -> None:
    category, got_source = classify_ergebnis(ergebnis, finding_categories(get_manifest(SOZ)))
    assert (category.key, got_source) == (key, source)


def test_format_date() -> None:
    d = date(2026, 12, 21)
    assert format_date(d, "de") == "Montag, 21. Dezember 2026"
    assert format_date(d, "de-LS") == "Montag, 21. Dezember 2026"
    assert format_date(d, "en") == "Monday, 21 December 2026"
    assert format_date(d, "tr") == "2026-12-21"


def test_checks_detect_discouragement_and_long_sentences() -> None:
    assert discouraging_hits("Ein Widerspruch ist hier aussichtslos.") == ["aussichtslos"]
    assert discouraging_hits("There is no chance.") == ["no chance"]
    assert discouraging_hits("Sie haben eine Chance.") == []
    assert sentences("Grundlage: § 84 Abs. 1 SGG. Neuer Satz.") == [
        "Grundlage: § 84 Abs. 1 SGG.",
        "Neuer Satz.",
    ]
    assert long_sentences("Eins zwei drei vier.", 3)[0][0] == 4


def _item(**over: Any) -> dict[str, Any]:
    base = {
        "module_id": SOZ,
        "spec_id": "widerspruch_sgg_84",
        "severity": "critical",
        "basis": "§ 84 Abs. 1 SGG",
        "status": "computed",
        "frist_typ": "monat",
        "bekanntgabe": "2026-11-20",
        "frist_ende": "2026-12-21",
    }
    return {**base, **over}


def test_render_deadline_never_renders_without_its_date() -> None:
    # A computed status without frist_ende cannot fill the text: the language
    # is reported missing instead of rendering a dateless deadline.
    rendered = render_deadline(get_manifest(SOZ), _item(frist_ende=None), ["de", "en"])
    assert rendered["texts"] == {}
    assert rendered["missing_languages"] == ["de", "en"]


def test_render_deadline_languages_and_bcp47() -> None:
    rendered = render_deadline(get_manifest(SOZ), _item(), ["de", "de-LS", "en", "fr"])
    assert rendered["texts"]["de-LS"]["bcp47"] == "de"
    assert rendered["texts"]["de-LS"]["register"] == "leichte_sprache"
    assert "Montag, 21. Dezember 2026" in rendered["texts"]["de"]["text"]
    assert rendered["missing_languages"] == ["fr"]


def test_banner_prefers_missing_input_then_earliest() -> None:
    late = {**_item(frist_ende="2027-01-31"), "spec_id": "late"}
    early = {**_item(frist_ende="2026-12-01"), "spec_id": "early"}
    unknown = {**_item(status="missing_input", frist_ende=None), "spec_id": "unknown"}
    info = {**_item(severity="info", frist_ende="2026-11-30"), "spec_id": "info"}
    assert deadline_banner([late, early, info])["spec_id"] == "early"
    assert deadline_banner([late, early, unknown])["spec_id"] == "unknown"
    assert deadline_banner([{**early, "status": "not_applicable"}]) is None


# ---------------------------------------------------------------------------
# Gate
# ---------------------------------------------------------------------------


def test_gate_passes_for_sozialrecht() -> None:
    report = plain_eval.evaluate(SOZ)
    assert report["failures"] == {}
    assert report["gate_passed"] is True
    assert report["cases_passed"] == report["cases_total"] >= 13
    # OQ-3: review is reported, not gated.
    assert report["review_pending"] == ["de", "de-LS", "en"]


def test_gate_fails_without_leichte_sprache_for_critical_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.plain.copy as copy_mod

    real = copy_mod.declared_copy_files

    def without_ls(manifest: Any) -> dict[str, str]:
        return {k: v for k, v in real(manifest).items() if k != "de-LS"}

    monkeypatch.setattr(copy_mod, "declared_copy_files", without_ls)
    failures, _ = plain_eval.check_copy(SOZ)
    assert any("de-LS" in f for f in failures["coverage"])


@pytest.mark.parametrize(
    ("mutate", "check"),
    [
        (lambda d: d["findings"].pop("einordnung_offen"), "coverage"),
        (lambda d: d["deadlines"]["widerspruch_sgg_84"]["texts"].pop("missing_input"), "coverage"),
        (
            lambda d: d["deadlines"]["widerspruch_sgg_84"]["texts"].__setitem__(
                "missing_input", "Ihre Frist endet am {frist_ende}."
            ),
            "placeholders",
        ),
        (
            lambda d: d["findings"]["rechtswidrig"].__setitem__(
                "next_step", "Ein Widerspruch ist leider aussichtslos."
            ),
            "duty_of_care",
        ),
        (
            lambda d: d["findings"]["rechtswidrig"].__setitem__(
                "text", " ".join(["Wort"] * 30) + "."
            ),
            "readability",
        ),
        (lambda d: d.__setitem__("format", "other"), "schema"),
    ],
)
def test_gate_catches_each_defect_class(
    monkeypatch: pytest.MonkeyPatch, mutate: Any, check: str
) -> None:
    import copy as pycopy

    import app.modules.content as content_mod

    real = content_mod.load_yaml

    def patched(manifest: Any, relative: str) -> Any:
        doc = real(manifest, relative)
        if relative == "copy/de/plain.yaml":
            doc = pycopy.deepcopy(doc)
            mutate(doc)
        return doc

    monkeypatch.setattr(content_mod, "load_yaml", patched)
    failures, _ = plain_eval.check_copy(SOZ)
    assert failures[check], failures


def test_core_copy_is_pinned_to_running_versions() -> None:
    default = str(Settings.model_fields["DISCLAIMER_VERSION"].default)
    for language in ("de", "de-LS", "en"):
        doc = core_copy.load_core_copy(
            language, disclaimer_version=default, disclosure_version=DISCLOSURE_VERSION
        )
        assert doc["language"] == language
    with pytest.raises(core_copy.CoreCopyError):
        core_copy.load_core_copy("de", disclaimer_version="v9.9.9", disclosure_version="1.0")


# ---------------------------------------------------------------------------
# HTTP
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


async def test_disclaimer_plain_readable_before_ack(client: httpx.AsyncClient) -> None:
    resp = await client.get("/api/v1/meta/disclaimer/plain", params={"lang": "de,de-LS,en"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["version"] == settings.DISCLAIMER_VERSION
    assert body["ack"] == {
        "header": "X-Disclaimer-Ack",
        "value": settings.DISCLAIMER_VERSION,
        "note": body["ack"]["note"],
    }
    assert list(body["texts"]) == ["de", "de-LS", "en"]
    assert body["texts"]["de-LS"]["bcp47"] == "de"
    assert body["texts"]["de"]["disclaimer"]["points"]


async def test_disclaimer_plain_language_errors(client: httpx.AsyncClient) -> None:
    bad = await client.get("/api/v1/meta/disclaimer/plain", params={"lang": "de;drop"})
    assert bad.status_code == 422
    assert bad.json()["detail"]["error"] == "PLAIN_LANGUAGE_INVALID"
    missing = await client.get("/api/v1/meta/disclaimer/plain", params={"lang": "fr"})
    assert missing.status_code == 404
    assert missing.json()["detail"]["error"] == "PLAIN_LANGUAGE_UNAVAILABLE"


async def test_disclaimer_plain_refuses_stale_copy(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core.config import _get_settings

    # Patch the live singleton: other tests may have replaced it since import.
    monkeypatch.setattr(_get_settings(), "DISCLAIMER_VERSION", "v9.9.9")
    resp = await client.get("/api/v1/meta/disclaimer/plain")
    assert resp.status_code == 503
    assert resp.json()["detail"]["error"] == "plain_copy_stale"


async def test_disclaimer_text_no_longer_claims_no_storage(client: httpx.AsyncClient) -> None:
    body = (await client.get("/api/v1/meta/disclaimer/text")).json()
    assert body["version"] == settings.DISCLAIMER_VERSION
    assert "nicht dauerhaft gespeichert" not in body["text"]
    assert "keine Rechtsberatung" in body["text"]


async def test_privacy_view(client: httpx.AsyncClient) -> None:
    resp = await client.get("/api/v1/meta/privacy", params={"lang": "de,en"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["deployment_mode"] == settings.DEPLOYMENT_MODE
    assert body["storage"]["cases_stored"] is True
    assert set(body["texts"]) == {"de", "en"}
    assert body["texts"]["de"]["deployment"]
    assert "OPENROUTER_API_KEY" not in json.dumps(body)


async def test_module_plain(client: httpx.AsyncClient) -> None:
    resp = await client.get("/api/v1/modules/sozialrecht/plain", headers=HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert body["available_languages"] == ["de", "de-LS", "en"]
    assert set(body["copy"]) == {"de", "de-LS", "en"}
    one = await client.get(
        "/api/v1/modules/sozialrecht/plain", params={"lang": "en,fr"}, headers=HEADERS
    )
    assert set(one.json()["copy"]) == {"en"}
    assert one.json()["missing_languages"] == ["fr"]
    stub = await client.get("/api/v1/modules/erbrecht/plain", headers=HEADERS)
    assert stub.status_code == 404
    assert stub.json()["detail"]["error"] == "PLAIN_LANGUAGE_UNAVAILABLE"
    unknown = await client.get("/api/v1/modules/nope/plain", headers=HEADERS)
    assert unknown.json()["detail"]["error"] == "MODULE_UNKNOWN"
    detail = (await client.get("/api/v1/modules/sozialrecht", headers=HEADERS)).json()
    assert detail["plain_languages"] == ["de", "de-LS", "en"]
    assert detail["capabilities"]["plain_language"] is True


LETTER = "Jobcenter Essen\nEssen, 06.07.2026\n\nBescheid über die Aufhebung …"


@pytest.fixture
async def case_id() -> AsyncGenerator[uuid.UUID, None]:
    async with async_session_factory() as db:
        case = CaseRun(
            session_id=str(uuid.uuid4()),
            input_text=LETTER,
            status="completed",
            title="Plain-Testfall",
        )
        db.add(case)
        await db.flush()
        db.add(
            CaseRunArea(
                case_run_id=case.id,
                legal_area=SOZ,
                module_id=SOZ,
                module_version="1.5.0",
                is_primary=True,
            )
        )
        db.add(
            PipelineStageLog(
                case_run_id=case.id,
                stage_name="generation",
                output_snapshot={
                    "ergebnis": "Vorläufige Einordnung: teilweise rechtswidrig. Die KdU …"
                },
                duration_ms=1,
            )
        )
        await db.commit()
        cid = case.id
    try:
        yield cid
    finally:
        async with async_session_factory() as db:
            await db.execute(sa_delete(CaseRun).where(CaseRun.id == cid))
            await db.commit()


async def test_case_plain_follows_confirmation(
    client: httpx.AsyncClient, case_id: uuid.UUID
) -> None:
    url = f"/api/v1/cases/{case_id}/plain"
    assert (await client.get(url)).status_code == 403  # ack required

    body = (await client.get(url, params={"lang": "de,en"}, headers=HEADERS)).json()
    assert body["finding"]["category"] == "teilweise_rechtswidrig"
    assert body["has_ergebnis"] is True
    (deadline,) = body["deadlines"]
    # Letter date only proposed from the text → provisional, still bannered.
    assert deadline["status"] == "provisional"
    assert deadline["frist_ende"] == "2026-08-10"
    assert "voraussichtlich" in deadline["texts"]["de"]["text"]
    assert body["banner"] == {"module_id": SOZ, "spec_id": "widerspruch_sgg_84"}
    assert body["provenance"]["modules"][0]["id"] == SOZ

    put = await client.put(
        f"/api/v1/cases/{case_id}/dossier/chronology",
        json={"facts": {"bescheid_datum": "2026-07-06"}},
        headers=HEADERS,
    )
    assert put.status_code == 200
    body = (await client.get(url, params={"lang": "de"}, headers=HEADERS)).json()
    (deadline,) = body["deadlines"]
    assert deadline["status"] == "computed"
    assert "Montag, 10. August 2026" in deadline["texts"]["de"]["text"]

    missing = await client.get(f"/api/v1/cases/{uuid.uuid4()}/plain", headers=HEADERS)
    assert missing.status_code == 404


def _sse(data: dict[str, Any]) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


async def _run_analyze(client: httpx.AsyncClient, body: dict[str, Any]) -> list[dict[str, Any]]:
    async with client.stream("POST", "/api/v1/analyze", json=body, headers=HEADERS) as response:
        content = (await response.aread()).decode()
    pending = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    if pending:
        await asyncio.wait(pending, timeout=10)
    return [json.loads(line[6:]) for line in content.splitlines() if line.startswith("data: ")]


async def _cleanup(events: list[dict[str, Any]]) -> None:
    ids = [uuid.UUID(e["case_run_id"]) for e in events if "case_run_id" in e]
    async with async_session_factory() as db:
        for cid in ids:
            await db.execute(sa_delete(CaseRun).where(CaseRun.id == cid))
        await db.commit()


@patch("app.api.routes.analyze.run_pipeline")
async def test_analyze_plain_is_opt_in(
    mock_run_pipeline: MagicMock, client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def generator(state: Any) -> AsyncGenerator[str, None]:
        state.final_output = {"ergebnis": "Vorläufige Einordnung: überwiegend rechtmäßig."}
        yield _sse({"stage": "generation", "status": "complete", "payload": {"duration_ms": 1}})

    mock_run_pipeline.side_effect = generator
    monkeypatch.setattr(
        "app.api.routes.analyze.check_preflight", AsyncMock(return_value={"is_ready": True})
    )
    plain_events = await _run_analyze(
        client,
        {"text": "Testbescheid.", "legal_areas": [SOZ], "plain_languages": ["de", "en"]},
    )
    default_events = await _run_analyze(client, {"text": "Testbescheid.", "legal_areas": [SOZ]})
    try:
        final = plain_events[-1]
        assert final["plain"]["finding"]["category"] == "ueberwiegend_rechtmaessig"
        assert set(final["plain"]["finding"]["texts"]) == {"de", "en"}
        assert "plain" not in default_events[-1]
    finally:
        await _cleanup(plain_events + default_events)

    bad = await client.post(
        "/api/v1/analyze", json={"text": "x", "plain_languages": ["de-xx"]}, headers=HEADERS
    )
    assert bad.status_code == 422
    assert bad.json()["detail"]["error"] == "PLAIN_LANGUAGE_INVALID"
