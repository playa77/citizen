"""Tenant drafts retain factual and legal review gates in the actual renderer."""

from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from app.services.document_generators import generate_document, select_generator

ROOT = Path(__file__).resolve().parents[2] / "modules/mietrecht"
IDS = [
    "pruefhinweise",
    "mieterhoehung_antwort",
    "betriebskosten_belegeinsicht",
    "maengelanzeige",
    "sozialwiderspruch",
]


@pytest.fixture
def templates(monkeypatch):
    data = yaml.safe_load((ROOT / "documents/templates.yaml").read_text())
    monkeypatch.setattr("app.modules.runtime.document_templates", lambda module: data)
    return data


@pytest.mark.parametrize("template", IDS)
def test_empty_inputs_keep_review_gates(templates, template):
    result = generate_document(template, None, [], [], module_id="mietrecht")
    assert "[BITTE PRÜFEN:" in result.rendered_text
    assert "Entwurf" in result.rendered_text
    assert "{claims_text}" not in result.rendered_text
    assert result.provenance is not None


def test_no_automatic_consent_or_objection_without_document_choice(templates):
    assert select_generator(None, module_id="mietrecht") == "pruefhinweise"
    for day in (date(2000, 1, 1), date(2099, 1, 1)):
        assert (
            select_generator(
                SimpleNamespace(frist_typ="monat", frist_ende=day), module_id="mietrecht"
            )
            == "pruefhinweise"
        )


def test_unconfirmed_model_claim_cannot_become_mietminderung(templates):
    result = generate_document(
        "maengelanzeige",
        None,
        [],
        [{"claim_text": "SYNTHETIC REDUCTION CLAIM 80%", "verification_status": "exakt"}],
        module_id="mietrecht",
    )
    assert "SYNTHETIC REDUCTION CLAIM" not in result.rendered_text
    assert "[BITTE PRÜFEN: angemessene Frist" in result.rendered_text
    assert "Zahlung" in result.rendered_text


def test_rent_increase_reply_does_not_assert_consent_or_invalidity(templates):
    result = generate_document("mieterhoehung_antwort", None, [], [], module_id="mietrecht")
    assert "keine Zustimmung" in result.rendered_text
    assert "[BITTE PRÜFEN: Zugang" in result.rendered_text
    assert "ersetzt keine" in result.rendered_text


def test_hardship_draft_warns_about_qualified_late_objections(templates):
    result = generate_document("sozialwiderspruch", None, [], [], module_id="mietrecht")
    assert "[BITTE PRÜFEN: Härtegründe" in result.rendered_text
    assert "ersten Termin" in result.rendered_text
    assert "Textform" in result.rendered_text


@pytest.mark.parametrize("language", ["de", "en", "de-LS"])
def test_plain_copy_safe_missing_dates_and_readability(language):
    import json
    from string import Formatter

    from jsonschema import Draft202012Validator

    from app.plain.checks import discouraging_hits, iter_texts, long_sentences

    copy = yaml.safe_load((ROOT / "copy" / language / "plain.yaml").read_text())
    schema = json.loads((ROOT.parents[1] / "app/plain/copy.schema.json").read_text())
    assert not list(Draft202012Validator(schema).iter_errors(copy))
    assert copy["review"]["status"] == "draft"
    assert set(copy["findings"]) == {
        "miete_pruefen",
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
