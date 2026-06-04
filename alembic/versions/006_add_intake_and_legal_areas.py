"""Add intake_session, case_run_area, legal_area tagging, widened source_type CHECK.

Revision ID: 006_add_intake_and_legal_areas
Revises: 005_add_case_chat_fields
Create Date: 2026-06-04 00:00:00.000000

This migration broadens Citizen from a single-area (SGB II/X) engine to a
general German legal AI assistant. It adds:

1. ``intake_session`` — multi-turn intake interview state, persisted in
   the same row so that conversations can resume after disconnect and
   intake results can be referenced from a case_run.
2. ``case_run_area`` — many-to-many join table linking a case_run to one
   or more legal_areas. A case is no longer bound to a single statute.
3. ``legal_chunk.legal_area`` — explicit area tag (erbrecht,
   schenkungsrecht, familienrecht, …) on every chunk so retrieval can
   filter by area. NULL = unspecified / multi-area.
4. Widened ``legal_source.source_type`` CHECK to include the new
   statutory sources: ``erbstg``, ``hoefev``, ``kschg``, ``burlg``,
   ``tvg``. All previously-allowed values remain allowed.

All changes are additive and backward-compatible: existing rows in
``legal_chunk`` have ``legal_area = NULL``; existing ``legal_source``
rows still satisfy the (widened) CHECK constraint.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "006_add_intake_and_legal_areas"
down_revision: Union[str, None] = "005_add_case_chat_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Mirrors app.db.models.SOURCE_TYPE_ALLOWED after the widening.
ALLOWED_SOURCE_TYPES: tuple[str, ...] = (
    "sgb1", "sgb2", "sgb3", "sgb9", "sgb12", "sgbx",
    "bgb", "vwvfg", "sgg",
    "weisung", "bsg",
    "erbstg", "hoefev", "kschg", "burlg", "tvg",
)


def _sql_in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def upgrade() -> None:
    # -----------------------------------------------------------------------
    # 1. legal_source.source_type CHECK — widen to include new source types
    # -----------------------------------------------------------------------
    # Drop old constraint and add new one with the expanded allowlist.
    # The previous constraint name was ``ck_legal_source_source_type`` (see
    # 001_init_schema.py).
    op.drop_constraint(
        "ck_legal_source_source_type",
        "legal_source",
        type_="check",
    )
    op.create_check_constraint(
        "ck_legal_source_source_type",
        "legal_source",
        f"source_type IN ({_sql_in(ALLOWED_SOURCE_TYPES)})",
    )

    # -----------------------------------------------------------------------
    # 2. legal_chunk.legal_area — new nullable column + index
    # -----------------------------------------------------------------------
    op.add_column(
        "legal_chunk",
        sa.Column("legal_area", sa.String(50), nullable=True),
    )
    op.create_index(
        "idx_legal_chunk_legal_area",
        "legal_chunk",
        ["legal_area"],
    )

    # -----------------------------------------------------------------------
    # 3. intake_session — new table for multi-turn intake state
    # -----------------------------------------------------------------------
    op.create_table(
        "intake_session",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("session_id", sa.String(100), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("turn_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("max_turns", sa.Integer, nullable=False, server_default="8"),
        sa.Column("messages", postgresql.JSONB, nullable=True),
        sa.Column("intake_result", postgresql.JSONB, nullable=True),
        sa.Column("primary_area", sa.String(50), nullable=True),
        sa.Column("secondary_areas", postgresql.ARRAY(sa.String(50)), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "status IN ('active', 'completed', 'abandoned')",
            name="ck_intake_session_status",
        ),
        sa.CheckConstraint(
            "turn_count >= 0 AND turn_count <= max_turns",
            name="ck_intake_session_turn_count",
        ),
    )
    op.create_index("idx_intake_session_id", "intake_session", ["session_id"])

    # -----------------------------------------------------------------------
    # 4. case_run_area — many-to-many join (case_run ↔ legal_area)
    # -----------------------------------------------------------------------
    op.create_table(
        "case_run_area",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "case_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("case_run.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("legal_area", sa.String(50), nullable=False),
        sa.Column("is_primary", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column(
            "intake_session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("intake_session.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("case_run_id", "legal_area", name="uq_case_run_area_case_area"),
        sa.CheckConstraint(
            "legal_area IN ("
            "'sozialrecht', 'erbrecht', 'schenkungsrecht', 'familienrecht', "
            "'mietrecht', 'arbeitsrecht', 'vertragsrecht', 'verwaltungsrecht', "
            "'strafrecht', 'andere'"
            ")",
            name="ck_case_run_area_legal_area",
        ),
    )
    op.create_index("idx_case_run_area_case", "case_run_area", ["case_run_id"])
    op.create_index("idx_case_run_area_area", "case_run_area", ["legal_area"])


def downgrade() -> None:
    # -----------------------------------------------------------------------
    # Reverse: case_run_area → intake_session → legal_chunk.legal_area → CHECK
    # -----------------------------------------------------------------------
    op.drop_index("idx_case_run_area_area", table_name="case_run_area")
    op.drop_index("idx_case_run_area_case", table_name="case_run_area")
    op.drop_table("case_run_area")

    op.drop_index("idx_intake_session_id", table_name="intake_session")
    op.drop_table("intake_session")

    op.drop_index("idx_legal_chunk_legal_area", table_name="legal_chunk")
    op.drop_column("legal_chunk", "legal_area")

    # Restore the original narrower CHECK constraint.
    ORIGINAL_ALLOWED: tuple[str, ...] = (
        "sgb1", "sgb2", "sgb3", "sgb9", "sgb12", "sgbx",
        "bgb", "vwvfg", "sgg",
        "weisung", "bsg",
    )
    op.drop_constraint(
        "ck_legal_source_source_type",
        "legal_source",
        type_="check",
    )
    op.create_check_constraint(
        "ck_legal_source_source_type",
        "legal_source",
        f"source_type IN ({_sql_in(ORIGINAL_ALLOWED)})",
    )
