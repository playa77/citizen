"""WP-130: extend statutory source types (D-071); preserve all existing data.

Revision ID: 016_debt_sources
Revises: 015_module_platform
Create Date: 2026-11-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "016_debt_sources"
down_revision: str | None = "015_module_platform"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PREVIOUS = (
    "sgb1", "sgb2", "sgb3", "sgb9", "sgb12", "sgbx", "bgb", "vwvfg", "sgg",
    "weisung", "bsg", "erbstg", "hoefev", "kschg", "burlg", "tvg",
)
ADDED = ("zpo", "inso", "rdg", "rvg")


def _replace(values: tuple[str, ...]) -> None:
    op.execute("ALTER TABLE legal_source DROP CONSTRAINT IF EXISTS ck_legal_source_source_type")
    allowed = ", ".join(f"'{value}'" for value in values)
    op.create_check_constraint(
        "ck_legal_source_source_type", "legal_source", f"source_type IN ({allowed})"
    )


def upgrade() -> None:
    _replace((*PREVIOUS, *ADDED))


def downgrade() -> None:
    # Never erase ingested law or cascading chunks to make a downgrade succeed.
    present = op.get_bind().execute(sa.text(
        "SELECT 1 FROM legal_source WHERE source_type IN ('zpo','inso','rdg','rvg') LIMIT 1"
    )).first()
    if present:
        raise RuntimeError("Cannot downgrade while WP-130 statutory sources are stored")
    _replace(PREVIOUS)
