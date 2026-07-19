"""Replace text_content unique constraint with text_hash (MD5) for SQLite.

Mirrors the PostgreSQL migration 011_pg_legal_chunk_text_hash but uses
Python hashlib for backfill (SQLite has no built-in md5() function) and
batch_alter_table for constraint changes (SQLite doesn't support
DROP CONSTRAINT directly).

Revision ID: 011_sqlite_legal_chunk_text_hash
Revises: 010_add_pii_mapping_to_case_run
Create Date: 2026-07-19 12:00:00.000000
"""

import hashlib
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "011_sqlite_legal_chunk_text_hash"
down_revision: str | None = "010_add_pii_mapping_to_case_run"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Add text_hash column (nullable initially for backfill)
    op.add_column("legal_chunk", sa.Column("text_hash", sa.String(64), nullable=True))

    # 2. Backfill using Python hashlib (SQLite has no built-in md5() function)
    bind = op.get_bind()
    rows = bind.execute(
        sa.text("SELECT id, text_content FROM legal_chunk WHERE text_hash IS NULL")
    ).fetchall()
    for row in rows:
        chunk_id = row[0]
        text_content = row[1]
        text_hash = hashlib.md5(text_content.encode("utf-8")).hexdigest()
        bind.execute(
            sa.text("UPDATE legal_chunk SET text_hash = :hash WHERE id = :id"),
            {"hash": text_hash, "id": chunk_id},
        )

    # 3. Rebuild table: set text_hash NOT NULL, swap unique constraint.
    # SQLite doesn't support ALTER COLUMN or DROP CONSTRAINT directly,
    # so we use batch_alter_table which recreates the table.
    with op.batch_alter_table("legal_chunk") as batch_op:
        batch_op.alter_column("text_hash", nullable=False)
        batch_op.drop_constraint("uq_legal_chunk_source_hierarchy_text", type_="unique")
        batch_op.create_unique_constraint(
            "uq_legal_chunk_source_hierarchy_hash",
            ["source_id", "hierarchy_path", "text_hash"],
        )


def downgrade() -> None:
    with op.batch_alter_table("legal_chunk") as batch_op:
        batch_op.drop_constraint("uq_legal_chunk_source_hierarchy_hash", type_="unique")
        batch_op.create_unique_constraint(
            "uq_legal_chunk_source_hierarchy_text",
            ["source_id", "hierarchy_path", "text_content"],
        )
        batch_op.alter_column("text_hash", nullable=True)
    op.drop_column("legal_chunk", "text_hash")
