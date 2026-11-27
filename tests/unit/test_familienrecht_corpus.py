"""Family source identity, guarded migration and current procedural calendar."""

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
    "famfg": ("FamFG", "famfg"),
    "uvg": ("UhVorschG", "uhvorschg"),
    "minuhv": ("MinUhV", "minuhv"),
}


@pytest.mark.parametrize("key", SOURCES)
def test_family_source_identity(key):
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
        ("2026-10-31", "NW", "2026-11-02"),
        ("2026-11-18", "SN", "2026-11-19"),
        ("2026-11-18", "BE", "2026-11-18"),
        ("2028-04-14", "NW", "2028-04-18"),
    ],
)
def test_famfg_rollover_uses_current_state_calendar(raw, land, expected):
    assert get_rollover("famfg_16")(date.fromisoformat(raw), land).isoformat() == expected


def test_family_migration_retains_history_and_refuses_destructive_downgrade(monkeypatch):
    path = Path("alembic/versions/021_family_sources.py")
    assert path.exists()
    spec = importlib.util.spec_from_file_location("family_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    assert migration.down_revision == "020_traffic_sources"
    op = MagicMock()
    monkeypatch.setattr(migration, "op", op)
    op.get_bind.return_value.execute.return_value.first.return_value = (1,)
    with pytest.raises(RuntimeError, match="family sources"):
        migration.downgrade()
    op.create_check_constraint.assert_not_called()
    op.get_bind.return_value.execute.return_value.first.return_value = None
    migration.downgrade()
    assert "'stpo'" in op.create_check_constraint.call_args.args[2]
    assert "'famfg'" not in op.create_check_constraint.call_args.args[2]
    migration.upgrade()
    assert all(f"'{key}'" in op.create_check_constraint.call_args.args[2] for key in SOURCES)
