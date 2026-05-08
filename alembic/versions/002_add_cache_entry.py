"""Add cache_entry table (WP-011).

Revision ID: 002_add_cache_entry
Revises: 001_init_schema
Create Date: 2026-05-08 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "002_add_cache_entry"
down_revision: Union[str, None] = "001_init_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "cache_entry",
        sa.Column("key", sa.String(128), primary_key=True),
        sa.Column(
            "value_json",
            postgresql.JSONB,
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=False),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=False),
            nullable=True,
        ),
    )
    op.create_index("idx_cache_expires", "cache_entry", ["expires_at"])


def downgrade() -> None:
    op.drop_index("idx_cache_expires", table_name="cache_entry")
    op.drop_table("cache_entry")
