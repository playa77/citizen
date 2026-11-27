"""Traffic content must require actual service, keep rights distinct and guard drafts."""

from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

from app.dossier.deadlines import ModuleSpecs, compute_deadlines
from app.fristen.specs import load_specs

ROOT = Path("modules/verkehrsrecht")


def data(name):
    assert (ROOT / name).exists(), f"Missing traffic content: {name}"
    return yaml.safe_load((ROOT / name).read_text())


def specs():
    data("fristen.yaml")
    return [ModuleSpecs("verkehrsrecht", tuple(load_specs(ROOT / "fristen.yaml")))]


def facts():
    return {
        "document_type": "bussgeldbescheid",
        "zustellung_tatsaechlich": "2026-11-07",
        "zustellungsart": "inland",
        "bundesland": "NW",
        "feiertagskalender_bestaetigt": True,
        "feiertage_zusaetzlich": [],
        "qualifikationen": {
            "bussgeldbescheid_bestaetigt": True,
            "zustellung_wirksam_bestaetigt": True,
            "regulaerer_einspruch_bestaetigt": True,
            "kein_sonderregime": True,
        },
    }


@pytest.mark.parametrize(
    "served,land,extra,end",
    [
        ("2026-11-02", "NW", [], "2026-11-16"),
        ("2026-11-07", "NW", [], "2026-11-23"),
        ("2026-12-18", "BE", [], "2027-01-04"),
        ("2026-11-04", "SN", [], "2026-11-19"),
        ("2026-11-04", "BE", [], "2026-11-18"),
        ("2026-11-02", "NW", ["2026-11-16"], "2026-11-17"),
    ],
)
def test_objection_actual_service_and_local_calendar(served, land, extra, end):
    f = facts()
    f.update(zustellung_tatsaechlich=served, bundesland=land, feiertage_zusaetzlich=extra)
    i = compute_deadlines(specs(), f, [])["items"][0]
    assert i["status"] == "computed"
    assert i["frist_ende"] == end
    assert "§ 43 Abs. 1 StPO" in i["explanation_de"]


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


@pytest.mark.parametrize("doctype", ["anhoerung", "zeugenfragebogen", "punkte", "fahrverbot"])
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


def test_intake_schema_qualifications_records_and_event_types():
    schema = data("intake-schema.yaml")
    v = Draft202012Validator(schema)
    assert not list(v.iter_errors({"own_matter_confirmed": True}))
    assert list(v.iter_errors({"own_matter_confirmed": False}))
    assert list(v.iter_errors({"own_matter_confirmed": True, "guessed": True}))
    for field in (
        "complete_file_confirmed",
        "no_multiple_bans_confirmed",
        "no_probationary_license_confirmed",
        "no_repeat_offence_confirmed",
        "custody_or_endorsement_required_confirmed",
    ):
        assert field in schema["properties"]
    assert list(v.iter_errors({"own_matter_confirmed": True, "excess_kmh": -1}))
    assert list(
        v.iter_errors(
            {
                "own_matter_confirmed": True,
                "interruptions": [
                    {"date": "2026-11-27", "basis": "hearing_received", "qualified_confirmed": True}
                ],
            }
        )
    )


@pytest.mark.parametrize("template", ["pruefhinweise", "einspruch", "akteneinsicht", "anhoerung"])
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
        module_id="verkehrsrecht",
    )
    assert "[BITTE PRÜFEN:" in doc.rendered_text and "Entwurf" in doc.rendered_text
    assert "UNCONFIRMED" not in doc.rendered_text
    assert "{absender}" not in doc.rendered_text and doc.provenance is not None
    assert select_generator(None, module_id="verkehrsrecht") == "pruefhinweise"


def test_rights_and_access_request_do_not_promise_deadline_suspension():
    t = data("documents/templates.yaml")["templates"]
    text = " ".join(p["text"] for p in t["akteneinsicht"]["parts"])
    assert "hemmt" in text and "Einspruchsfrist" in text
    text = " ".join(p["text"] for p in t["anhoerung"]["parts"])
    assert "Personalien" in text and "Zeugen" in text and "§ 111" in text
    for lang in ("de", "en", "de-LS"):
        assert data(f"copy/{lang}/plain.yaml")["review"]["status"] == "draft"


def test_weekly_objection_provenance_and_role_specific_goldset_anchors():
    rule = data("fristen.yaml")[0]
    assert "§ 43 Abs. 1 StPO" in rule["fristbeginn_basis"]
    assert "§ 42" not in rule["fristbeginn_basis"]
    cases = {c["id"]: c for c in data("goldset/goldset-v0.1.0.yaml")["cases"]}
    hearing = {c["norm"] for c in cases["VK-008"]["expected"]["citations"]}
    witness = {c["norm"] for c in cases["VK-009"]["expected"]["citations"]}
    assert {"§55 OWiG", "§111 OWiG"} <= hearing
    assert {"§52 StPO", "§55 StPO"} <= witness
