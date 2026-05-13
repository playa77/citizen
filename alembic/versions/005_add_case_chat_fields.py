"""Add case chat fields to case_run and user_adjudication to claim.

Revision ID: 005_add_case_chat_fields
Revises: 004_add_legal_parameter
Create Date: 2026-05-13 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "005_add_case_chat_fields"
down_revision: Union[str, None] = "004_add_legal_parameter"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- case_run: title, updated_at, chat_history, user_edits ---
    op.add_column(
        "case_run",
        sa.Column("title", sa.String(200), nullable=True),
    )
    op.add_column(
        "case_run",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.add_column(
        "case_run",
        sa.Column("chat_history", postgresql.JSONB, nullable=True),
    )
    op.add_column(
        "case_run",
        sa.Column("user_edits", postgresql.JSONB, nullable=True),
    )

    # --- claim: user_adjudication ---
    op.add_column(
        "claim",
        sa.Column("user_adjudication", postgresql.JSONB, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("claim", "user_adjudication")
    op.drop_column("case_run", "user_edits")
    op.drop_column("case_run", "chat_history")
    op.drop_column("case_run", "updated_at")
    op.drop_column("case_run", "title")
