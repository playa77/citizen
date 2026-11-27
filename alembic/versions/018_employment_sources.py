"""WP-132: employment source types; retain existing source and chunk data.

Revision ID: 018_employment_sources
Revises: 017_tenancy_sources
Create Date: 2026-11-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "018_employment_sources"
down_revision: str | None = "017_tenancy_sources"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PREVIOUS = (
    "sgb1", "sgb2", "sgb3", "sgb9", "sgb12", "sgbx", "bgb", "vwvfg", "sgg",
    "weisung", "bsg", "erbstg", "hoefev", "kschg", "burlg", "tvg",
    "zpo", "inso", "rdg", "rvg", "betrkv", "heizkostenv", "landes_mietrecht",
)
ADDED = ("tzbfg", "entgfg", "milog", "muschg", "arbzg", "arbgg")


def _replace(values: tuple[str, ...]) -> None:
    op.execute("ALTER TABLE legal_source DROP CONSTRAINT IF EXISTS ck_legal_source_source_type")
    allowed = ", ".join(f"'{value}'" for value in values)
    op.create_check_constraint(
        "ck_legal_source_source_type", "legal_source", f"source_type IN ({allowed})"
    )


def upgrade() -> None:
    _replace((*PREVIOUS, *ADDED))


def downgrade() -> None:
    present = op.get_bind().execute(sa.text(
        "SELECT 1 FROM legal_source "
        "WHERE source_type IN ('tzbfg','entgfg','milog','muschg','arbzg','arbgg') LIMIT 1"
    )).first()
    if present:
        raise RuntimeError("Cannot downgrade while WP-132 employment sources are stored")
    _replace(PREVIOUS)
