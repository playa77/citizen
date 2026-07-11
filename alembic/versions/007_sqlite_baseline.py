"""sqlite baseline — create all 14 tables with SQLite-compatible types

Revision ID: 007_sqlite_baseline
Revises:
Create Date: 2026-07-10 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "007_sqlite_baseline"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # -------------------------------------------------------------------
    # 1. legal_source
    # -------------------------------------------------------------------
    op.create_table(
        "legal_source",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source_type", sa.String(50), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("jurisdiction", sa.String(100), nullable=False, server_default="DE"),
        sa.Column("effective_date", sa.Date, nullable=False),
        sa.Column("source_url", sa.Text, nullable=False),
        sa.Column("version_hash", sa.String(64), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint(
            "source_type IN ("
            "'sgb1', 'sgb2', 'sgb3', 'sgb9', 'sgb12', 'sgbx', "
            "'bgb', 'vwvfg', 'sgg', "
            "'weisung', 'bsg', "
            "'erbstg', 'hoefev', 'kschg', 'burlg', 'tvg'"
            ")",
            name="ck_legal_source_source_type",
        ),
        sa.UniqueConstraint("source_type", "version_hash", name="uq_legal_source_type_version"),
    )
    op.create_index("idx_source_type_active", "legal_source", ["source_type", "is_active"])

    # -------------------------------------------------------------------
    # 2. legal_chunk
    # -------------------------------------------------------------------
    op.create_table(
        "legal_chunk",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "source_id",
            sa.String(36),
            sa.ForeignKey("legal_source.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("unit_type", sa.String(20), nullable=False),
        sa.Column("hierarchy_path", sa.Text, nullable=False),
        sa.Column("text_content", sa.Text, nullable=False),
        sa.Column("effective_date", sa.Date, nullable=False),
        sa.Column("legal_area", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint(
            "unit_type IN ('statute', 'paragraph', 'absatz', 'satz')",
            name="ck_legal_chunk_unit_type",
        ),
        sa.UniqueConstraint(
            "source_id", "hierarchy_path", "text_content",
            name="uq_legal_chunk_source_hierarchy_text",
        ),
    )
    op.create_index("idx_chunk_source", "legal_chunk", ["source_id"])
    op.create_index("idx_chunk_hierarchy", "legal_chunk", ["hierarchy_path"])
    op.create_index("idx_legal_chunk_legal_area", "legal_chunk", ["legal_area"])

    # -------------------------------------------------------------------
    # 3. chunk_embedding
    # -------------------------------------------------------------------
    op.create_table(
        "chunk_embedding",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "chunk_id",
            sa.String(36),
            sa.ForeignKey("legal_chunk.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # SQLite stores embedding as BLOB. Use LargeBinary (maps to BLOB).
        sa.Column("embedding", sa.LargeBinary, nullable=False),
        sa.Column("model_name", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("chunk_id", "model_name", name="uq_chunk_embedding_chunk_model"),
    )

    # -------------------------------------------------------------------
    # 4. case_run
    # -------------------------------------------------------------------
    op.create_table(
        "case_run",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("session_id", sa.String(100), nullable=False),
        sa.Column("input_text", sa.Text, nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("latency_ms", sa.Integer, nullable=True),
        sa.Column("llm_fallback_chain", sa.JSON, nullable=True),
        sa.Column("legal_snapshot", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("title", sa.String(200), nullable=True),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("chat_history", sa.JSON, nullable=True),
        sa.Column("user_edits", sa.JSON, nullable=True),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'failed')",
            name="ck_case_run_status",
        ),
    )
    op.create_index("idx_case_session", "case_run", ["session_id"])

    # -------------------------------------------------------------------
    # 5. pipeline_stage_log
    # -------------------------------------------------------------------
    op.create_table(
        "pipeline_stage_log",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "case_run_id",
            sa.String(36),
            sa.ForeignKey("case_run.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("stage_name", sa.String(50), nullable=False),
        sa.Column("input_snapshot", sa.JSON, nullable=True),
        sa.Column("output_snapshot", sa.JSON, nullable=True),
        sa.Column("duration_ms", sa.Integer, nullable=False),
        sa.Column("error_trace", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint(
            "stage_name IN ("
            "'normalization', 'classification', 'decomposition', "
            "'retrieval', 'construction', 'verification', 'generation', "
            "'disclaimer_ack'"
            ")",
            name="ck_pipeline_stage_log_stage_name",
        ),
    )
    op.create_index("idx_stage_case", "pipeline_stage_log", ["case_run_id"])

    # -------------------------------------------------------------------
    # 6. claim
    # -------------------------------------------------------------------
    op.create_table(
        "claim",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "case_run_id",
            sa.String(36),
            sa.ForeignKey("case_run.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("claim_text", sa.Text, nullable=False),
        sa.Column("confidence_score", sa.Float, nullable=False),
        sa.Column("claim_type", sa.String(30), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("user_adjudication", sa.JSON, nullable=True),
        sa.CheckConstraint(
            "claim_type IN ('fact', 'interpretation', 'recommendation')",
            name="ck_claim_claim_type",
        ),
        sa.CheckConstraint(
            "confidence_score BETWEEN 0.0 AND 1.0",
            name="ck_claim_confidence_score",
        ),
    )

    # -------------------------------------------------------------------
    # 7. evidence_binding
    # -------------------------------------------------------------------
    op.create_table(
        "evidence_binding",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "claim_id",
            sa.String(36),
            sa.ForeignKey("claim.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "chunk_id",
            sa.String(36),
            sa.ForeignKey("legal_chunk.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("binding_strength", sa.Float, nullable=False),
        sa.Column("quote_excerpt", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint(
            "binding_strength BETWEEN 0.0 AND 1.0",
            name="ck_evidence_binding_binding_strength",
        ),
    )
    op.create_index(
        "idx_binding_unique",
        "evidence_binding",
        ["claim_id", "chunk_id"],
        unique=True,
    )

    # -------------------------------------------------------------------
    # 8. cache_entry
    # -------------------------------------------------------------------
    op.create_table(
        "cache_entry",
        sa.Column("key", sa.String(128), primary_key=True),
        sa.Column("value_json", sa.JSON, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("expires_at", sa.DateTime, nullable=True),
    )
    op.create_index("idx_cache_expires", "cache_entry", ["expires_at"])

    # -------------------------------------------------------------------
    # 9. legal_parameter
    # -------------------------------------------------------------------
    op.create_table(
        "legal_parameter",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("parameter_key", sa.String(200), nullable=False),
        sa.Column("value_numeric", sa.Float, nullable=True),
        sa.Column("value_json", sa.JSON, nullable=True),
        sa.Column("value_text", sa.Text, nullable=True),
        sa.Column("unit", sa.String(50), nullable=True),
        sa.Column("domain", sa.String(50), nullable=False, server_default="sgb2"),
        sa.Column("valid_from", sa.Date, nullable=False),
        sa.Column("valid_to", sa.Date, nullable=True),
        sa.Column(
            "source_chunk_id",
            sa.String(36),
            sa.ForeignKey("legal_chunk.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("source_quote", sa.Text, nullable=True),
        sa.Column("review_status", sa.String(20), nullable=False, server_default="proposed"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
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

    # -------------------------------------------------------------------
    # 10. conversation
    # -------------------------------------------------------------------
    op.create_table(
        "conversation",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("title", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )

    # -------------------------------------------------------------------
    # 11. conversation_message
    # -------------------------------------------------------------------
    op.create_table(
        "conversation_message",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "conversation_id",
            sa.String(36),
            sa.ForeignKey("conversation.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint(
            "role IN ('user', 'assistant', 'system')",
            name="ck_conversation_message_role",
        ),
    )
    op.create_index(
        "idx_message_conversation",
        "conversation_message",
        ["conversation_id"],
    )

    # -------------------------------------------------------------------
    # 12. conversation_document
    # -------------------------------------------------------------------
    op.create_table(
        "conversation_document",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "conversation_id",
            sa.String(36),
            sa.ForeignKey("conversation.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("original_filename", sa.String(500), nullable=False),
        sa.Column("normalized_text", sa.Text, nullable=False),
        sa.Column(
            "case_run_id",
            sa.String(36),
            sa.ForeignKey("case_run.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index(
        "idx_document_conversation",
        "conversation_document",
        ["conversation_id"],
    )

    # -------------------------------------------------------------------
    # 13. intake_session
    # -------------------------------------------------------------------
    op.create_table(
        "intake_session",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("session_id", sa.String(100), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("turn_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("max_turns", sa.Integer, nullable=False, server_default="8"),
        sa.Column("messages", sa.JSON, nullable=True),
        sa.Column("intake_result", sa.JSON, nullable=True),
        sa.Column("primary_area", sa.String(50), nullable=True),
        sa.Column("secondary_areas", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
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

    # -------------------------------------------------------------------
    # 14. case_run_area
    # -------------------------------------------------------------------
    op.create_table(
        "case_run_area",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "case_run_id",
            sa.String(36),
            sa.ForeignKey("case_run.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("legal_area", sa.String(50), nullable=False),
        sa.Column("is_primary", sa.Boolean, nullable=False, server_default=sa.text("0")),
        sa.Column(
            "intake_session_id",
            sa.String(36),
            sa.ForeignKey("intake_session.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
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
    """Drop all tables in reverse dependency order."""
    op.drop_table("case_run_area")
    op.drop_table("intake_session")
    op.drop_table("conversation_document")
    op.drop_table("conversation_message")
    op.drop_table("conversation")
    op.drop_table("legal_parameter")
    op.drop_table("cache_entry")
    op.drop_table("evidence_binding")
    op.drop_table("claim")
    op.drop_table("pipeline_stage_log")
    op.drop_table("case_run")
    op.drop_table("chunk_embedding")
    op.drop_table("legal_chunk")
    op.drop_table("legal_source")
