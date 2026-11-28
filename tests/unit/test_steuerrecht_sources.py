"""Tax sources retain official identities through parsing and retrieval."""

import importlib.util
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from bs4 import BeautifulSoup

from app.citations.parser import parse_citations
from app.db.models import SOURCE_TYPE_ALLOWED
from app.services import corpus
from app.services.retrieval import _extract_norm_references

SOURCES = {
    "estg": ("EStG", "estg"),
    "ao": ("AO", "ao_1977"),
    "solzg": ("SolZG", "solzg_1995"),
    "fgo": ("FGO", "fgo"),
    "stberg": ("StBerG", "stberg"),
}


@pytest.mark.parametrize("key", SOURCES)
def test_tax_source_identity(key):
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


def test_migration_retains_history_and_guards_downgrade(monkeypatch):
    path = Path("alembic/versions/023_tax_sources.py")
    assert path.exists()
    spec = importlib.util.spec_from_file_location("tax_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    assert migration.down_revision == "022_residence_sources"
    op = MagicMock()
    monkeypatch.setattr(migration, "op", op)
    op.get_bind.return_value.execute.return_value.first.return_value = (1,)
    with pytest.raises(RuntimeError, match="tax sources"):
        migration.downgrade()
    op.create_check_constraint.assert_not_called()
    op.get_bind.return_value.execute.return_value.first.return_value = None
    migration.downgrade()
    assert "'aufenthg'" in op.create_check_constraint.call_args.args[2]
    assert "'estg'" not in op.create_check_constraint.call_args.args[2]
    migration.upgrade()
    assert all(f"'{key}'" in op.create_check_constraint.call_args.args[2] for key in SOURCES)
