"""Replace text_content unique constraint with text_hash (MD5) to fix btree index size limit.

The original unique constraint on (source_id, hierarchy_path, text_content) fails
when text_content exceeds ~2704 bytes (PostgreSQL btree v4 maximum index row size).
MD5 hash (32 chars) is well within btree limits and sufficient for deduplication.

Revision ID: 011_pg_legal_chunk_text_hash
Revises: 006_add_intake_and_legal_areas
Create Date: 2026-07-19 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "011_pg_legal_chunk_text_hash"
down_revision: str | None = "006_add_intake_and_legal_areas"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Add text_hash column (nullable initially for backfill)
    op.add_column("legal_chunk", sa.Column("text_hash", sa.String(64), nullable=True))

    # 2. Backfill using PostgreSQL's built-in md5() function
    op.execute("UPDATE legal_chunk SET text_hash = md5(text_content)")

    # 3. Set NOT NULL
    op.alter_column("legal_chunk", "text_hash", nullable=False)

    # 4. Drop old unique constraint on text_content
    op.drop_constraint(
        "uq_legal_chunk_source_hierarchy_text",
        "legal_chunk",
        type_="unique",
    )

    # 5. Create new unique constraint on text_hash
    op.create_unique_constraint(
        "uq_legal_chunk_source_hierarchy_hash",
        "legal_chunk",
        ["source_id", "hierarchy_path", "text_hash"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_legal_chunk_source_hierarchy_hash",
        "legal_chunk",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_legal_chunk_source_hierarchy_text",
        "legal_chunk",
        ["source_id", "hierarchy_path", "text_content"],
    )
    op.drop_column("legal_chunk", "text_hash")
