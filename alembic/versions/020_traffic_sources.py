"""WP-134: traffic source types; retain existing source and chunk data.

Revision ID: 020_traffic_sources
Revises: 019_contract_sources
Create Date: 2026-11-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "020_traffic_sources"
down_revision: str | None = "019_contract_sources"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PREVIOUS = (
    "sgb1",
    "sgb2",
    "sgb3",
    "sgb9",
    "sgb12",
    "sgbx",
    "bgb",
    "vwvfg",
    "sgg",
    "weisung",
    "bsg",
    "erbstg",
    "hoefev",
    "kschg",
    "burlg",
    "tvg",
    "zpo",
    "inso",
    "rdg",
    "rvg",
    "betrkv",
    "heizkostenv",
    "landes_mietrecht",
)
PREVIOUS = (*PREVIOUS, "tzbfg", "entgfg", "milog", "muschg", "arbzg", "arbgg")
PREVIOUS = (*PREVIOUS, "egbgb", "eu261")
ADDED = ("owig", "stvg", "stvo", "bkatv", "fev", "stpo")


def _replace(values: tuple[str, ...]) -> None:
    op.execute("ALTER TABLE legal_source DROP CONSTRAINT IF EXISTS ck_legal_source_source_type")
    allowed = ", ".join(f"'{value}'" for value in values)
    op.create_check_constraint(
        "ck_legal_source_source_type", "legal_source", f"source_type IN ({allowed})"
    )


def upgrade() -> None:
    _replace((*PREVIOUS, *ADDED))


def downgrade() -> None:
    present = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT 1 FROM legal_source "
                "WHERE source_type IN ('owig','stvg','stvo','bkatv','fev','stpo') LIMIT 1"
            )
        )
        .first()
    )
    if present:
        raise RuntimeError("Cannot downgrade while WP-134 traffic sources are stored")
    _replace(PREVIOUS)
