"""Family content must qualify procedural scope, minimise third-party data and guard drafts."""

from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

from app.dossier.deadlines import ModuleSpecs, compute_deadlines
from app.fristen.specs import load_specs

ROOT = Path("modules/familienrecht")


def data(name):
    assert (ROOT / name).exists(), f"Missing family content: {name}"
    return yaml.safe_load((ROOT / name).read_text())


def specs():
    data("fristen.yaml")
    return [ModuleSpecs("familienrecht", tuple(load_specs(ROOT / "fristen.yaml")))]


def facts():
    return {
        "document_type": "famfg_regulaerer_endbeschluss",
        "zustellung_tatsaechlich": "2026-11-07",
        "zustellungsart": "inland",
        "bundesland": "NW",
        "feiertagskalender_bestaetigt": True,
        "feiertage_zusaetzlich": [],
        "qualifikationen": {
            "regulaerer_endbeschluss_bestaetigt": True,
            "zustellung_wirksam_bestaetigt": True,
            "kein_113_verfahren_bestaetigt": True,
            "kein_sonderregime": True,
        },
    }


@pytest.mark.parametrize(
    "served,land,extra,end",
    [
        ("2026-10-02", "NW", [], "2026-11-02"),
        ("2026-10-21", "NW", [], "2026-11-23"),
        ("2026-12-01", "BE", [], "2027-01-04"),
        ("2026-10-18", "SN", [], "2026-11-19"),
        ("2026-10-18", "BE", [], "2026-11-18"),
        ("2026-10-30", "NW", ["2026-11-30"], "2026-12-01"),
    ],
)
def test_objection_actual_service_and_local_calendar(served, land, extra, end):
    f = facts()
    f.update(zustellung_tatsaechlich=served, bundesland=land, feiertage_zusaetzlich=extra)
    i = compute_deadlines(specs(), f, [])["items"][0]
    assert i["status"] == "computed"
    assert i["frist_ende"] == end
    assert "§ 63 Abs. 3 FamFG" in i["explanation_de"]


@pytest.mark.parametrize(
    "key",
    ["zustellung_tatsaechlich", "zustellungsart", "bundesland", "feiertagskalender_bestaetigt"],
)
def test_missing_service_or_calendar_never_uses_letter_date(key):
    f = facts()
    f.pop(key)
    f["bescheid_datum"] = "2026-11-07"
    i = compute_deadlines(specs(), f, [])["items"][0]
    assert i["status"] == "missing_input" and i["frist_ende"] is None


def test_each_qualification_and_service_mode_is_required():
    for key in facts()["qualifikationen"]:
        f = facts()
        f["qualifikationen"][key] = None
        assert compute_deadlines(specs(), f, [])["items"][0]["status"] == "missing_input"
    for mode in ("ausland", "oeffentlich"):
        f = facts()
        f["zustellungsart"] = mode
        assert compute_deadlines(specs(), f, [])["items"][0]["status"] == "missing_input"


@pytest.mark.parametrize(
    "doctype",
    [
        "einstweilige_anordnung",
        "unterhaltsaufforderung",
        "uvg_bescheid",
        "ehesache",
        "genehmigung_rechtsgeschaeft",
    ],
)
def test_other_documents_do_not_start_objection(doctype):
    f = facts()
    f["document_type"] = doctype
    assert compute_deadlines(specs(), f, [])["items"][0]["status"] == "not_applicable"


def test_literal_goldset_dates_and_guards():
    for case in data("goldset/dossier-goldset-v1.0.0.yaml")["cases"]:
        actual = {
            i["spec_id"]: i["frist_ende"]
            for i in compute_deadlines(specs(), case["facts"], [])["items"]
            if i["status"] == "computed"
        }
        assert actual == {
            i["spec_id"]: i["frist_ende"] for i in case["expected"]["deadlines"]
        }, case["id"]


def test_intake_schema_minimises_third_party_data():
    v = Draft202012Validator(data("intake-schema.yaml"))
    assert not list(v.iter_errors({"own_matter_confirmed": True}))
    for field in ("child_name", "child_birth_date", "ex_partner_address", "medical_history"):
        assert list(v.iter_errors({"own_matter_confirmed": True, field: "private"}))
    assert list(v.iter_errors({"own_matter_confirmed": False}))
    assert list(v.iter_errors({"own_matter_confirmed": True, "age_at_month_end": 18}))


@pytest.mark.parametrize(
    "template", ["pruefhinweise", "auskunft", "stellungnahme", "uvg_vorbereitung"]
)
def test_actual_drafts_preserve_review_and_never_insert_unconfirmed_claims(monkeypatch, template):
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
    data("documents/templates.yaml")
    from app.services.document_generators import generate_document, select_generator

    doc = generate_document(
        template,
        None,
        [],
        [{"claim_text": "UNCONFIRMED", "verification_status": "exakt"}],
        module_id="familienrecht",
    )
    assert "[BITTE PRÜFEN:" in doc.rendered_text and "Entwurf" in doc.rendered_text
    assert "UNCONFIRMED" not in doc.rendered_text
    assert "{absender}" not in doc.rendered_text and doc.provenance is not None
    assert select_generator(None, module_id="familienrecht") == "pruefhinweise"


def test_referral_and_reuse_limits_remain_explicit():
    for lang in ("de", "en", "de-LS"):
        assert data(f"copy/{lang}/plain.yaml")["review"]["status"] == "draft"
    text = (ROOT / "prompts/profile.yaml").read_text()
    assert "§113" in text and "§114" in text and "Kindeswohl" in text
    assert "Düsseldorfer Tabelle" in text
    templates = data("documents/templates.yaml")["templates"]
    for name in ("pruefhinweise", "auskunft", "stellungnahme", "uvg_vorbereitung"):
        text = " ".join(p["text"] for p in templates[name]["parts"])
        assert "keine Frist" in text and "[BITTE PRÜFEN:" in text
