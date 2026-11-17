"""Update feed format ``citizen-update-feed-v1.0`` (WP-111).

Parsing happens only *after* the signature verified (``app.updates.apply``):
an unverified feed is opaque bytes. ``parse_feed`` then checks the schema,
the version range syntax and every parameter row with the same validator
the module parameter files use.
"""

# Semantic Version: 1.0.0 | 2026-11-17 — WP-111: initial version.

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from app.modules.registry import ModuleManifestError
from app.modules.semver import VersionRangeError, validate_range

FEED_FORMAT = "citizen-update-feed-v1.0"
FEED_SCHEMA_PATH = Path(__file__).with_name("update-feed.schema.json")
#: Feeds are small (a parameter set, some notices); anything larger is refused
#: before it is read into memory completely.
MAX_FEED_BYTES = 1_048_576


class UpdateFeedError(Exception):
    """A verified feed that is malformed or does not apply here."""


@dataclass(frozen=True)
class UpdateFeed:
    module_id: str
    serial: int
    issued_at: datetime
    applies_to: str
    description_de: str | None
    parameter_entries: tuple[tuple[str | None, tuple[dict[str, Any], ...]], ...]  # (erratum, rows)
    corpus_notices: tuple[dict[str, Any], ...]
    raw: dict[str, Any]


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    schema = json.loads(FEED_SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def parse_feed(feed_bytes: bytes) -> UpdateFeed:
    """Parse and validate verified feed bytes."""
    if len(feed_bytes) > MAX_FEED_BYTES:
        raise UpdateFeedError(f"feed larger than {MAX_FEED_BYTES} bytes")
    try:
        data = json.loads(feed_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UpdateFeedError(f"feed is not UTF-8 JSON: {exc}") from exc
    errors = sorted(_validator().iter_errors(data), key=lambda e: list(e.path))
    if errors:
        details = "; ".join(
            f"{'/'.join(str(p) for p in e.path) or '<root>'}: {e.message}" for e in errors[:5]
        )
        raise UpdateFeedError(f"feed violates {FEED_FORMAT}: {details}")
    try:
        validate_range(data["applies_to"])
    except VersionRangeError as exc:
        raise UpdateFeedError(f"applies_to: {exc}") from exc
    issued_at = datetime.fromisoformat(data["issued_at"].replace("Z", "+00:00"))
    parameters: list[tuple[str | None, tuple[dict[str, Any], ...]]] = []
    notices: list[dict[str, Any]] = []
    for entry in data["entries"]:
        if entry["kind"] == "parameters":
            parameters.append((entry.get("erratum"), tuple(entry["rows"])))
        else:
            notices.append({k: v for k, v in entry.items() if k != "kind"})
    return UpdateFeed(
        module_id=data["module_id"],
        serial=int(data["serial"]),
        issued_at=issued_at,
        applies_to=data["applies_to"],
        description_de=data.get("description_de"),
        parameter_entries=tuple(parameters),
        corpus_notices=tuple(notices),
        raw=data,
    )


def build_feed(
    *,
    module_id: str,
    serial: int,
    issued_at: datetime,
    applies_to: str,
    parameter_rows: list[dict[str, Any]] | None = None,
    erratum: str | None = None,
    corpus_notices: list[dict[str, Any]] | None = None,
    description_de: str | None = None,
) -> bytes:
    """Maintainer helper: serialise a feed (validated by round-tripping it)."""
    entries: list[dict[str, Any]] = []
    if parameter_rows:
        entry: dict[str, Any] = {"kind": "parameters", "rows": parameter_rows}
        if erratum:
            entry["erratum"] = erratum
        entries.append(entry)
    for notice in corpus_notices or []:
        entries.append({"kind": "corpus_notice", **notice})
    doc: dict[str, Any] = {
        "format": FEED_FORMAT,
        "module_id": module_id,
        "serial": serial,
        "issued_at": issued_at.isoformat().replace("+00:00", "Z"),
        "applies_to": applies_to,
    }
    if description_de:
        doc["description_de"] = description_de
    doc["entries"] = entries
    payload = (json.dumps(doc, indent=2, ensure_ascii=False, default=str) + "\n").encode("utf-8")
    try:
        parse_feed(payload)
    except UpdateFeedError as exc:
        raise ModuleManifestError(f"refusing to build an invalid feed: {exc}") from exc
    return payload


__all__ = [
    "FEED_FORMAT",
    "MAX_FEED_BYTES",
    "UpdateFeed",
    "UpdateFeedError",
    "build_feed",
    "parse_feed",
]
