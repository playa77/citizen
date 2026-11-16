"""Disclaimer v3.0.0 consistency guards (WP-96, D-059).

- Part D carries every module addendum verbatim (the `## DE` / `## EN` bodies
  of ``modules/<id>/DISCLAIMER_ADDENDUM.md``), so an addendum cannot change
  without the compiled disclaimer changing too.
- Part D names every installed module, so a new module cannot ship without a
  disclaimer revision (ARCHITECTURE.md § 6.3: the disclaimer version bumps
  with the module set).
- The DE and EN documents carry the same version, their newest change-history
  entry is that version, and the shipped ``DISCLAIMER_VERSION`` default is
  ``"v" + <document version>``.
"""

# Semantic Version: 1.0.0 | 2026-11-16 — WP-96.

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.core.config import Settings
from app.modules.registry import default_modules_root, discover_modules

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCS = {
    "de": (REPO_ROOT / "DISCLAIMER_DE.md", "## Teil D", "## Änderungshistorie"),
    "en": (REPO_ROOT / "DISCLAIMER_EN.md", "## Part D", "## Change History"),
}
MODULES = discover_modules(default_modules_root())


def _normalize(text: str) -> str:
    """Collapse whitespace so line wrapping does not matter."""
    return " ".join(text.split())


def _part_d(lang: str) -> str:
    path, start, end = DOCS[lang]
    text = path.read_text(encoding="utf-8")
    assert start in text, f"{path.name}: {start!r} missing"
    return text[text.index(start) : text.index(end)]


def _addendum_body(path: Path, lang: str) -> str:
    text = path.read_text(encoding="utf-8")
    match = re.search(r"^## DE\n(.*?)^## EN\n(.*)\Z", text, flags=re.S | re.M)
    assert match, f"{path}: needs a '## DE' section followed by an '## EN' section"
    body = match.group(1 if lang == "de" else 2).strip()
    assert body, f"{path}: empty {lang.upper()} section"
    return body


ADDENDA = [
    (module_id, manifest.path / manifest.raw["compliance"]["disclaimer_addendum"])
    for module_id, manifest in sorted(MODULES.items())
    if isinstance(manifest.raw.get("compliance"), dict)
    and "disclaimer_addendum" in manifest.raw["compliance"]
]


def test_shipped_modules_declare_addenda() -> None:
    # Pins the WP-96 set; a module dropping its addendum must be deliberate.
    assert {module_id for module_id, _ in ADDENDA} >= {"sozialrecht", "strafrecht"}


@pytest.mark.parametrize("lang", ["de", "en"])
@pytest.mark.parametrize(("module_id", "path"), ADDENDA, ids=[m for m, _ in ADDENDA])
def test_part_d_contains_addendum_verbatim(module_id: str, path: Path, lang: str) -> None:
    body = _normalize(_addendum_body(path, lang))
    assert body in _normalize(_part_d(lang)), (
        f"{DOCS[lang][0].name} Part D does not contain the {lang.upper()} addendum of "
        f"{module_id!r} verbatim — copy it and bump DISCLAIMER_VERSION"
    )


@pytest.mark.parametrize("lang", ["de", "en"])
def test_part_d_names_every_installed_module(lang: str) -> None:
    part_d = _part_d(lang)
    missing = [module_id for module_id in MODULES if f"`{module_id}`" not in part_d]
    assert not missing, f"{DOCS[lang][0].name} Part D does not name: {missing}"


def _document_version(lang: str) -> str:
    text = DOCS[lang][0].read_text(encoding="utf-8")
    match = re.search(r"^\*\*Version:\*\* (\d+\.\d+\.\d+)", text, flags=re.M)
    assert match, f"{DOCS[lang][0].name}: no '**Version:** X.Y.Z' header"
    return match.group(1)


def test_versions_are_aligned() -> None:
    version = _document_version("de")
    assert _document_version("en") == version
    # Newest change-history entry documents the current version.
    for lang in ("de", "en"):
        path, _, history = DOCS[lang]
        text = path.read_text(encoding="utf-8")
        tail = text[text.index(history) :]
        newest = re.search(r"^- \*\*(\d+\.\d+\.\d+) ", tail, flags=re.M)
        assert newest and newest.group(1) == version, f"{path.name}: history not at {version}"
    # The ack version clients must send is the document version (B.12).
    assert Settings.model_fields["DISCLAIMER_VERSION"].default == f"v{version}"
