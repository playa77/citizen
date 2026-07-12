"""Update pipeline_stage_log CHECK constraint to include stages 8-9.

Adds adversarial_review and calculation_check to the stage_name constraint,
and removes disclaimer_ack (not a pipeline stage).

Revision ID: 008_fix_stage_name_allowed
Revises: 007_sqlite_baseline
Create Date: 2026-07-12 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "008_fix_stage_name_allowed"
down_revision: Union[str, None] = "007_sqlite_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Old constraint values (for downgrade)
_OLD_STAGES = (
    "'normalization', 'classification', 'decomposition', "
    "'retrieval', 'construction', 'verification', 'generation', "
    "'disclaimer_ack'"
)

# New constraint values (all 9 pipeline stages)
_NEW_STAGES = (
    "'normalization', 'classification', 'decomposition', "
    "'retrieval', 'construction', 'verification', 'generation', "
    "'adversarial_review', 'calculation_check'"
)


def upgrade() -> None:
    # Drop old constraint
    op.execute(
        "ALTER TABLE pipeline_stage_log "
        "DROP CONSTRAINT IF EXISTS ck_pipeline_stage_log_stage_name"
    )
    # Add new constraint with all 9 stage names
    op.execute(
        "ALTER TABLE pipeline_stage_log "
        "ADD CONSTRAINT ck_pipeline_stage_log_stage_name "
        f"CHECK (stage_name IN ({_NEW_STAGES}))"
    )


def downgrade() -> None:
    # Drop new constraint
    op.execute(
        "ALTER TABLE pipeline_stage_log "
        "DROP CONSTRAINT IF EXISTS ck_pipeline_stage_log_stage_name"
    )
    # Restore old constraint
    op.execute(
        "ALTER TABLE pipeline_stage_log "
        "ADD CONSTRAINT ck_pipeline_stage_log_stage_name "
        f"CHECK (stage_name IN ({_OLD_STAGES}))"
    )
