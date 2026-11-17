"""Fetch → verify → check → apply one update feed (WP-111).

Order matters and is fixed:

1. fetch feed and signature bytes (local path or ``https://`` URL; size
   capped, plain GET, no identifying headers or query parameters);
2. verify the Ed25519 signature against the trust file — *before* the feed
   is parsed; the signing key must be allowed for the feed's module;
3. parse and validate the feed; check the module is installed, its version
   lies in ``applies_to``, the serial is above every applied serial and
   ``issued_at`` is not in the future (clock skew ≤ 1 day);
4. in one transaction: upsert the parameter rows (domain = the installed
   manifest's ``parameters.domain``) and insert the ``module_update`` row.

A feed already applied (same module, serial and SHA-256) is reported as
``already_applied`` and changes nothing. ``dry_run`` stops after step 3 and
reports what step 4 would do; it still needs the database (last serial).

The running service reads the ledger at startup (provenance
``parameter_set``); after applying, restart it — as after
``scripts/seed_module_parameters.py``.
"""

# Semantic Version: 1.0.0 | 2026-11-17 — WP-111: initial version.

from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ModuleUpdate
from app.modules.parameter_seed import upsert_parameter_rows
from app.modules.parameters import ParameterRow, parse_parameter_entry
from app.modules.registry import ModuleManifest, ModuleManifestError
from app.modules.semver import in_range
from app.updates.feed import MAX_FEED_BYTES, UpdateFeed, UpdateFeedError, parse_feed
from app.updates.ledger import last_serial
from app.updates.signing import TrustedKey, UpdateTrustError, load_trust_file, verify_signature

#: Allowed clock skew for ``issued_at`` in the future.
MAX_CLOCK_SKEW = timedelta(days=1)
_FETCH_TIMEOUT = 30.0
_FETCH_ATTEMPTS = 3
_TRANSIENT = frozenset({429, 500, 502, 503, 504})


@dataclass(frozen=True)
class VerifiedFeed:
    feed: UpdateFeed
    key_id: str
    sha256: str
    source: str


@dataclass
class ApplyReport:
    module_id: str
    serial: int
    status: str  # applied | dry_run | already_applied
    key_id: str
    feed_sha256: str
    module_version: str
    parameters: list[dict[str, Any]] = field(default_factory=list)
    corpus_notices: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "module_id": self.module_id,
            "serial": self.serial,
            "status": self.status,
            "key_id": self.key_id,
            "feed_sha256": self.feed_sha256,
            "module_version": self.module_version,
            "parameters": self.parameters,
            "corpus_notices": self.corpus_notices,
        }


# ---------------------------------------------------------------------------
# Fetch
# ---------------------------------------------------------------------------


async def fetch_bytes(location: str, *, client: httpx.AsyncClient | None = None) -> bytes:
    """Read a feed or signature from a local path or an ``https://`` URL.

    Bounded: at most ``MAX_FEED_BYTES``, ``_FETCH_ATTEMPTS`` tries with
    exponential backoff on transient statuses/transport errors, one request
    in flight. ``http://`` is refused (the signature protects integrity, TLS
    protects which feed a person sees).
    """
    if location.startswith("http://"):
        raise UpdateFeedError("plain http:// is refused; use https://")
    if not location.startswith("https://"):
        path = Path(location)
        if path.stat().st_size > MAX_FEED_BYTES:
            raise UpdateFeedError(f"{location}: larger than {MAX_FEED_BYTES} bytes")
        return path.read_bytes()

    async def _get(c: httpx.AsyncClient) -> bytes:
        delay = 1.0
        for attempt in range(1, _FETCH_ATTEMPTS + 1):
            try:
                async with c.stream("GET", location) as resp:
                    if resp.status_code in _TRANSIENT and attempt < _FETCH_ATTEMPTS:
                        retry_after = resp.headers.get("Retry-After", "")
                        wait = float(retry_after) if retry_after.isdigit() else delay
                        await asyncio.sleep(min(wait, 30.0))
                        delay *= 2
                        continue
                    resp.raise_for_status()
                    chunks: list[bytes] = []
                    size = 0
                    async for chunk in resp.aiter_bytes():
                        size += len(chunk)
                        if size > MAX_FEED_BYTES:
                            raise UpdateFeedError(f"{location}: larger than {MAX_FEED_BYTES} bytes")
                        chunks.append(chunk)
                    return b"".join(chunks)
            except (httpx.TransportError, httpx.TimeoutException):
                if attempt == _FETCH_ATTEMPTS:
                    raise
                await asyncio.sleep(delay)
                delay *= 2
        raise UpdateFeedError(f"{location}: no response after {_FETCH_ATTEMPTS} attempts")

    if client is not None:
        return await _get(client)
    async with httpx.AsyncClient(follow_redirects=True, timeout=_FETCH_TIMEOUT) as c:
        return await _get(c)


# ---------------------------------------------------------------------------
# Verify + check
# ---------------------------------------------------------------------------


def verify_feed(
    feed_bytes: bytes, signature_bytes: bytes, trust: dict[str, TrustedKey], source: str
) -> VerifiedFeed:
    """Signature first, then parse; the key must be allowed for the module."""
    key = verify_signature(feed_bytes, signature_bytes, trust)
    feed = parse_feed(feed_bytes)
    if not key.may_sign_for(feed.module_id):
        raise UpdateTrustError(
            f"key {key.id} is not trusted for module {feed.module_id!r} "
            f"(allowed: {', '.join(key.modules)})"
        )
    return VerifiedFeed(feed, key.id, hashlib.sha256(feed_bytes).hexdigest(), source)


def check_applicable(
    feed: UpdateFeed, manifest: ModuleManifest | None, applied_serial: int, now: datetime
) -> None:
    """Raise ``UpdateFeedError`` unless *feed* may be applied to *manifest*."""
    if manifest is None:
        raise UpdateFeedError(f"module {feed.module_id!r} is not installed")
    if not in_range(manifest.version, feed.applies_to):
        raise UpdateFeedError(
            f"feed applies to {feed.module_id} {feed.applies_to!r}; installed is "
            f"{manifest.version}"
        )
    if feed.serial <= applied_serial:
        raise UpdateFeedError(
            f"feed serial {feed.serial} is not newer than the applied serial "
            f"{applied_serial} (rollback/replay refused)"
        )
    issued = feed.issued_at if feed.issued_at.tzinfo else feed.issued_at.replace(tzinfo=UTC)
    if issued > now + MAX_CLOCK_SKEW:
        raise UpdateFeedError(f"feed issued_at {feed.issued_at.isoformat()} lies in the future")
    if feed.parameter_entries and not isinstance(manifest.raw.get("parameters"), dict):
        raise UpdateFeedError(f"module {feed.module_id!r} declares no parameter domain")


def feed_rows(feed: UpdateFeed, manifest: ModuleManifest) -> list[tuple[str | None, ParameterRow]]:
    """``(erratum, row)`` for every parameter row, validated like file rows."""
    domain = str(manifest.raw["parameters"]["domain"])
    rows: list[tuple[str | None, ParameterRow]] = []
    seen: set[tuple[str, str]] = set()
    for erratum, entries in feed.parameter_entries:
        for index, entry in enumerate(entries):
            try:
                row = parse_parameter_entry(entry, domain, f"feed {feed.serial} row {index}")
            except ModuleManifestError as exc:
                raise UpdateFeedError(str(exc)) from exc
            identity = (row.key, row.valid_from.isoformat())
            if identity in seen:
                raise UpdateFeedError(f"feed repeats parameter {row.key}@{row.valid_from}")
            seen.add(identity)
            rows.append((erratum, row))
    return rows


# ---------------------------------------------------------------------------
# Apply
# ---------------------------------------------------------------------------


async def apply_verified_feed(
    session: AsyncSession,
    verified: VerifiedFeed,
    manifest: ModuleManifest | None,
    *,
    dry_run: bool = False,
    now: datetime | None = None,
) -> ApplyReport:
    """Check and apply *verified* in *session* (flushes; the caller commits)."""
    feed = verified.feed
    existing = (
        await session.execute(
            select(ModuleUpdate).where(
                ModuleUpdate.module_id == feed.module_id, ModuleUpdate.serial == feed.serial
            )
        )
    ).scalar_one_or_none()
    if existing is not None and existing.feed_sha256 == verified.sha256:
        return ApplyReport(
            feed.module_id,
            feed.serial,
            "already_applied",
            verified.key_id,
            verified.sha256,
            existing.module_version,
            list(existing.parameters),
            list(existing.corpus_notices),
        )
    check_applicable(
        feed, manifest, await last_serial(session, feed.module_id), now or datetime.now(UTC)
    )
    assert manifest is not None  # check_applicable raised otherwise
    rows = feed_rows(feed, manifest) if feed.parameter_entries else []
    report = ApplyReport(
        feed.module_id,
        feed.serial,
        "dry_run" if dry_run else "applied",
        verified.key_id,
        verified.sha256,
        manifest.version,
        corpus_notices=[dict(n) for n in feed.corpus_notices],
    )
    if dry_run:
        report.parameters = [
            {
                "key": r.key,
                "domain": r.domain,
                "valid_from": r.valid_from.isoformat(),
                "erratum": e,
                "action": "pending",
            }
            for e, r in rows
        ]
        return report
    result = await upsert_parameter_rows(session, [r for _, r in rows])
    report.parameters = [
        {
            "key": r.key,
            "domain": r.domain,
            "valid_from": r.valid_from.isoformat(),
            "erratum": e,
            "action": result.action((r.key, r.domain, r.valid_from)),
        }
        for e, r in rows
    ]
    session.add(
        ModuleUpdate(
            module_id=feed.module_id,
            serial=feed.serial,
            feed_sha256=verified.sha256,
            key_id=verified.key_id,
            issued_at=feed.issued_at,
            module_version=manifest.version,
            source=verified.source,
            parameters=report.parameters,
            corpus_notices=report.corpus_notices,
        )
    )
    await session.flush()
    return report


def trust_file_path() -> Path:
    """``UPDATE_TRUST_FILE`` resolved against the repository root."""
    from app.core.config import settings

    path = Path(settings.UPDATE_TRUST_FILE)
    return path if path.is_absolute() else Path(__file__).resolve().parents[2] / path


async def apply_from_location(
    feed_location: str,
    signature_location: str | None = None,
    *,
    trust_file: Path | None = None,
    modules: dict[str, ModuleManifest] | None = None,
    dry_run: bool = False,
) -> ApplyReport:
    """End-to-end: fetch, verify, check and apply (commits unless *dry_run*)."""
    from app.db.session import async_session_factory
    from app.modules.runtime import installed_modules

    trust = load_trust_file(trust_file or trust_file_path())
    feed_bytes = await fetch_bytes(feed_location)
    signature_bytes = await fetch_bytes(signature_location or f"{feed_location}.sig")
    verified = verify_feed(feed_bytes, signature_bytes, trust, feed_location)
    installed = modules if modules is not None else installed_modules()
    async with async_session_factory() as session:
        report = await apply_verified_feed(
            session, verified, installed.get(verified.feed.module_id), dry_run=dry_run
        )
        if report.status == "applied":
            await session.commit()
            from app.services.parameter_store import reload_parameter_cache

            await reload_parameter_cache(session)
        else:
            await session.rollback()
    return report


__all__ = [
    "ApplyReport",
    "VerifiedFeed",
    "apply_from_location",
    "apply_verified_feed",
    "check_applicable",
    "feed_rows",
    "fetch_bytes",
    "trust_file_path",
    "verify_feed",
]
