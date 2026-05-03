"""init schema

Revision ID: 001_init_schema
Revises:
Create Date: 2026-05-02 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import (
    ARRAY,
    JSONB,
    TIMESTAMP,
)
from sqlalchemy.dialects.postgresql import (
    UUID as PG_UUID,
)

from alembic import op

# revision identifiers
revision: str = "001_init_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _pk() -> sa.Column:
    """Convenience: UUID primary key with gen_random_uuid()."""
    return sa.Column(
        "id",
        PG_UUID(as_uuid=True),
        server_default=sa.text("gen_random_uuid()"),
        primary_key=True,
    )


def _ts() -> sa.Column:
    """Convenience: TIMESTAMPTZ NOT NULL DEFAULT NOW()."""
    return sa.Column(
        "created_at",
        TIMESTAMP(timezone=True),
        server_default=sa.text("NOW()"),
        nullable=False,
    )


def upgrade() -> None:
    # --- pgvector extension ---
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # --- 1. legal_source ---
    op.create_table(
        "legal_source",
        _pk(),
        sa.Column("source_type", sa.String(50), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("jurisdiction", sa.String(100), server_default="DE", nullable=False),
        sa.Column("effective_date", sa.Date, nullable=False),
        sa.Column("source_url", sa.Text, nullable=False),
        sa.Column("version_hash", sa.String(64), nullable=False),
        sa.Column("is_active", sa.Boolean, server_default="true", nullable=False),
        _ts(),
        sa.Column(
            "updated_at",
            TIMESTAMP(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "source_type IN ('sgb2', 'sgbx', 'weisung', 'bsg')",
            name="ck_legal_source_source_type",
        ),
    )
    op.create_index(
        "idx_source_type_active",
        "legal_source",
        ["source_type", "is_active"],
    )

    # --- 2. legal_chunk ---
    op.create_table(
        "legal_chunk",
        _pk(),
        sa.Column(
            "source_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("legal_source.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("unit_type", sa.String(20), nullable=False),
        sa.Column("hierarchy_path", sa.Text, nullable=False),
        sa.Column("text_content", sa.Text, nullable=False),
        sa.Column("effective_date", sa.Date, nullable=False),
        _ts(),
        sa.CheckConstraint(
            "unit_type IN ('statute', 'paragraph', 'absatz', 'satz')",
            name="ck_legal_chunk_unit_type",
        ),
    )
    op.create_index("idx_chunk_source", "legal_chunk", ["source_id"])
    op.create_index("idx_chunk_hierarchy", "legal_chunk", ["hierarchy_path"])

    # --- 3. chunk_embedding ---
    vector_dim = 1536
    op.create_table(
        "chunk_embedding",
        _pk(),
        sa.Column(
            "chunk_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("legal_chunk.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("embedding", Vector(dim=vector_dim), nullable=False),
        sa.Column("model_name", sa.String(100), nullable=False),
        _ts(),
    )
    op.execute(
        "CREATE INDEX idx_embedding_vector ON chunk_embedding "
        "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    )

    # --- 4. case_run ---
    op.create_table(
        "case_run",
        _pk(),
        sa.Column("session_id", sa.String(100), nullable=False),
        sa.Column("input_text", sa.Text, nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("latency_ms", sa.Integer, nullable=True),
        sa.Column("llm_fallback_chain", ARRAY(sa.String), nullable=True),
        _ts(),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'failed')",
            name="ck_case_run_status",
        ),
    )
    op.create_index("idx_case_session", "case_run", ["session_id"])

    # --- 5. pipeline_stage_log ---
    op.create_table(
        "pipeline_stage_log",
        _pk(),
        sa.Column(
            "case_run_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("case_run.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("stage_name", sa.String(50), nullable=False),
        sa.Column("input_snapshot", JSONB, nullable=True),
        sa.Column("output_snapshot", JSONB, nullable=True),
        sa.Column("duration_ms", sa.Integer, nullable=False),
        sa.Column("error_trace", sa.Text, nullable=True),
        _ts(),
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

    # --- 6. claim ---
    op.create_table(
        "claim",
        _pk(),
        sa.Column(
            "case_run_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("case_run.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("claim_text", sa.Text, nullable=False),
        sa.Column("confidence_score", sa.Float, nullable=False),
        sa.Column("claim_type", sa.String(30), nullable=False),
        _ts(),
        sa.CheckConstraint(
            "claim_type IN ('fact', 'interpretation', 'recommendation')",
            name="ck_claim_claim_type",
        ),
        sa.CheckConstraint(
            "confidence_score BETWEEN 0.0 AND 1.0",
            name="ck_claim_confidence_score",
        ),
    )

    # --- 7. evidence_binding ---
    op.create_table(
        "evidence_binding",
        _pk(),
        sa.Column(
            "claim_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("claim.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "chunk_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("legal_chunk.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("binding_strength", sa.Float, nullable=False),
        sa.Column("quote_excerpt", sa.Text, nullable=False),
        _ts(),
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


def downgrade() -> None:
    # Drop tables in reverse dependency order
    op.drop_table("evidence_binding")
    op.drop_table("claim")
    op.drop_table("pipeline_stage_log")
    op.drop_table("case_run")
    op.drop_table("chunk_embedding")
    op.drop_table("legal_chunk")
    op.drop_table("legal_source")
