"""WP-111 — signed module update channel (ARCHITECTURE.md § 3.9).

Signature/trust (Ed25519, key ids, per-module key scope, tamper detection),
feed format, applicability (version range, anti-rollback, clock skew),
the DB apply path inside a rolled-back transaction (parameter rows +
ledger, idempotent re-apply, feed rows protected from file re-seeding),
provenance ``parameter_set`` with applied feeds, and fetch hygiene.
"""

# Semantic Version: 1.0.0 | 2026-11-17 — WP-111

from __future__ import annotations

import base64
import json
import os
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.db.models import LegalParameter, ModuleUpdate
from app.modules.parameter_seed import upsert_parameter_rows
from app.modules.parameters import parse_parameter_entry
from app.modules.registry import ModuleManifestError, default_modules_root, discover_modules
from app.modules.runtime import module_provenance, set_applied_updates
from app.updates.apply import (
    apply_verified_feed,
    check_applicable,
    fetch_bytes,
    verify_feed,
)
from app.updates.feed import UpdateFeedError, build_feed, parse_feed
from app.updates.ledger import feed_owned_parameters, load_applied_updates
from app.updates.signing import (
    UpdateTrustError,
    generate_private_key,
    key_id_for,
    load_trust_file,
    parse_trust,
    public_key_bytes,
    sign_feed,
    write_private_key,
)

INSTALLED = discover_modules(default_modules_root())
DEFAULT = "sozialrecht"
MANIFEST = INSTALLED[DEFAULT]
NOW = datetime(2027, 1, 15, 9, 0, tzinfo=UTC)
KEY_UNDER_TEST = "test.wp111.betrag"


def _trust(key: Any, modules: list[str] | None = None) -> dict[str, Any]:
    raw = public_key_bytes(key.public_key())
    return parse_trust(
        {
            "format": "citizen-update-trust-v1.0",
            "keys": [
                {
                    "id": key_id_for(raw),
                    "public_key": base64.b64encode(raw).decode(),
                    "modules": modules or ["*"],
                }
            ],
        },
        "test",
    )


def _row(value: float = 42.0, valid_from: str = "2027-01-01") -> dict[str, Any]:
    return {
        "key": KEY_UNDER_TEST,
        "value_numeric": value,
        "unit": "EUR",
        "valid_from": valid_from,
        "review_status": "verified",
    }


def _feed(serial: int = 1, **overrides: Any) -> bytes:
    args: dict[str, Any] = {
        "module_id": DEFAULT,
        "serial": serial,
        "issued_at": NOW,
        "applies_to": f">={MANIFEST.version},<{int(MANIFEST.version.split('.')[0]) + 1}.0.0",
        "parameter_rows": [_row()],
        "corpus_notices": [{"source_type": "sgb2", "summary_de": "Änderung zum 01.01.2027"}],
    }
    args.update(overrides)
    return build_feed(**args)


@pytest.fixture
def key() -> Any:
    return generate_private_key()


# ---------------------------------------------------------------------------
# Signatures and trust
# ---------------------------------------------------------------------------


class TestSigning:
    def test_round_trip(self, key: Any) -> None:
        feed = _feed()
        verified = verify_feed(feed, sign_feed(feed, key), _trust(key), "mem")
        assert verified.feed.serial == 1 and verified.key_id == key_id_for(
            public_key_bytes(key.public_key())
        )

    def test_tampered_feed_refused(self, key: Any) -> None:
        feed = _feed()
        signature = sign_feed(feed, key)
        with pytest.raises(UpdateTrustError, match="does not verify"):
            verify_feed(feed.replace(b"42.0", b"43.0"), signature, _trust(key), "mem")

    def test_unknown_key_refused(self, key: Any) -> None:
        feed = _feed()
        with pytest.raises(UpdateTrustError, match="not in the trust file"):
            verify_feed(feed, sign_feed(feed, generate_private_key()), _trust(key), "mem")

    def test_key_scoped_to_other_module(self, key: Any) -> None:
        feed = _feed()
        with pytest.raises(UpdateTrustError, match="not trusted for module"):
            verify_feed(feed, sign_feed(feed, key), _trust(key, ["mietrecht"]), "mem")

    def test_signature_checked_before_parsing(self, key: Any) -> None:
        garbage = b"not json at all"
        with pytest.raises(UpdateTrustError):
            verify_feed(garbage, sign_feed(b"other", key), _trust(key), "mem")

    def test_trust_file_rules(self, key: Any) -> None:
        raw = public_key_bytes(key.public_key())
        entry = {"id": "0" * 16, "public_key": base64.b64encode(raw).decode(), "modules": ["*"]}
        with pytest.raises(UpdateTrustError, match="does not match"):
            parse_trust({"format": "citizen-update-trust-v1.0", "keys": [entry]}, "t")
        with pytest.raises(UpdateTrustError, match="format"):
            parse_trust({"keys": []}, "t")

    def test_shipped_trust_file_is_empty(self) -> None:
        repo = Path(__file__).resolve().parents[2]
        assert load_trust_file(repo / "config" / "update-trust.yaml") == {}

    def test_private_key_file_mode_and_no_overwrite(self, tmp_path: Path, key: Any) -> None:
        path = tmp_path / "k.pem"
        write_private_key(key, path)
        assert (path.stat().st_mode & 0o777) == 0o600
        with pytest.raises(FileExistsError):
            write_private_key(key, path)


# ---------------------------------------------------------------------------
# Feed format + applicability
# ---------------------------------------------------------------------------


class TestFeed:
    def test_parse(self) -> None:
        feed = parse_feed(_feed())
        assert feed.module_id == DEFAULT and len(feed.parameter_entries) == 1
        assert feed.corpus_notices[0]["source_type"] == "sgb2"

    @pytest.mark.parametrize(
        "mutate",
        [
            lambda d: d.update(serial=0),
            lambda d: d.update(entries=[]),
            lambda d: d.update(format="other"),
            lambda d: d.update(applies_to="nonsense"),
            lambda d: d["entries"].append({"kind": "code", "payload": "x"}),
        ],
    )
    def test_invalid(self, mutate: Any) -> None:
        doc = json.loads(_feed())
        mutate(doc)
        with pytest.raises(UpdateFeedError):
            parse_feed(json.dumps(doc).encode())

    def test_build_refuses_invalid(self) -> None:
        with pytest.raises(ModuleManifestError):
            build_feed(module_id="Bad", serial=1, issued_at=NOW, applies_to=">=1.0.0")

    def test_applicability(self) -> None:
        feed = parse_feed(_feed(serial=3))
        check_applicable(feed, MANIFEST, 2, NOW)
        with pytest.raises(UpdateFeedError, match="rollback"):
            check_applicable(feed, MANIFEST, 3, NOW)
        with pytest.raises(UpdateFeedError, match="not installed"):
            check_applicable(feed, None, 0, NOW)
        old = parse_feed(_feed(applies_to="<1.0.0"))
        with pytest.raises(UpdateFeedError, match="installed is"):
            check_applicable(old, MANIFEST, 0, NOW)
        future = parse_feed(_feed(issued_at=NOW + timedelta(days=3)))
        with pytest.raises(UpdateFeedError, match="future"):
            check_applicable(future, MANIFEST, 0, NOW)

    def test_feed_rows_use_module_validator(self) -> None:
        row = parse_parameter_entry(_row(), "x", "t")
        assert row.valid_from == date(2027, 1, 1)
        with pytest.raises(ModuleManifestError):
            parse_parameter_entry({**_row(), "review_status": "maybe"}, "x", "t")


# ---------------------------------------------------------------------------
# Apply (DB, rolled back)
# ---------------------------------------------------------------------------


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(os.environ["DATABASE_URL"], poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            outer = await conn.begin()
            db = AsyncSession(bind=conn, expire_on_commit=False)
            try:
                yield db
            finally:
                await db.close()
                await outer.rollback()
    finally:
        await engine.dispose()


async def test_apply_writes_rows_and_ledger(session: AsyncSession, key: Any) -> None:
    feed = _feed()
    verified = verify_feed(feed, sign_feed(feed, key), _trust(key), "mem")
    report = await apply_verified_feed(session, verified, MANIFEST, now=NOW)
    assert report.status == "applied"
    assert report.parameters[0]["action"] == "created"
    stored = (
        await session.execute(
            select(LegalParameter).where(LegalParameter.parameter_key == KEY_UNDER_TEST)
        )
    ).scalar_one()
    assert stored.value_numeric == 42.0 and stored.domain == MANIFEST.raw["parameters"]["domain"]
    ledger = (await session.execute(select(ModuleUpdate))).scalars().all()
    assert [(r.module_id, r.serial) for r in ledger] == [(DEFAULT, 1)]
    assert ledger[0].corpus_notices[0]["source_type"] == "sgb2"

    again = await apply_verified_feed(session, verified, MANIFEST, now=NOW)
    assert again.status == "already_applied"

    state = await load_applied_updates(session)
    assert state[DEFAULT].serial == 1 and state[DEFAULT].latest_valid_from == date(2027, 1, 1)

    # File re-seeding must not revert the feed's value (WP-111 precedence).
    protected = await feed_owned_parameters(session)
    stale = parse_parameter_entry(_row(value=1.0), stored.domain, "file")
    result = await upsert_parameter_rows(session, [stale], protected=protected)
    assert result.protected and not result.updated
    await session.refresh(stored)
    assert stored.value_numeric == 42.0

    # A newer correction feed replaces the value and advances the serial.
    feed2 = _feed(serial=2, parameter_rows=[_row(value=44.0)], corpus_notices=None)
    verified2 = verify_feed(feed2, sign_feed(feed2, key), _trust(key), "mem")
    report2 = await apply_verified_feed(session, verified2, MANIFEST, now=NOW)
    assert report2.parameters[0]["action"] == "updated"
    await session.refresh(stored)
    assert stored.value_numeric == 44.0
    # Replaying serial 1 (different feed bytes) is a rollback attempt.
    with pytest.raises(UpdateFeedError, match="rollback"):
        replay = _feed(serial=1, description_de="replay")
        await apply_verified_feed(
            session,
            verify_feed(replay, sign_feed(replay, key), _trust(key), "mem"),
            MANIFEST,
            now=NOW,
        )


async def test_dry_run_writes_nothing(session: AsyncSession, key: Any) -> None:
    feed = _feed()
    verified = verify_feed(feed, sign_feed(feed, key), _trust(key), "mem")
    report = await apply_verified_feed(session, verified, MANIFEST, dry_run=True, now=NOW)
    assert report.status == "dry_run" and report.parameters[0]["action"] == "pending"
    assert (await session.execute(select(ModuleUpdate))).scalars().all() == []


def test_provenance_parameter_set_includes_feeds() -> None:
    _, version, before = module_provenance(DEFAULT)
    assert before is not None and before.startswith(f"{version}+") and ".u" not in before
    try:
        set_applied_updates({DEFAULT: (3, date(2099, 1, 1))})
        assert module_provenance(DEFAULT)[2] == f"{version}+2099-01-01.u3"
        set_applied_updates({DEFAULT: (4, date(2000, 1, 1))})  # older rows: file date wins
        assert module_provenance(DEFAULT)[2] == f"{before}.u4"
    finally:
        set_applied_updates({})
    assert module_provenance(DEFAULT)[2] == before


async def test_fetch_refuses_plain_http_and_oversize(tmp_path: Path) -> None:
    with pytest.raises(UpdateFeedError, match="http://"):
        await fetch_bytes("http://example.invalid/feed.json")
    big = tmp_path / "big.json"
    big.write_bytes(b"x" * (1_048_576 + 1))
    with pytest.raises(UpdateFeedError, match="larger"):
        await fetch_bytes(str(big))

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.query == b""  # no identifying parameters
        return httpx.Response(200, content=b"x" * (1_048_576 + 10))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(UpdateFeedError, match="larger"):
            await fetch_bytes("https://example.invalid/feed.json", client=client)
