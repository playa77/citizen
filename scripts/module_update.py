#!/usr/bin/env python3
"""Signed module update channel CLI (WP-111; ``app/updates``).

Maintainer side (offline, no database)::

    python -m scripts.module_update keygen --out release-key.pem
    python -m scripts.module_update make --module sozialrecht --serial 1 \\
        --applies-to ">=1.4.0,<2.0.0" --parameters fix.yaml [--erratum E-2027-001] \\
        [--notice notice.yaml] --out sozialrecht-update-1.json
    python -m scripts.module_update sign sozialrecht-update-1.json --key release-key.pem
    python -m scripts.module_update verify sozialrecht-update-1.json [--trust FILE]

Operator side (database)::

    python -m scripts.module_update apply <feed path|https URL> [--sig …] [--dry-run]
    python -m scripts.module_update status [--module ID]

``make`` reads parameter rows in the module parameter-file format
(``parameters: [...]``) and corpus notices as a YAML list. Publish the feed
and its ``.sig`` as static files (e.g. GitHub release assets). After
``apply``, restart the service so provenance ``parameter_set`` ids include
the feed. The private key is written with mode 0600 and never printed.

Exit codes: 0 success (incl. ``already_applied``), 1 refused (signature,
trust, feed or applicability problem), 2 usage/IO/database error.
"""

# Version: 2026-11-17.1 (WP-111)

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from app.updates.feed import UpdateFeedError, build_feed
from app.updates.signing import (
    UpdateTrustError,
    generate_private_key,
    key_id_for,
    load_private_key,
    load_trust_file,
    public_key_bytes,
    sign_feed,
    write_private_key,
)

logger = logging.getLogger("module_update")


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _trust_path(arg: str | None) -> Path:
    if arg:
        return Path(arg)
    from app.updates.apply import trust_file_path

    return trust_file_path()


def cmd_keygen(args: argparse.Namespace) -> int:
    key = generate_private_key()
    write_private_key(key, Path(args.out))
    raw = public_key_bytes(key.public_key())
    entry = {
        "id": key_id_for(raw),
        "public_key": base64.b64encode(raw).decode("ascii"),
        "modules": ["*"],
        "note": "TODO: describe this key",
    }
    print(f"private key written to {args.out} (mode 0600) — keep it out of the repository")
    print("trust-file entry (config/update-trust.yaml `keys:`):")
    print(yaml.safe_dump([entry], sort_keys=False, allow_unicode=True), end="")
    return 0


def cmd_make(args: argparse.Namespace) -> int:
    rows: list[dict[str, Any]] = []
    if args.parameters:
        data = yaml.safe_load(Path(args.parameters).read_text(encoding="utf-8"))
        rows = _jsonable((data or {}).get("parameters") or [])
    notices: list[dict[str, Any]] = []
    if args.notice:
        notices = _jsonable(yaml.safe_load(Path(args.notice).read_text(encoding="utf-8")) or [])
    payload = build_feed(
        module_id=args.module,
        serial=args.serial,
        issued_at=datetime.now(UTC).replace(microsecond=0),
        applies_to=args.applies_to,
        parameter_rows=rows,
        erratum=args.erratum,
        corpus_notices=notices,
        description_de=args.description,
    )
    out = Path(args.out)
    if out.exists():
        print(f"refused: {out} exists", file=sys.stderr)
        return 2
    out.write_bytes(payload)
    print(f"feed written to {out} ({len(rows)} parameter row(s), {len(notices)} notice(s))")
    return 0


def cmd_sign(args: argparse.Namespace) -> int:
    feed = Path(args.feed)
    sig = Path(args.out or f"{args.feed}.sig")
    if sig.exists():
        print(f"refused: {sig} exists", file=sys.stderr)
        return 2
    sig.write_bytes(sign_feed(feed.read_bytes(), load_private_key(Path(args.key))))
    print(f"signature written to {sig}")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    from app.updates.apply import verify_feed

    feed_bytes = Path(args.feed).read_bytes()
    sig_bytes = Path(args.sig or f"{args.feed}.sig").read_bytes()
    verified = verify_feed(
        feed_bytes, sig_bytes, load_trust_file(_trust_path(args.trust)), args.feed
    )
    feed = verified.feed
    print(
        f"verified: module {feed.module_id} serial {feed.serial}, key {verified.key_id}, "
        f"applies to {feed.applies_to!r}, sha256 {verified.sha256}"
    )
    return 0


def cmd_apply(args: argparse.Namespace) -> int:
    from app.updates.apply import apply_from_location

    report = asyncio.run(
        apply_from_location(
            args.feed,
            args.sig,
            trust_file=_trust_path(args.trust),
            dry_run=args.dry_run,
        )
    )
    print(json.dumps(report.as_dict(), indent=2, ensure_ascii=False))
    if report.status == "applied":
        print("applied — restart the service so provenance includes the feed", file=sys.stderr)
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    async def _run() -> list[dict[str, Any]]:
        from sqlalchemy import select

        from app.db.models import ModuleUpdate
        from app.db.session import async_session_factory

        async with async_session_factory() as session:
            query = select(ModuleUpdate).order_by(ModuleUpdate.module_id, ModuleUpdate.serial)
            if args.module:
                query = query.where(ModuleUpdate.module_id == args.module)
            rows = (await session.execute(query)).scalars().all()
        return [
            {
                "module_id": r.module_id,
                "serial": r.serial,
                "applied_at": r.applied_at.isoformat(),
                "key_id": r.key_id,
                "module_version": r.module_version,
                "parameters": len(r.parameters),
                "corpus_notices": len(r.corpus_notices),
                "source": r.source,
            }
            for r in rows
        ]

    print(json.dumps(asyncio.run(_run()), indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("keygen", help="new Ed25519 release key (maintainer)")
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_keygen)

    p = sub.add_parser("make", help="build a feed from parameter rows / notices (maintainer)")
    p.add_argument("--module", required=True)
    p.add_argument("--serial", type=int, required=True)
    p.add_argument("--applies-to", required=True)
    p.add_argument("--parameters", help="YAML file with `parameters: [...]` rows")
    p.add_argument("--erratum", help="erratum id the parameter rows correct")
    p.add_argument("--notice", help="YAML list of corpus notices")
    p.add_argument("--description", help="description_de")
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_make)

    p = sub.add_parser("sign", help="detached signature for a feed (maintainer)")
    p.add_argument("feed")
    p.add_argument("--key", required=True)
    p.add_argument("--out")
    p.set_defaults(func=cmd_sign)

    for name, func, helptext in (
        ("verify", cmd_verify, "verify signature + format, offline"),
        ("apply", cmd_apply, "verify, check and apply a feed (database)"),
    ):
        p = sub.add_parser(name, help=helptext)
        p.add_argument("feed", help="path or https URL")
        p.add_argument("--sig", help="signature path/URL (default: <feed>.sig)")
        p.add_argument("--trust", help="trust file (default: UPDATE_TRUST_FILE)")
        if name == "apply":
            p.add_argument("--dry-run", action="store_true")
        p.set_defaults(func=func)

    p = sub.add_parser("status", help="applied feeds (database)")
    p.add_argument("--module")
    p.set_defaults(func=cmd_status)

    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )
    try:
        return int(args.func(args))
    except (UpdateTrustError, UpdateFeedError) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # IO/DB errors: report, no partial-success claim
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
