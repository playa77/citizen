"""Debt drafts preserve review gates in the actual generic renderer."""

from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from app.services.document_generators import generate_document, select_generator

ROOT = Path(__file__).resolve().parents[2] / "modules/schuldnerrecht"
IDS = [
    "pruefhinweise",
    "widerspruch_mahnbescheid_hilfe",
    "forderung_bestreiten",
    "p_konto_bescheinigung_anfragen",
    "datenauskunft_art15",
]


@pytest.fixture
def templates(monkeypatch):
    data = yaml.safe_load((ROOT / "documents/templates.yaml").read_text())
    monkeypatch.setattr("app.modules.runtime.document_templates", lambda module: data)
    return data


@pytest.mark.parametrize("template", IDS)
def test_empty_inputs_keep_review_placeholders(templates, template):
    result = generate_document(template, None, [], [], module_id="schuldnerrecht")
    assert "[BITTE PRÜFEN:" in result.rendered_text
    assert "Entwurf" in result.rendered_text
    assert "{claims_text}" not in result.rendered_text
    assert result.provenance is not None


def test_no_deadline_or_lapsed_date_never_selects_opposition(templates):
    assert select_generator(None, module_id="schuldnerrecht") == "pruefhinweise"
    for day in (date(2000, 1, 1), date(2099, 1, 1)):
        assert (
            select_generator(
                SimpleNamespace(frist_typ="zwei_wochen", frist_ende=day), module_id="schuldnerrecht"
            )
            == "pruefhinweise"
        )


def test_unconfirmed_limitation_claim_is_not_accepted(templates):
    result = generate_document(
        "forderung_bestreiten",
        None,
        [],
        [{"claim_text": "SYNTHETIC LIMITATION ASSERTION", "verification_status": "exakt"}],
        module_id="schuldnerrecht",
    )
    assert "SYNTHETIC LIMITATION ASSERTION" not in result.rendered_text
    assert "Hemmung" in result.rendered_text
    assert "Neubeginn" in result.rendered_text
    assert "[BITTE PRÜFEN:" in result.rendered_text


def test_opposition_guidance_preserves_late_opposition_and_form_caveat(templates):
    result = generate_document(
        "widerspruch_mahnbescheid_hilfe", None, [], [], module_id="schuldnerrecht"
    )
    assert "Vollstreckungsbescheid" in result.rendered_text
    assert "nicht allgemein verpflichtend" in result.rendered_text
    assert "nicht für Sie" in result.rendered_text


@pytest.mark.parametrize("language", ["de", "en", "de-LS"])
def test_plain_copy_schema_readability_and_safe_missing_dates(language):
    import json
    from string import Formatter

    from jsonschema import Draft202012Validator

    from app.plain.checks import discouraging_hits, iter_texts, long_sentences

    copy = yaml.safe_load((ROOT / "copy" / language / "plain.yaml").read_text())
    schema = json.loads((ROOT.parents[1] / "app/plain/copy.schema.json").read_text())
    assert not list(Draft202012Validator(schema).iter_errors(copy))
    assert copy["review"]["status"] == "draft"
    assert set(copy["findings"]) == {
        "forderung_pruefen",
        "kosten_pruefen",
        "frist_pruefen",
        "beratung_erforderlich",
        "einordnung_offen",
    }
    for path, text in iter_texts(copy):
        assert not discouraging_hits(text), path
        assert not long_sentences(text, 14 if language == "de-LS" else 22), path
    for deadline in copy["deadlines"].values():
        assert set(deadline["texts"]) == {
            "computed",
            "provisional",
            "missing_input",
            "not_applicable",
        }
        for status, text in deadline["texts"].items():
            fields = {field for _, field, _, _ in Formatter().parse(text) if field}
            assert fields <= {"frist_ende", "bekanntgabe", "basis"}
            if status in {"missing_input", "not_applicable"}:
                assert not fields
