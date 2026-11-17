"""Ed25519 keys, signatures and the trust file of the update channel (WP-111).

Signature file (``<feed>.sig``, format ``citizen-update-signature-v1.0``)::

    {"format": "citizen-update-signature-v1.0", "algorithm": "ed25519",
     "key_id": "<16 hex>", "signature": "<base64 over the exact feed bytes>"}

The signature covers the feed file's bytes as published — no JSON
canonicalisation, so what is verified is exactly what is parsed.

Trust file (``UPDATE_TRUST_FILE``, default ``config/update-trust.yaml``,
format ``citizen-update-trust-v1.0``) lists the public keys this deployment
accepts and, per key, the module ids it may sign for (``"*"`` = all). The
repository ships it **empty**: until the maintainer publishes a key and an
operator adds it, no feed verifies. Private keys never enter the repository;
the maintainer CLI writes them to a file with mode 0600.
"""

# Semantic Version: 1.0.0 | 2026-11-17 — WP-111: initial version.

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

SIGNATURE_FORMAT = "citizen-update-signature-v1.0"
TRUST_FORMAT = "citizen-update-trust-v1.0"
ALGORITHM = "ed25519"


class UpdateTrustError(Exception):
    """Signature, key or trust-file problem — the feed must not be applied."""


def _b64decode(text: str, what: str) -> bytes:
    try:
        return base64.b64decode(text, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise UpdateTrustError(f"{what} is not valid base64") from exc


def public_key_bytes(key: Ed25519PublicKey) -> bytes:
    return key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)


def key_id_for(raw_public_key: bytes) -> str:
    """Key id: the first 16 hex digits of SHA-256 over the raw public key."""
    return hashlib.sha256(raw_public_key).hexdigest()[:16]


def generate_private_key() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.generate()


def private_key_pem(key: Ed25519PrivateKey) -> bytes:
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )


def write_private_key(key: Ed25519PrivateKey, path: Path) -> None:
    """Write *key* as PEM, readable by the owner only; never overwrite."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(private_key_pem(key))


def load_private_key(path: Path) -> Ed25519PrivateKey:
    key = serialization.load_pem_private_key(path.read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise UpdateTrustError(f"{path} is not an Ed25519 private key")
    return key


def sign_feed(feed_bytes: bytes, key: Ed25519PrivateKey) -> bytes:
    """Detached signature document (JSON bytes) for *feed_bytes*."""
    raw_public = public_key_bytes(key.public_key())
    doc = {
        "format": SIGNATURE_FORMAT,
        "algorithm": ALGORITHM,
        "key_id": key_id_for(raw_public),
        "signature": base64.b64encode(key.sign(feed_bytes)).decode("ascii"),
    }
    return (json.dumps(doc, indent=2) + "\n").encode("utf-8")


@dataclass(frozen=True)
class TrustedKey:
    id: str
    public_key: Ed25519PublicKey
    modules: tuple[str, ...]  # module ids, or ("*",)
    note: str | None

    def may_sign_for(self, module_id: str) -> bool:
        return "*" in self.modules or module_id in self.modules


def parse_trust(data: Any, where: str) -> dict[str, TrustedKey]:
    """Validate a trust document; key ids must match their public keys."""
    if not isinstance(data, dict) or data.get("format") != TRUST_FORMAT:
        raise UpdateTrustError(f"{where}: expected format {TRUST_FORMAT!r}")
    keys: dict[str, TrustedKey] = {}
    for entry in data.get("keys") or []:
        if not isinstance(entry, dict):
            raise UpdateTrustError(f"{where}: key entry is not a mapping")
        raw = _b64decode(str(entry.get("public_key", "")), f"{where}: public_key")
        if len(raw) != 32:
            raise UpdateTrustError(f"{where}: public_key must be 32 raw Ed25519 bytes")
        computed = key_id_for(raw)
        if entry.get("id") != computed:
            raise UpdateTrustError(
                f"{where}: key id {entry.get('id')!r} does not match its public key ({computed})"
            )
        modules = entry.get("modules")
        if (
            not isinstance(modules, list)
            or not modules
            or not all(isinstance(m, str) for m in modules)
        ):
            raise UpdateTrustError(f"{where}: key {computed}: `modules` must be a non-empty list")
        keys[computed] = TrustedKey(
            id=computed,
            public_key=Ed25519PublicKey.from_public_bytes(raw),
            modules=tuple(modules),
            note=entry.get("note"),
        )
    return keys


def load_trust_file(path: Path) -> dict[str, TrustedKey]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise UpdateTrustError(f"trust file {path} unreadable: {exc}") from exc
    return parse_trust(data, str(path))


def verify_signature(
    feed_bytes: bytes, signature_bytes: bytes, trust: dict[str, TrustedKey]
) -> TrustedKey:
    """Verify the detached signature; return the trusted key that made it.

    Raises ``UpdateTrustError`` for a malformed signature document, an
    unknown key id or a signature that does not verify.
    """
    try:
        doc = json.loads(signature_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UpdateTrustError("signature file is not JSON") from exc
    if not isinstance(doc, dict) or doc.get("format") != SIGNATURE_FORMAT:
        raise UpdateTrustError(f"signature file: expected format {SIGNATURE_FORMAT!r}")
    if doc.get("algorithm") != ALGORITHM:
        raise UpdateTrustError(f"signature algorithm {doc.get('algorithm')!r} not supported")
    key = trust.get(str(doc.get("key_id")))
    if key is None:
        raise UpdateTrustError(
            f"signature key {doc.get('key_id')!r} is not in the trust file "
            f"(trusted: {sorted(trust) or 'none'})"
        )
    signature = _b64decode(str(doc.get("signature", "")), "signature")
    try:
        key.public_key.verify(signature, feed_bytes)
    except InvalidSignature as exc:
        raise UpdateTrustError("signature does not verify — feed altered or wrong key") from exc
    return key


__all__ = [
    "SIGNATURE_FORMAT",
    "TRUST_FORMAT",
    "TrustedKey",
    "UpdateTrustError",
    "generate_private_key",
    "key_id_for",
    "load_private_key",
    "load_trust_file",
    "parse_trust",
    "public_key_bytes",
    "sign_feed",
    "verify_signature",
    "write_private_key",
]
