"""Qualified migration deadlines, minimised intake and guarded own-matter drafts."""

from copy import deepcopy
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

from app.dossier.deadlines import ModuleSpecs, compute_deadlines
from app.fristen.specs import load_specs

ROOT = Path("modules/aufenthaltsrecht")
LANGUAGES = ("de", "de-LS", "en", "ar", "fa", "uk", "tr", "ru")


def data(name):
    assert (ROOT / name).exists(), f"Missing residence content: {name}"
    return yaml.safe_load((ROOT / name).read_text())


def facts(doctype="asyl_zwei_wochen"):
    rules = load_specs(ROOT / "fristen.yaml")
    qualified = {
        key: True
        for rule in rules
        if rule.applies_when.get("document_type") == doctype
        for key in rule.requires_confirmed
    }
    return {
        "document_type": doctype,
        "zustellung_tatsaechlich": "2026-11-13",
        "ereignis_datum": "2026-11-13",
        "zustellungsart": "inland",
        "bundesland": "NW",
        "feiertagskalender_bestaetigt": True,
        "feiertage_zusaetzlich": [],
        "qualifikationen": qualified,
    }


def results(f):
    data("fristen.yaml")
    specs = [ModuleSpecs("aufenthaltsrecht", tuple(load_specs(ROOT / "fristen.yaml")))]
    return {i["spec_id"]: i for i in compute_deadlines(specs, f, [])["items"]}


@pytest.mark.parametrize(
    "doctype,spec,served,land,extra,end",
    [
        ("auslaender_widerspruchsbescheid", "auf_klage", "2026-10-31", "NW", [], "2026-11-30"),
        ("auslaender_direktklage", "auf_direktklage", "2026-12-01", "BE", [], "2027-01-04"),
        ("auslaender_widerspruch", "auf_widerspruch", "2026-10-18", "SN", [], "2026-11-19"),
        ("asyl_zwei_wochen", "asyl_klage", "2026-11-13", "NW", [], "2026-11-27"),
        ("asyl_zwei_wochen", "asyl_klage", "2026-10-30", "NW", ["2026-11-13"], "2026-11-16"),
        ("asyl_36", "asyl_36_klage", "2026-11-13", "NW", [], "2026-11-20"),
        ("asyl_36", "asyl_36_eil", "2026-11-13", "NW", [], "2026-11-20"),
        ("asyl_34a", "asyl_34a_klage", "2026-11-13", "NW", [], "2026-11-20"),
        ("asyl_34a", "asyl_34a_eil", "2026-11-13", "NW", [], "2026-11-20"),
    ],
)
def test_qualified_dates_and_local_holidays(doctype, spec, served, land, extra, end):
    f = facts(doctype) | dict(
        zustellung_tatsaechlich=served,
        ereignis_datum=served,
        bundesland=land,
        feiertage_zusaetzlich=extra,
    )
    item = results(f)[spec]
    assert item["status"] == "computed" and item["frist_ende"] == end
    assert item["severity"] == "critical"


def test_no_issue_date_fallback_and_every_qualification_is_required():
    f = facts()
    for key in (
        "zustellung_tatsaechlich",
        "zustellungsart",
        "bundesland",
        "feiertagskalender_bestaetigt",
    ):
        bad = deepcopy(f)
        bad.pop(key)
        bad["bescheid_datum"] = "2026-11-01"
        item = results(bad)["asyl_klage"]
        assert item["status"] == "missing_input" and item["frist_ende"] is None
    rule = next(s for s in load_specs(ROOT / "fristen.yaml") if s.id == "asyl_klage")
    for key in rule.requires_confirmed:
        bad = deepcopy(f)
        bad["qualifikationen"].pop(key)
        assert results(bad)["asyl_klage"]["status"] == "missing_input"


@pytest.mark.parametrize(
    "doctype",
    [
        "asyl_altrecht",
        "asyl_flughafen",
        "asyl_unbekannt",
        "duldung",
        "titel",
        "einbuergerung",
        "sonstiges",
    ],
)
def test_unknown_and_transition_procedures_never_get_ordinary_dates(doctype):
    assert all(i["frist_ende"] is None for i in results(facts(doctype)).values())


def test_minimised_intake_excludes_sensitive_narratives():
    v = Draft202012Validator(data("intake-schema.yaml"))
    assert not list(v.iter_errors({"own_matter_confirmed": True}))
    for key in (
        "persecution_story",
        "religion",
        "health_history",
        "passport_number",
        "third_party_name",
    ):
        assert list(v.iter_errors({"own_matter_confirmed": True, key: "private"}))
    assert list(v.iter_errors({"own_matter_confirmed": False}))


@pytest.mark.parametrize("lang", LANGUAGES)
def test_each_language_provides_warning_and_all_deadline_statuses(lang):
    doc = data(f"copy/{lang}/plain.yaml")
    assert doc["review"]["status"] == "draft"
    for spec in load_specs(ROOT / "fristen.yaml"):
        entry = doc["deadlines"][spec.id]
        assert entry["action"]
        assert all(
            entry["texts"][s]
            for s in ("computed", "provisional", "missing_input", "not_applicable")
        )
    from app.core.config import Settings
    from app.plain.core_copy import load_core_copy

    core = load_core_copy(
        lang,
        disclaimer_version=Settings.model_fields["DISCLAIMER_VERSION"].default,
        disclosure_version="1.0",
    )
    assert core["review"]["status"] == "draft"
    assert core["privacy"]["inference"]["unknown"]


@pytest.mark.parametrize(
    "template", ["pruefhinweise", "verlaengerung", "akteneinsicht", "fristbitte"]
)
def test_actual_drafts_do_not_fabricate_facts_or_asylum_narratives(template, monkeypatch):
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
    from app.services.document_generators import generate_document

    doc = generate_document(
        template,
        None,
        [],
        [{"claim_text": "UNCONFIRMED", "verification_status": "exakt"}],
        module_id="aufenthaltsrecht",
    )
    assert "[BITTE PRÜFEN:" in doc.rendered_text and "Entwurf" in doc.rendered_text
    assert "UNCONFIRMED" not in doc.rendered_text and doc.provenance is not None
    assert "keine Frist" in doc.rendered_text


@pytest.mark.parametrize("lang", LANGUAGES)
def test_rendered_lawsuit_and_interim_cards_name_different_remedies(lang):
    from app.modules.runtime import get_manifest
    from app.plain.render import render_deadline

    items = results(facts("asyl_36"))
    cards = [
        render_deadline(get_manifest("aufenthaltsrecht"), items[k], [lang])["texts"][lang]
        for k in ("asyl_36_klage", "asyl_36_eil")
    ]
    assert cards[0]["title"] != cards[1]["title"]


def test_conflicting_asylum_qualifications_cannot_yield_longer_date():
    f = facts("asyl_zwei_wochen")
    f["qualifikationen"]["wochenklage_bestaetigt"] = True
    assert results(f)["asyl_klage"]["status"] == "missing_input"
    assert results(f)["asyl_klage"]["frist_ende"] is None
    from app.fristen.evaluator import FristInput, evaluate_spec
    from datetime import date

    rule = next(s for s in load_specs(ROOT / "fristen.yaml") if s.id == "asyl_klage")
    with pytest.raises(ValueError, match="[Cc]onflict|[Ww]iderspr"):
        evaluate_spec(
            rule,
            FristInput(
                bescheid_datum=date(2026, 11, 13),
                zustellung_tatsaechlich=date(2026, 11, 13),
                document_type="asyl_zwei_wochen",
                zustellungsart="inland",
                bundesland="NW",
                qualifikationen=f["qualifikationen"],
                feiertagskalender_bestaetigt=True,
            ),
            module_id="aufenthaltsrecht",
        )


@pytest.mark.parametrize("doctype,base", [("asyl_36", "asyl_36"), ("asyl_34a", "asyl_34a")])
def test_interim_application_uses_effective_notification_independently(doctype, base):
    f = facts(doctype)
    f["ereignis_datum"] = "2026-11-11"
    f["bekanntgabe_tatsaechlich"] = "2026-11-11"
    f["qualifikationen"]["wirksame_bekanntgabe_bestaetigt"] = True
    r = results(f)
    assert r[base + "_eil"]["frist_ende"] == "2026-11-18"
    assert r[base + "_klage"]["frist_ende"] == "2026-11-20"
    f.pop("ereignis_datum")
    assert results(f)[base + "_eil"]["status"] == "missing_input"


@pytest.mark.parametrize("lang", LANGUAGES)
@pytest.mark.parametrize("doctype", ["asyl_unbekannt", "asyl_altrecht", "asyl_flughafen"])
def test_public_plain_view_retains_urgent_referral_without_a_date(lang, doctype):
    from app.plain.service import case_plain

    section = {"items": list(results(facts(doctype)).values())}
    view = case_plain({}, ["aufenthaltsrecht"], section, [lang])
    assert view["banner"] is not None
    selected = next(i for i in view["deadlines"] if i["spec_id"] == view["banner"]["spec_id"])
    assert selected["frist_ende"] is None and selected["referral_required"] is True
    assert selected["texts"][lang]["action"]
