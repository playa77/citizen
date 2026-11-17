"""Module scaffold (WP-115 authoring kit; ``docs/MODULE-AUTHORING.md``).

Generates a new module package that passes ``app.modules.validate`` as
generated: manifest, corpus scope, intake row, empty deadline specs, one
example parameter (``review_status: proposed``), dossier content, errata
file, changelog, disclaimer addendum, deny-phrase list and a goldset
template. Everything legal in it is a placeholder for the module steward —
the scaffold encodes structure, never law.

Two layouts:

``in_tree``
    ``modules/<id>/`` in this repository, tier ``experimental``. Adding a
    module to the repository also means a disclaimer Part D entry and a
    ``DISCLAIMER_VERSION`` bump (``tests/unit/test_disclaimer_addenda.py``).
``out_of_tree``
    an installable package ``citizen-module-<id>/`` whose
    ``citizen.modules`` entry point names the module directory (WP-112);
    tier ``community`` (the registry clamps out-of-tree modules to it
    anyway, and they are never enabled implicitly).

The CLI wrapper is ``python -m scripts.new_module``.
"""

# Semantic Version: 1.0.0 | 2026-11-17 — WP-115: initial version.

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from app.modules.sdk import SDK_VERSION

_ID_RE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")

LAYOUT_IN_TREE = "in_tree"
LAYOUT_OUT_OF_TREE = "out_of_tree"


class ScaffoldError(ValueError):
    """Invalid scaffold request (bad id, existing target, …)."""


@dataclass(frozen=True)
class ScaffoldResult:
    module_dir: Path  # directory holding module.yaml
    package_dir: Path | None  # out-of-tree: the installable project root
    files: tuple[Path, ...]


def used_area_orders(modules_root: Path | None = None) -> set[int]:
    """Every area-key ``order`` in use: core procedural library + installed modules."""
    import yaml

    from app.modules.areas import PROCEDURAL_DIR
    from app.modules.content import load_section
    from app.modules.registry import default_modules_root, discover_installed_modules

    sections = [yaml.safe_load((PROCEDURAL_DIR / "intake.yaml").read_text(encoding="utf-8"))]
    modules, _rejected = discover_installed_modules(modules_root or default_modules_root())
    sections.extend(load_section(m, "intake") for m in modules.values())
    used: set[int] = set()
    for section in sections:
        areas = section.get("areas") if isinstance(section, dict) else None
        for entry in (areas or {}).values():
            rank = (entry or {}).get("order")
            if isinstance(rank, int) and not isinstance(rank, bool):
                used.add(rank)
    return used


def next_free_order(used: set[int], step: int = 10) -> int:
    """The next area-key ``order`` above every used value, on a *step* grid."""
    top = max(used, default=0)
    return (top // step + 1) * step


def _files(
    module_id: str, title_de: str, title_en: str, tier: str, order: int, today: date
) -> dict[str, str]:
    year = today.year
    core_major = SDK_VERSION.split(".")[0]
    return {
        "module.yaml": f"""\
# {title_de} — module scaffolded {today.isoformat()} (WP-115 authoring kit).
# Fill every placeholder, then run:  python -m scripts.validate_module <dir>
# Authoring guide: docs/MODULE-AUTHORING.md (Citizen core repository).

# Semantic Version: 0.1.0 | {today.isoformat()} — scaffold

id: {module_id}
version: 0.1.0
core_api: ">={SDK_VERSION},<{int(core_major) + 1}.0"
title:
  de: "{title_de}"
  en: "{title_en}"
tier: {tier}
scope:
  summary_de: "TODO: Geltungsbereich in einem Satz (welche Gesetze, welche Schreiben)"
  own_matter_only: true
  out_of_scope: []
corpus: corpus.yaml
intake: intake.yaml
parameters:
  domain: {module_id}
  files: [parameters/*.yaml]
fristen: fristen.yaml
dossier: dossier.yaml
errata: errata.yaml
goldset:
  path: goldset/goldset-v0.1.0.yaml
compliance:
  purpose_drift_deny_file: compliance/deny-phrases.json
  special_regimes: []
  disclaimer_addendum: DISCLAIMER_ADDENDUM.md
legacy_aliases: []
""",
        "corpus.yaml": f"""\
# Corpus scope of module `{module_id}` (ARCHITECTURE.md § 3.3).
# `areas.<key>.source_types`: corpus source types (core source catalog keys)
# that satisfy the area — pre-flight readiness and retrieval filter.
# Optional `case_law` (verified modules only, WP-113): see MODULE-AUTHORING.md.

areas:
  {module_id}:
    source_types: []
""",
        "intake.yaml": f"""\
# Intake tables of module `{module_id}` (ARCHITECTURE.md § 3.8).
# `order` ranks the area key in the global area-key order (unique across all
# installed modules; the scaffold picked the next free value).

areas:
  {module_id}:
    order: {order}
    keywords: []
""",
        "fristen.yaml": """\
# Deadline specs (ARCHITECTURE.md § 2.3) — data evaluated by the Fristen core.
# Each spec needs golden date tests before the module is promoted. Example:
#
# - id: einspruch_beispiel
#   label_de: "Einspruchsfrist"
#   trigger: zustellung
#   bekanntgabe_fiction: none
#   duration: { days: 14 }
#   rollover: bgb_193
#   basis: "§ … …"
#   severity: critical
[]
""",
        f"parameters/{year}.yaml": f"""\
# Versioned legal parameters of module `{module_id}` (ARCHITECTURE.md § 3.4).
# Every value needs a source (`basis`) and a parameter steward's review
# (`review_status: verified`). Updates between releases travel on the signed
# update channel (WP-111).

parameters:
  - key: {module_id}.beispiel.betrag
    value_numeric: 0
    unit: EUR
    valid_from: {year}-01-01
    review_status: proposed
    basis: "TODO: Fundstelle"
    notes: "Scaffold placeholder — replace or delete."
""",
        "dossier.yaml": f"""\
# Appointment dossier content of module `{module_id}` (ARCHITECTURE.md § 3.7).
# Copy speaks to the person ("Sie") preparing their own appointment.

format: citizen-module-dossier-v1.0
checklist:
  - id: schreiben_vollstaendig
    label_de: "Das Schreiben, um das es geht — vollständig, mit allen Seiten und Anlagen"
    why_de: "Die Beratung braucht den genauen Wortlaut."
    topic: kernunterlagen
    required: true
questions:
  - id: frist_bestaetigen
    text_de: "Welche Frist läuft in meinem Fall, und bis wann muss ich handeln?"
    topic: fristen
""",
        "errata.yaml": f"""\
# Errata of module `{module_id}` (WP-110; citizen-module-errata-v1.0).
# A PATCH that corrects a wrong value, deadline or copy adds one entry here.

format: citizen-module-errata-v1.0
errata: []
""",
        "goldset/goldset-v0.1.0.yaml": f"""\
# Goldset of module `{module_id}` — verified SYNTHETIC cases only (D-020).
# A module is promoted to `verified` only with >= 15 cases and a published
# eval report (roadmap § 7, sub-WP .8). Case shape (see the default
# module's goldset for complete examples):
#
# - id: GS-001
#   version: 1.0.0
#   title: "…"
#   category: …
#   difficulty: leicht|mittel|schwer
#   input_document: {{type: text, text: "…synthetic letter…"}}
#   expected:
#     overall_assessment: …
#     summary: "…"
#     legal_issues: [{{id: GS-001-I1, issue: "…", assessment: …}}]
#     citations: [{{norm: "§ … …", rolle: "…"}}]
#     known_traps: ["…"]
#   pii_annotations: []
#   negative_controls: []

goldset:
  id: goldset-{module_id}
  version: 0.1.0
  schema_version: 1.0.0
  created: {today.isoformat()}
  legal_area: {module_id}
  jurisdiction: DE
  language: de
  case_count: 0
  provenance: synthetic
cases: []
""",
        "compliance/deny-phrases.json": json.dumps([], indent=2) + "\n",
        "DISCLAIMER_ADDENDUM.md": f"""\
# Disclaimer addendum — module `{module_id}`

Area-specific limits of the module (ARCHITECTURE.md § 7). The `## DE` and
`## EN` bodies are copied verbatim into Part D of the disclaimer for in-tree
modules.

## DE

**Geltungsbereich.** TODO: Was das Modul behandelt, was nicht, und wann eine
Beratungsstelle oder Anwältin/Anwalt unverzichtbar ist.

## EN

**Scope.** TODO: what the module covers, what it does not, and when an
advice centre or lawyer is indispensable.
""",
        "CHANGELOG.md": f"""\
# Changelog — module `{module_id}`

Module semver (ARCHITECTURE.md § 6.2), independent of the core version.

## 0.1.0 — {today.isoformat()}

- Scaffolded with the WP-115 authoring kit (tier `{tier}`).
""",
    }


def _package_files(module_id: str, title_en: str) -> dict[str, str]:
    pkg = f"citizen_module_{module_id}"
    return {
        "pyproject.toml": f"""\
[build-system]
requires = ["setuptools>=68.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "citizen-module-{module_id.replace("_", "-")}"
version = "0.1.0"
description = "Citizen out-of-tree module: {title_en}"
requires-python = ">=3.11"
license = {{text = "MIT"}}

# WP-112: the core discovers this module through this entry point and loads it
# at tier `community` (opt-in via ENABLED_MODULES only).
[project.entry-points."citizen.modules"]
{module_id} = "{pkg}"

[tool.setuptools]
packages = ["{pkg}"]

[tool.setuptools.package-data]
{pkg} = ["*.yaml", "*.md", "*/*.yaml", "*/*.json", "CHANGELOG.md"]
""",
        "README.md": f"""\
# citizen-module-{module_id}

Out-of-tree module for Citizen (`citizen.modules` entry point, tier
`community`). Install it into the Citizen environment, validate it, and
enable it explicitly:

    pip install -e .
    python -m scripts.validate_module --module {module_id}
    ENABLED_MODULES='["<default module>", "{module_id}"]'
""",
        f"{pkg}/__init__.py": f'''\
"""Citizen out-of-tree module `{module_id}`: data package (no code needed).

The entry point names this package; the core loads the module from this
directory (module.yaml beside this file).
"""
''',
    }


def scaffold_module(
    module_id: str,
    *,
    title_de: str,
    title_en: str,
    dest: Path,
    layout: str = LAYOUT_IN_TREE,
    used_orders: set[int] | None = None,
    modules_root: Path | None = None,
    today: date | None = None,
) -> ScaffoldResult:
    """Write a new module skeleton under *dest*; refuse to overwrite anything.

    The area-key ``order`` is the next free value above *used_orders*, or —
    when not given — above every order the installed modules (under
    *modules_root*) and the core procedural library use.
    """
    if not _ID_RE.match(module_id):
        raise ScaffoldError(f"invalid module id {module_id!r} (pattern {_ID_RE.pattern})")
    if layout not in (LAYOUT_IN_TREE, LAYOUT_OUT_OF_TREE):
        raise ScaffoldError(f"unknown layout {layout!r}")
    today = today or date.today()
    if used_orders is None:
        used_orders = used_area_orders(modules_root)
    order = next_free_order(used_orders)
    if layout == LAYOUT_IN_TREE:
        package_dir = None
        module_dir = dest / module_id
        tier = "experimental"
        root = module_dir
    else:
        package_dir = dest / f"citizen-module-{module_id.replace('_', '-')}"
        module_dir = package_dir / f"citizen_module_{module_id}"
        tier = "community"
        root = package_dir
    if root.exists():
        raise ScaffoldError(f"target {root} already exists — refusing to overwrite")

    written: list[Path] = []
    contents = {
        module_dir / rel: text
        for rel, text in _files(module_id, title_de, title_en, tier, order, today).items()
    }
    if package_dir is not None:
        contents.update(
            {package_dir / rel: text for rel, text in _package_files(module_id, title_en).items()}
        )
    for path, text in contents.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        written.append(path)
    return ScaffoldResult(module_dir=module_dir, package_dir=package_dir, files=tuple(written))


__all__ = [
    "LAYOUT_IN_TREE",
    "LAYOUT_OUT_OF_TREE",
    "ScaffoldError",
    "ScaffoldResult",
    "next_free_order",
    "used_area_orders",
    "scaffold_module",
]
