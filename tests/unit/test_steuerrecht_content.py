"""Tax preparation contracts: own-matter scope, guarded drafts and content gates."""

import json
import shutil
from pathlib import Path

import pytest
import yaml

from app.modules.catalog import public_scope
from app.modules.registry import discover_modules
from app.modules.validate import validate_module_dir

ROOT = Path("modules/steuerrecht")


def data(name):
    assert (ROOT / name).exists(), f"Missing tax module content: {name}"
    return yaml.safe_load((ROOT / name).read_text())


def test_tax_manifest_is_experimental_own_matter_without_assistance():
    raw = data("module.yaml")
    assert raw["tier"] == "experimental"
    assert raw["scope"]["own_matter_only"] is True
    assert raw["scope"]["third_party_assistance"] is False
    manifest = discover_modules(Path("modules"))["steuerrecht"]
    assert public_scope(manifest)["third_party_assistance"] is False
    assert "third_party_assistance" not in public_scope(
        discover_modules(Path("modules"))["sozialrecht"]
    )


@pytest.mark.parametrize("value", [True, None])
def test_tax_assistance_boundary_is_validated(tmp_path, value):
    data("module.yaml")
    target = tmp_path / "steuerrecht"
    shutil.copytree(ROOT, target)
    manifest = data("module.yaml")
    if value is None:
        manifest["scope"].pop("third_party_assistance")
    else:
        manifest["scope"]["third_party_assistance"] = value
    (target / "module.yaml").write_text(yaml.safe_dump(manifest))
    report = validate_module_dir(target, tmp_path)
    assert any("third_party_assistance" in e for e in report.errors)


def test_guarded_tax_drafts_cover_three_requested_remedies():
    templates = data("documents/templates.yaml")["templates"]
    assert set(templates) == {"einspruch", "aussetzung", "aenderung"}
    for row in templates.values():
        text = "\n".join(p.get("text", "") for p in row["parts"])
        assert "[BITTE PRÜFEN" in text
        assert "Entwurf" in text and "keine automatische" in text.lower()
        assert "Zahlung" in text
    assert "§361 AO" in str(templates["aussetzung"])
    assert "§172 AO" in str(templates["aenderung"])


def test_plain_copy_languages_remain_draft_and_keep_urgent_referral():
    for language in ("de", "en", "de-LS"):
        doc = data(f"copy/{language}/plain.yaml")
        assert doc["review"]["status"] == "draft"
        assert doc["deadlines"]["steuerrecht_einspruch"]["referral_when_not_applicable"] is True


def test_synthetic_goldset_has_at_least_fifteen_distinct_cases():
    goldset = data("goldset/goldset-v0.1.0.yaml")
    cases = goldset["cases"]
    assert len(cases) >= 15
    assert len({c["id"] for c in cases}) == len(cases)
    assert goldset["goldset"]["provenance"] == "synthetic"
    assert all(c["expected"]["known_traps"] for c in cases)


def test_dossier_minimises_identifiers_and_asks_tax_specific_questions():
    dossier = data("dossier.yaml")
    assert {"bescheid", "erklaerung", "zahlung", "datenschutz"} <= {
        r["id"] for r in dossier["checklist"]
    }
    assert any("Aussetzung" in q["text_de"] for q in dossier["questions"])
    deny = json.loads((ROOT / "compliance/deny-phrases.json").read_text())
    assert "Steuerberatung für Mandanten" in deny


@pytest.mark.asyncio
async def test_module_detail_serves_scope_and_minimised_schema_without_selection():
    from app.api.routes.modules import get_module
    from app.db.session import engine
    from app.modules.runtime import request_modules

    try:
        body = await get_module("steuerrecht")
    finally:
        await engine.dispose()
    assert body["scope"]["third_party_assistance"] is False
    assert body["intake_schema"]["properties"]["own_matter_confirmed"]["const"] is True
    assert body["intake_schema"]["additionalProperties"] is False
    assert request_modules([]) == []


@pytest.mark.parametrize("doc_type", ["einspruch", "aussetzung", "aenderung"])
def test_rendered_action_drafts_keep_unconfirmed_assertions(doc_type):
    from app.services.document_generators import generate_document

    document = generate_document(doc_type, None, [], [], module_id="steuerrecht")
    assert "[BITTE PRÜFEN" in document.rendered_text
    assert document.provenance is not None
    assert "keine automatische" in document.rendered_text


def test_goldset_deadline_outcomes_include_missing_date_refusals():
    from app.dossier.deadlines import ModuleSpecs, compute_deadlines
    from app.fristen.specs import load_specs

    specs = [ModuleSpecs("steuerrecht", tuple(load_specs(ROOT / "fristen.yaml")))]
    for case in data("goldset/dossier-goldset-v1.0.0.yaml")["cases"]:
        item = compute_deadlines(specs, case["facts"], [])["items"][0]
        expected = case["expected"]["deadlines"]
        if expected:
            assert item["frist_ende"] == expected[0]["frist_ende"], case["id"]
        else:
            assert item["status"] == "missing_input" and item["frist_ende"] is None, case["id"]
