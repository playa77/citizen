"""Add legal_parameter table and legal_snapshot column to case_run.

Revision ID: 004_add_legal_parameter
Revises: 003_add_conversations
Create Date: 2026-05-13 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "004_add_legal_parameter"
down_revision: Union[str, None] = "003_add_conversations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- legal_parameter ---
    op.create_table(
        "legal_parameter",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("parameter_key", sa.String(200), nullable=False),
        sa.Column("value_numeric", sa.Float, nullable=True),
        sa.Column("value_json", postgresql.JSONB, nullable=True),
        sa.Column("value_text", sa.Text, nullable=True),
        sa.Column("unit", sa.String(50), nullable=True),
        sa.Column(
            "domain",
            sa.String(50),
            nullable=False,
            server_default="sgb2",
        ),
        sa.Column("valid_from", sa.Date, nullable=False),
        sa.Column("valid_to", sa.Date, nullable=True),
        sa.Column(
            "source_chunk_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("legal_chunk.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("source_quote", sa.Text, nullable=True),
        sa.Column(
            "review_status",
            sa.String(20),
            nullable=False,
            server_default="proposed",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "review_status IN ('proposed', 'validated', 'verified', 'deprecated')",
            name="ck_legal_parameter_review_status",
        ),
    )
    op.create_index(
        "idx_param_key_valid",
        "legal_parameter",
        ["parameter_key", "valid_from", "valid_to"],
    )
    op.create_index(
        "idx_param_domain",
        "legal_parameter",
        ["domain"],
    )

    # --- legal_snapshot column on case_run ---
    op.add_column(
        "case_run",
        sa.Column(
            "legal_snapshot",
            postgresql.JSONB,
            nullable=True,
        ),
    )

    # --- Seed data: Regelbedarf parameters (review_status = 'verified') ---
    op.execute(
        sa.text(
            "INSERT INTO legal_parameter "
            "(id, parameter_key, domain, valid_from, valid_to, value_numeric, unit, review_status) "
            "VALUES "
            "(gen_random_uuid(), 'sgb2.regelbedarf.rbs1', 'sgb2', '2025-01-01', '2025-12-31', 563.0, 'EUR_MONTH', 'verified'), "
            "(gen_random_uuid(), 'sgb2.regelbedarf.rbs2', 'sgb2', '2025-01-01', '2025-12-31', 506.0, 'EUR_MONTH', 'verified'), "
            "(gen_random_uuid(), 'sgb2.regelbedarf.rbs1', 'sgb2', '2024-01-01', '2024-12-31', 563.0, 'EUR_MONTH', 'verified'), "
            "(gen_random_uuid(), 'sgb2.regelbedarf.rbs2', 'sgb2', '2024-01-01', '2024-12-31', 506.0, 'EUR_MONTH', 'verified')"
        )
    )


def downgrade() -> None:
    op.drop_column("case_run", "legal_snapshot")
    op.drop_index("idx_param_domain", table_name="legal_parameter")
    op.drop_index("idx_param_key_valid", table_name="legal_parameter")
    op.drop_table("legal_parameter")
