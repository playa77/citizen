"""Collapse the former SQLite-branch schema changes into the single PG DAG.

Applies the cumulative schema content of the deleted SQLite-only migrations
008/009/010 to PostgreSQL so a fresh deploy reaches the complete schema
through one linear chain (resolves pending D-007). All operations are
idempotent: production instances that received these changes via manual DDL
(DECISIONS.md §D-005) can replay this migration safely.

Revision ID: 012_pg_collapse_sqlite_branch
Revises: 011_pg_legal_chunk_text_hash
Create Date: 2026-08-25 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "012_pg_collapse_sqlite_branch"
down_revision: Union[str, None] = "011_pg_legal_chunk_text_hash"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# All nine pipeline stages (content of former migration 008) plus
# 'disclaimer_ack': app/services/audit.py persists one disclaimer_ack row per
# run (WP-015 acceptance: "7 stages + 1 disclaimer_ack"), so the constraint
# must allow it. Former migration 008 dropped the value, which made every
# audit-trail insert violate this constraint on PostgreSQL.
_NEW_STAGES = (
    "'normalization', 'classification', 'decomposition', "
    "'retrieval', 'construction', 'verification', 'generation', "
    "'adversarial_review', 'calculation_check', 'disclaimer_ack'"
)


def upgrade() -> None:
    # Former 008: pipeline_stage_log CHECK constraint with all 9 stages.
    op.execute(
        "ALTER TABLE pipeline_stage_log "
        "DROP CONSTRAINT IF EXISTS ck_pipeline_stage_log_stage_name"
    )
    op.execute(
        "ALTER TABLE pipeline_stage_log "
        "ADD CONSTRAINT ck_pipeline_stage_log_stage_name "
        f"CHECK (stage_name IN ({_NEW_STAGES}))"
    )

    # Former 009: regime/notes columns on legal_parameter.
    op.execute("ALTER TABLE legal_parameter ADD COLUMN IF NOT EXISTS regime VARCHAR(50)")
    op.execute("ALTER TABLE legal_parameter ADD COLUMN IF NOT EXISTS notes TEXT")

    # Former 010: pii_mapping JSON column on case_run.
    op.execute("ALTER TABLE case_run ADD COLUMN IF NOT EXISTS pii_mapping JSON")


def downgrade() -> None:
    op.drop_column("case_run", "pii_mapping")
    op.drop_column("legal_parameter", "notes")
    op.drop_column("legal_parameter", "regime")
