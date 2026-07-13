"""Add pii_mapping JSON column to case_run for WP-30 pseudonymization gate.

Stores the bidirectional PII-to-placeholder mapping per case run so that
pipeline output can be depseudonymized before user display.

Revision ID: 010_add_pii_mapping_to_case_run
Revises: 009_add_regime_and_notes_to_legal_parameter
Create Date: 2026-07-12 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "010_add_pii_mapping_to_case_run"
down_revision: str | None = "009_add_regime_and_notes_to_legal_parameter"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "case_run",
        sa.Column("pii_mapping", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("case_run", "pii_mapping")
