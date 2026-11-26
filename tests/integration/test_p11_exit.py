"""P11 exit criterion (roadmap § 5): "a scaffolded test module passes
validation, ships a parameter update via the signed feed, and is visible
via /modules".

End to end through the shipped tools, each run as its own process the way
an author and an operator would run them:

1. ``scripts.new_module --out-of-tree`` scaffolds a module package;
2. a ``*.dist-info`` with a ``citizen.modules`` entry point makes it an
   installed out-of-tree module (what ``pip install`` would write);
3. ``scripts.validate_module --module <id>`` finds it by entry point and
   passes it;
4. ``scripts.module_update keygen / make / sign / apply`` ships a signed
   parameter update into the database (trust file in the test directory);
5. in-process, with the module enabled explicitly, ``GET /api/v1/modules``
   lists it (origin ``entry_point``, tier ``community``) and
   ``GET /api/v1/modules/{id}`` shows the applied feed and the
   feed-qualified ``parameter_set`` after the ledger is loaded as at startup.

Everything the test writes to the database is removed afterwards.
"""

# Semantic Version: 1.0.0 | 2026-11-17

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml
from sqlalchemy import delete

from app.core.config import _get_settings, settings
from app.db.models import LegalModule, LegalParameter, ModuleUpdate
from app.db.session import async_session_factory, engine
from app.main import app
from app.modules import areas, runtime
from app.updates.ledger import load_applied_updates

REPO = Path(__file__).resolve().parents[2]
MODULE_ID = "p11_exitmod"
HEADERS = {"X-Disclaimer-Ack": settings.DISCLAIMER_VERSION}


def _run(args: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", *args],
        cwd=REPO,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


def _clear_caches() -> None:
    runtime.installed_modules.cache_clear()
    runtime.module_registry.cache_clear()
    runtime.module_provenance.cache_clear()
    areas.area_tables.cache_clear()


async def _cleanup_db() -> None:
    async with async_session_factory() as session:
        await session.execute(delete(ModuleUpdate).where(ModuleUpdate.module_id == MODULE_ID))
        await session.execute(delete(LegalParameter).where(LegalParameter.domain == MODULE_ID))
        await session.execute(delete(LegalModule).where(LegalModule.id == MODULE_ID))
        await session.commit()
    await engine.dispose()


@pytest.fixture
def installed_package(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    env = dict(os.environ)
    result = _run(
        [
            "scripts.new_module",
            MODULE_ID,
            "--title-de",
            "Exit-Test",
            "--title-en",
            "Exit test",
            "--out-of-tree",
            str(tmp_path),
        ],
        env,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    package = tmp_path / f"citizen-module-{MODULE_ID.replace('_', '-')}"
    dist_info = package / f"citizen_module_{MODULE_ID}-0.1.0.dist-info"
    dist_info.mkdir()
    (dist_info / "METADATA").write_text(
        f"Metadata-Version: 2.1\nName: citizen-module-{MODULE_ID}\nVersion: 0.1.0\n"
    )
    (dist_info / "entry_points.txt").write_text(
        f"[citizen.modules]\n{MODULE_ID} = citizen_module_{MODULE_ID}\n"
    )
    monkeypatch.syspath_prepend(str(package))
    monkeypatch.setattr(_get_settings(), "ENABLED_MODULES", ["sozialrecht", MODULE_ID])
    _clear_caches()
    try:
        yield package
    finally:
        asyncio.run(_cleanup_db())
        runtime.set_applied_updates({})
        monkeypatch.undo()
        _clear_caches()


def test_p11_exit(installed_package: Path, tmp_path: Path) -> None:
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([str(installed_package), env.get("PYTHONPATH", "")])

    # 3. validation, finding the module through its entry point
    validated = _run(["scripts.validate_module", "--module", MODULE_ID, "--json"], env)
    assert validated.returncode == 0, validated.stdout + validated.stderr
    (report,) = json.loads(validated.stdout)
    assert report["ok"] and report["tier"] == "community"

    # 4. a signed parameter update
    key = tmp_path / "release.pem"
    keygen = _run(["scripts.module_update", "keygen", "--out", str(key)], env)
    assert keygen.returncode == 0, keygen.stderr
    entry = yaml.safe_load(keygen.stdout.split("`keys:`):\n", 1)[1])
    trust = tmp_path / "trust.yaml"
    trust.write_text(yaml.safe_dump({"format": "citizen-update-trust-v1.0", "keys": entry}))
    rows = tmp_path / "rows.yaml"
    rows.write_text(
        yaml.safe_dump(
            {
                "parameters": [
                    {
                        "key": f"{MODULE_ID}.beispiel.betrag",
                        "value_numeric": 123.45,
                        "unit": "EUR",
                        "valid_from": "2027-01-01",
                        "review_status": "verified",
                        "basis": "Exit-Test",
                    }
                ]
            }
        )
    )
    feed = tmp_path / "feed.json"
    for args in (
        [
            "make",
            "--module",
            MODULE_ID,
            "--serial",
            "1",
            "--applies-to",
            ">=0.1.0,<1.0.0",
            "--parameters",
            str(rows),
            "--out",
            str(feed),
        ],
        ["sign", str(feed), "--key", str(key)],
        ["verify", str(feed), "--trust", str(trust)],
        ["apply", str(feed), "--trust", str(trust)],
    ):
        step = _run(["scripts.module_update", *args], env)
        assert step.returncode == 0, f"{args[0]}: {step.stdout}{step.stderr}"
    applied = json.loads(step.stdout[: step.stdout.rindex("}") + 1])
    assert applied["status"] == "applied"
    assert applied["parameters"][0]["action"] == "created"

    # 5. visible via /modules (startup would load the ledger the same way)
    async def check() -> tuple[dict[str, Any], dict[str, Any]]:
        async with async_session_factory() as session:
            state = await load_applied_updates(session)
        runtime.set_applied_updates({m: (a.serial, a.latest_valid_from) for m, a in state.items()})
        transport = httpx.ASGITransport(app=app)
        try:
            async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
                listing = (await client.get("/api/v1/modules", headers=HEADERS)).json()
                detail = (await client.get(f"/api/v1/modules/{MODULE_ID}", headers=HEADERS)).json()
        finally:
            with contextlib.suppress(Exception):
                await engine.dispose()
        return listing, detail

    listing, detail = asyncio.run(check())
    summary = next(m for m in listing["modules"] if m["id"] == MODULE_ID)
    assert summary["origin"] == "entry_point"
    assert summary["tier"] == "community" and summary["enabled"] is True
    assert detail["updates"][0]["serial"] == 1
    assert detail["updates"][0]["parameters"][0]["key"] == f"{MODULE_ID}.beispiel.betrag"
    assert detail["parameter_set"] == "0.1.0+2027-01-01.u1"
