"""WP-102 — module dossier content (dossier.yaml) and the multi-module merge."""

# Semantic Version: 1.0.0 | 2026-11-16 — P10

from __future__ import annotations

import copy
from typing import Any

import pytest
import yaml

from app.dossier.module_content import (
    ModuleDossier,
    module_dossier,
    public_dossier_checklist,
    select_checklist,
    select_questions,
    validate_module_dossier,
)
from app.modules.registry import ModuleManifestError, default_modules_root, discover_modules
from app.modules.runtime import get_manifest

INSTALLED = discover_modules(default_modules_root())


def _raw(module_id: str = "sozialrecht") -> dict[str, Any]:
    manifest = get_manifest(module_id)
    data: dict[str, Any] = yaml.safe_load(
        (manifest.path / str(manifest.raw["dossier"])).read_text(encoding="utf-8")
    )
    return data


def test_every_declared_dossier_is_valid() -> None:
    declared = [m for m, man in INSTALLED.items() if isinstance(man.raw.get("dossier"), str)]
    assert "sozialrecht" in declared
    for module_id in declared:
        content = module_dossier(module_id)
        assert content is not None
        assert content.goldset_path is None or content.goldset_path.is_file()


def test_sozialrecht_content_shape() -> None:
    content = module_dossier("sozialrecht")
    assert content is not None
    required_always = {i["id"] for i in content.checklist if i["required"] and "when" not in i}
    assert {"bescheid_vollstaendig", "zugang_nachweis"} <= required_always
    assert {c.kind for c in content.cues} >= {"antrag", "termin", "zugang"}
    assert content.gate["deadline_completeness_min"] == 1.0


@pytest.mark.parametrize(
    "mutate, message",
    [
        (lambda d: d.update(format="v0"), "format"),
        (lambda d: d["checklist"].append(copy.deepcopy(d["checklist"][0])), "duplicate checklist"),
        (lambda d: d["checklist"][0].update(required="yes"), "required"),
        (lambda d: d["questions"][0].update(when={"any_keyword": []}), "when"),
        (lambda d: d.update(extra=True), "extra"),
    ],
)
def test_schema_rejects_invalid_content(mutate: Any, message: str) -> None:
    data = _raw()
    mutate(data)
    with pytest.raises(ModuleManifestError, match=message):
        validate_module_dossier(data, context="test")


def _content(module_id: str, checklist: list[dict[str, Any]]) -> ModuleDossier:
    return ModuleDossier(module_id, tuple(checklist), (), (), None)


def test_merge_key_deduplicates_across_modules_in_order() -> None:
    a = _content(
        "a",
        [
            {"id": "id_a", "label_de": "Ausweis", "required": True, "merge_key": "ausweis"},
            {"id": "only_a", "label_de": "A", "required": False},
        ],
    )
    b = _content(
        "b",
        [
            {"id": "id_b", "label_de": "Ausweis (B)", "required": True, "merge_key": "ausweis"},
            {"id": "kw", "label_de": "K", "required": True, "when": {"any_keyword": ["Miete"]}},
        ],
    )
    items = select_checklist([a, b], ["Die MIETE beträgt"])
    assert [(i["id"], i["modules"]) for i in items] == [
        ("id_a", ["a", "b"]),
        ("only_a", ["a"]),
        ("kw", ["b"]),
    ]
    assert [i["id"] for i in select_checklist([a, b], ["nichts"])] == ["id_a", "only_a"]


def test_questions_select_by_keyword() -> None:
    content = module_dossier("sozialrecht")
    assert content is not None
    plain = {q["id"] for q in select_questions([content], ["Ein Schreiben."])}
    with_kdu = {q["id"] for q in select_questions([content], ["Ihre Heizkosten"])}
    assert "unterkunft_angemessen" in with_kdu - plain
    assert all(q["origin"] == "module" for q in select_questions([content], ["x"]))


def test_public_checklist_for_module_api() -> None:
    public = public_dossier_checklist("sozialrecht")
    assert public is not None
    assert public["format"] == "citizen-module-dossier-v1.0"
    assert public["checklist"] and public["questions"]
    stubs = [m for m, man in INSTALLED.items() if "dossier" not in man.raw]
    assert stubs and public_dossier_checklist(stubs[0]) is None
