"""Add regime and notes columns to legal_parameter.

Tags each parameter row with a regime label (e.g. "2024", "a.F.", "n.F.") and
provides a free-text notes field for review annotations (e.g. OQ-3 verification
tracking).

Revision ID: 009_add_regime_and_notes_to_legal_parameter
Revises: 008_fix_stage_name_allowed
Create Date: 2026-07-12 00:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "009_add_regime_and_notes_to_legal_parameter"
down_revision: str | None = "008_fix_stage_name_allowed"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "legal_parameter",
        sa.Column("regime", sa.String(50), nullable=True),
    )
    op.add_column(
        "legal_parameter",
        sa.Column("notes", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("legal_parameter", "notes")
    op.drop_column("legal_parameter", "regime")
