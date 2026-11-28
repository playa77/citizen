"""WP-136: residence source types; retain existing source and chunk data.

Revision ID: 022_residence_sources
Revises: 021_family_sources
Create Date: 2026-11-27
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "022_residence_sources"
down_revision: str | None = "021_family_sources"
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
PREVIOUS = (*PREVIOUS, "owig", "stvg", "stvo", "bkatv", "fev", "stpo")
PREVIOUS = (*PREVIOUS, "famfg", "uvg", "minuhv")
ADDED = ("aufenthg", "asylg", "aufenthv", "beschv", "freizuegg_eu", "stag", "vwgo")


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
                "WHERE source_type IN ('aufenthg','asylg','aufenthv','beschv',"
                "'freizuegg_eu','stag','vwgo') LIMIT 1"
            )
        )
        .first()
    )
    if present:
        raise RuntimeError("Cannot downgrade while WP-136 residence sources are stored")
    _replace(PREVIOUS)
