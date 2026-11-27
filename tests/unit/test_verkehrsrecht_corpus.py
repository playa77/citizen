"""Traffic source identity, explicit partial annex coverage and procedural calendar."""

import importlib.util
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from bs4 import BeautifulSoup

from app.citations.parser import parse_citations
from app.db.models import SOURCE_TYPE_ALLOWED
from app.fristen.rollover import get_rollover
from app.services import corpus
from app.services.retrieval import _extract_norm_references

SOURCES = {
    "owig": ("OWiG", "owig_1968"),
    "stvg": ("StVG", "stvg"),
    "stvo": ("StVO", "stvo_2013"),
    "bkatv": ("BKatV", "bkatv_2013"),
    "fev": ("FeV", "fev_2010"),
    "stpo": ("StPO", "stpo"),
}


@pytest.mark.parametrize("key", SOURCES)
def test_traffic_source_identity(key):
    law, slug = SOURCES[key]
    assert key in SOURCE_TYPE_ALLOWED
    metadata = corpus.CORPUS_SOURCE_METADATA[key]
    assert metadata["has_scraper"] is True
    assert metadata["checked_by_default"] is False
    assert corpus.gii_source_slugs()[key] == slug
    assert parse_citations(f"§ 1 {law}")[0].source_type == key
    assert _extract_norm_references(f"§ 1 {law}") == [f"§ 1 {law}"]
    soup = BeautifulSoup(
        '<div class="jnnorm"><span class="jnenbez">§ 1</span>'
        '<div class="jurAbsatz">(1) Synthetische Regel.</div></div>',
        "html.parser",
    )
    chunk = corpus._parse_law_sections(soup, key, law, date(2026, 11, 27), f"/{slug}/")[0]
    assert chunk["hierarchy_path"] == f"{law} > § 1 > Abs. 1"
    assert chunk["source_url"] == f"https://www.gesetze-im-internet.de/{slug}/"
    assert corpus._infer_law_name(soup, key) == law


@pytest.mark.parametrize("key", ["bkatv", "fev", "stvo"])
def test_annex_limitation_is_explicit_not_mislabeled_as_section(key):
    assert "Anlagen" in corpus.CORPUS_SOURCE_METADATA[key]["description"]
    soup = BeautifulSoup(
        '<div class="jnnorm"><span class="jnenbez">Anlage 13</span>'
        '<div class="jurAbsatz"><table><tr><td>synthetic</td></tr></table>'
        "</div></div>",
        "html.parser",
    )
    assert corpus._parse_law_sections(soup, key, SOURCES[key][0], date(2026, 11, 27), "/") == []


@pytest.mark.parametrize(
    "raw,land,expected",
    [
        ("2026-11-21", "NW", "2026-11-23"),
        ("2027-01-01", "BE", "2027-01-04"),
        ("2026-10-31", "NW", "2026-11-02"),
        ("2026-11-18", "SN", "2026-11-19"),
        ("2026-11-18", "BE", "2026-11-18"),
        ("2028-04-14", "NW", "2028-04-18"),
    ],
)
def test_stpo_rollover_uses_current_state_calendar(raw, land, expected):
    assert get_rollover("stpo_43")(date.fromisoformat(raw), land).isoformat() == expected


def test_traffic_migration_retains_history_and_refuses_destructive_downgrade(monkeypatch):
    path = Path("alembic/versions/020_traffic_sources.py")
    assert path.exists()
    spec = importlib.util.spec_from_file_location("traffic_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    assert migration.down_revision == "019_contract_sources"
    op = MagicMock()
    monkeypatch.setattr(migration, "op", op)
    op.get_bind.return_value.execute.return_value.first.return_value = (1,)
    with pytest.raises(RuntimeError, match="traffic sources"):
        migration.downgrade()
    op.create_check_constraint.assert_not_called()
    op.get_bind.return_value.execute.return_value.first.return_value = None
    migration.downgrade()
    assert "'eu261'" in op.create_check_constraint.call_args.args[2]
    assert "'owig'" not in op.create_check_constraint.call_args.args[2]
    migration.upgrade()
    assert all(f"'{key}'" in op.create_check_constraint.call_args.args[2] for key in SOURCES)
