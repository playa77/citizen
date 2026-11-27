"""Residence sources and administrative procedural calendar retain explicit identity."""

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
    "aufenthg": ("AufenthG", "aufenthg_2004"),
    "asylg": ("AsylG", "asylvfg_1992"),
    "aufenthv": ("AufenthV", "aufenthv"),
    "beschv": ("BeschV", "beschv_2013"),
    "freizuegg_eu": ("FreizügG/EU", "freiz_gg_eu_2004"),
    "stag": ("StAG", "stag"),
    "vwgo": ("VwGO", "vwgo"),
}


@pytest.mark.parametrize("key", SOURCES)
def test_residence_source_identity(key):
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


@pytest.mark.parametrize(
    "raw,land,expected",
    [
        ("2026-11-21", "NW", "2026-11-23"),
        ("2027-01-01", "BE", "2027-01-04"),
        ("2026-11-18", "SN", "2026-11-19"),
        ("2026-11-18", "BE", "2026-11-18"),
        ("2028-04-14", "NW", "2028-04-18"),
    ],
)
def test_vwgo_rollover_uses_current_state_calendar(raw, land, expected):
    assert get_rollover("vwgo_57")(date.fromisoformat(raw), land).isoformat() == expected


def test_migration_retains_history_and_guards_downgrade(monkeypatch):
    path = Path("alembic/versions/022_residence_sources.py")
    assert path.exists()
    spec = importlib.util.spec_from_file_location("residence_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    assert migration.down_revision == "021_family_sources"
    op = MagicMock()
    monkeypatch.setattr(migration, "op", op)
    op.get_bind.return_value.execute.return_value.first.return_value = (1,)
    with pytest.raises(RuntimeError, match="residence sources"):
        migration.downgrade()
    op.create_check_constraint.assert_not_called()
    op.get_bind.return_value.execute.return_value.first.return_value = None
    migration.downgrade()
    assert "'famfg'" in op.create_check_constraint.call_args.args[2]
    assert "'aufenthg'" not in op.create_check_constraint.call_args.args[2]
    migration.upgrade()
    assert all(f"'{key}'" in op.create_check_constraint.call_args.args[2] for key in SOURCES)


def test_lettered_sections_remain_distinct_from_the_numeric_section():
    soup = BeautifulSoup(
        "".join(
            f'<div class="jnnorm"><span class="jnenbez">§ {number}</span>'
            f'<div class="jurAbsatz">(1) Synthetische Norm {number}.</div></div>'
            for number in ("34", "34a", "87", "87e")
        ),
        "html.parser",
    )
    chunks = corpus._parse_law_sections(
        soup, "asylg", "AsylG", date(2026, 11, 27), "/asylvfg_1992/"
    )
    assert [c["hierarchy_path"] for c in chunks] == [
        "AsylG > § 34 > Abs. 1",
        "AsylG > § 34a > Abs. 1",
        "AsylG > § 87 > Abs. 1",
        "AsylG > § 87e > Abs. 1",
    ]
    # Tagging still uses the numeric BGB range without truncating stored identity.
    bgb = corpus._parse_law_sections(
        BeautifulSoup(
            '<div class="jnnorm"><span class="jnenbez">§ 1612a</span>'
            '<div class="jurAbsatz">(1) Synthetisch.</div></div>',
            "html.parser",
        ),
        "bgb",
        "BGB",
        date(2026, 11, 27),
        "/bgb/",
    )[0]
    assert bgb["hierarchy_path"] == "BGB > § 1612a > Abs. 1"
    assert bgb["legal_area"] == "familienrecht"


def test_adjacent_prose_does_not_hide_a_known_statute_reference():
    assert _extract_norm_references("§ 34a AsylG und § 87e AsylG") == ["§ 34a AsylG", "§ 87e AsylG"]
    assert _extract_norm_references("§ 81 AufenthG gilt; § 10 StAG ist relevant.") == [
        "§ 81 AufenthG",
        "§ 10 StAG",
    ]
    assert _extract_norm_references("§ 1 FreizügG/EU und § 2 AufenthG") == [
        "§ 1 FreizügG/EU",
        "§ 2 AufenthG",
    ]
