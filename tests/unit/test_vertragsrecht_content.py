"""Consumer contract content must retain evidence and exceptional-regime guards."""

from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

from app.dossier.deadlines import ModuleSpecs, compute_deadlines
from app.fristen.specs import load_specs

ROOT = Path(__file__).resolve().parents[2] / "modules/vertragsrecht"


def _data(name):
    return yaml.safe_load((ROOT / name).read_text())


def test_all_literal_goldset_deadlines_and_guards():
    specs = [ModuleSpecs("vertragsrecht", tuple(load_specs(ROOT / "fristen.yaml")))]
    for case in _data("goldset/dossier-goldset-v1.0.0.yaml")["cases"]:
        section = compute_deadlines(specs, case["facts"], [])
        actual = {
            i["spec_id"]: i["frist_ende"] for i in section["items"] if i["status"] == "computed"
        }
        assert actual == {
            i["spec_id"]: i["frist_ende"] for i in case["expected"]["deadlines"]
        }, case["id"]


@pytest.mark.parametrize(
    "spec_id", ["vr_widerruf", "vr_gewaehrleistung", "vr_vermutung", "vr_verjaehrung"]
)
def test_each_qualification_is_individually_required(spec_id):
    specs = [ModuleSpecs("vertragsrecht", tuple(load_specs(ROOT / "fristen.yaml")))]
    case = next(
        c
        for c in _data("goldset/dossier-goldset-v1.0.0.yaml")["cases"]
        if any(d["spec_id"] == spec_id for d in c["expected"]["deadlines"])
    )
    for key in case["facts"]["qualifikationen"]:
        facts = {
            **case["facts"],
            "qualifikationen": {**case["facts"]["qualifikationen"], key: None},
        }
        item = next(
            i for i in compute_deadlines(specs, facts, [])["items"] if i["spec_id"] == spec_id
        )
        assert item["status"] == "missing_input"
        assert item["frist_ende"] is None


def test_drafts_and_presumption_never_claim_automatic_action():
    templates = _data("documents/templates.yaml")["templates"]
    assert set(templates) == {
        "pruefhinweise",
        "widerruf",
        "maengelanzeige",
        "kuendigung",
        "fluggastforderung",
    }
    for template in templates.values():
        text = "\n".join(p["text"] for p in template["parts"])
        assert "[BITTE PRÜFEN:" in text
        assert "Entwurf" in text
        assert "Keine automatische Versendung oder gerichtliche Einreichung." in text
    for language in ("de", "en", "de-LS"):
        copy = _data(f"copy/{language}/plain.yaml")
        assert copy["review"]["status"] == "draft"
        assert ("not a filing deadline" if language == "en" else "keine Klagefrist") in copy[
            "deadlines"
        ]["vr_vermutung"]["action"]


def test_schema_uses_confirmed_inputs_and_rejects_unknown_properties():
    validator = Draft202012Validator(_data("intake-schema.yaml"))
    assert not list(
        validator.iter_errors({"own_matter_confirmed": True, "applicability_confirmed": None})
    )
    assert list(validator.iter_errors({"own_matter_confirmed": False}))
    assert list(validator.iter_errors({"own_matter_confirmed": True, "invented_entitlement": True}))


@pytest.mark.parametrize(
    "template", ["pruefhinweise", "widerruf", "maengelanzeige", "kuendigung", "fluggastforderung"]
)
def test_actual_renderer_keeps_review_placeholders(monkeypatch, template):
    from app.core import config

    monkeypatch.setattr(
        config,
        "_SETTINGS",
        config.Settings(
            _env_file=None,
            OPENROUTER_API_KEY="offline-placeholder",
            DEPLOYMENT_MODE="dev",
            CITIZEN_SYNTHETIC_DATA_ONLY=True,
        ),
    )
    from app.services.document_generators import generate_document, select_generator

    result = generate_document(
        template,
        None,
        [],
        [{"claim_text": "UNCONFIRMED CLAIM", "verification_status": "exakt"}],
        module_id="vertragsrecht",
    )
    assert "Entwurf" in result.rendered_text
    assert "[BITTE PRÜFEN:" in result.rendered_text
    assert "UNCONFIRMED CLAIM" not in result.rendered_text
    assert "{absender}" not in result.rendered_text
    assert result.provenance is not None
    assert select_generator(None, module_id="vertragsrecht") == "pruefhinweise"


def test_new_year_holiday_rollover_and_no_document_date_fallback():
    specs = [ModuleSpecs("vertragsrecht", tuple(load_specs(ROOT / "fristen.yaml")))]
    source = _data("goldset/dossier-goldset-v1.0.0.yaml")["cases"][0]["facts"]
    facts = {**source, "ereignis_datum": "2026-12-18"}
    item = next(
        i for i in compute_deadlines(specs, facts, [])["items"] if i["spec_id"] == "vr_widerruf"
    )
    assert item["frist_ende"] == "2027-01-04"
    facts.pop("ereignis_datum")
    facts["bescheid_datum"] = "2026-12-18"
    item = next(
        i for i in compute_deadlines(specs, facts, [])["items"] if i["spec_id"] == "vr_widerruf"
    )
    assert item["status"] == "missing_input"
    assert item["frist_ende"] is None


def test_intake_schema_covers_all_calculator_qualification_fields():
    validator = Draft202012Validator(_data("intake-schema.yaml"))
    fields = _data("intake-schema.yaml")["properties"]
    assert {
        "outer_limit_rollover_confirmed",
        "principal_constant_confirmed",
        "notice_status",
        "claim_basis",
        "reduction_confirmed",
    } <= fields.keys()
    for key in ("principal_cents", "distance_km"):
        assert list(validator.iter_errors({"own_matter_confirmed": True, key: -1}))
    assert list(validator.iter_errors({"own_matter_confirmed": True, "notice_status": "guessed"}))
