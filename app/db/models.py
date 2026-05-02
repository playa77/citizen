"""SQLAlchemy 2.0 declarative ORM models for Citizen (v1.0).

Mirrors the DDL from Technical Specification §4.1 exactly:
  legal_source → legal_chunk → chunk_embedding
  case_run → pipeline_stage_log, claim → evidence_binding
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)

VECTOR_DIM = 1536  # Default embedding dimension


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""


# ---------------------------------------------------------------------------
# 1. legal_source
# ---------------------------------------------------------------------------

SOURCE_TYPE_ALLOWED = ("sgb2", "sgbx", "weisung", "bsg")


class LegalSource(Base):
    """Root record for a legal document."""

    __tablename__ = "legal_source"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    jurisdiction: Mapped[str] = mapped_column(String(100), nullable=False, server_default="DE")
    effective_date: Mapped[datetime] = mapped_column(Date, nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    version_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())

    # Relationships
    chunks: Mapped[list["LegalChunk"]] = relationship(
        "LegalChunk", back_populates="source", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint(
            f"source_type IN ('{",".join(SOURCE_TYPE_ALLOWED)}')",
            name="ck_legal_source_source_type",
        ),
        Index("idx_source_type_active", "source_type", "is_active"),
    )


# ---------------------------------------------------------------------------
# 2. legal_chunk
# ---------------------------------------------------------------------------

UNIT_TYPE_ALLOWED = ("statute", "paragraph", "absatz", "satz")


class LegalChunk(Base):
    """Hierarchical unit of law (e.g., SGB II > § 31 > Abs. 1 > Satz 2)."""

    __tablename__ = "legal_chunk"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    source_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("legal_source.id", ondelete="CASCADE"),
        nullable=False,
    )
    unit_type: Mapped[str] = mapped_column(String(20), nullable=False)
    hierarchy_path: Mapped[str] = mapped_column(Text, nullable=False)
    text_content: Mapped[str] = mapped_column(Text, nullable=False)
    effective_date: Mapped[datetime] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())

    # Relationships
    source: Mapped["LegalSource"] = relationship("LegalSource", back_populates="chunks")
    embeddings: Mapped[list["ChunkEmbedding"]] = relationship(
        "ChunkEmbedding", back_populates="chunk", cascade="all, delete-orphan"
    )
    evidence_bindings: Mapped[list["EvidenceBinding"]] = relationship(
        "EvidenceBinding", back_populates="chunk"
    )

    __table_args__ = (
        CheckConstraint(
            f"unit_type IN ('{",".join(UNIT_TYPE_ALLOWED)}')",
            name="ck_legal_chunk_unit_type",
        ),
        Index("idx_chunk_source", "source_id"),
        Index("idx_chunk_hierarchy", "hierarchy_path"),
    )


# ---------------------------------------------------------------------------
# 3. chunk_embedding
# ---------------------------------------------------------------------------


class ChunkEmbedding(Base):
    """Dense vector representation of a legal_chunk."""

    __tablename__ = "chunk_embedding"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    chunk_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("legal_chunk.id", ondelete="CASCADE"),
        nullable=False,
    )
    embedding: Mapped[Any] = mapped_column(Vector(VECTOR_DIM), nullable=False)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())

    # Relationships
    chunk: Mapped["LegalChunk"] = relationship("LegalChunk", back_populates="embeddings")

    __table_args__ = (
        Index(
            "idx_embedding_vector",
            "embedding",
            postgresql_using="ivfflat",
            postgresql_with={"lists": 100},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )


# ---------------------------------------------------------------------------
# 4. case_run
# ---------------------------------------------------------------------------

CASE_STATUS_ALLOWED = ("queued", "running", "completed", "failed")


class CaseRun(Base):
    """Represents a single analysis session."""

    __tablename__ = "case_run"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    session_id: Mapped[str] = mapped_column(String(100), nullable=False)
    input_text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    llm_fallback_chain: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())

    # Relationships
    stage_logs: Mapped[list["PipelineStageLog"]] = relationship(
        "PipelineStageLog", back_populates="case_run", cascade="all, delete-orphan"
    )
    claims: Mapped[list["Claim"]] = relationship(
        "Claim", back_populates="case_run", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint(
            f"status IN ('{",".join(CASE_STATUS_ALLOWED)}')",
            name="ck_case_run_status",
        ),
        Index("idx_case_session", "session_id"),
    )


# ---------------------------------------------------------------------------
# 5. pipeline_stage_log
# ---------------------------------------------------------------------------

STAGE_NAME_ALLOWED = (
    "normalization",
    "classification",
    "decomposition",
    "retrieval",
    "construction",
    "verification",
    "generation",
)


class PipelineStageLog(Base):
    """Immutable audit record for each pipeline stage."""

    __tablename__ = "pipeline_stage_log"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    case_run_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("case_run.id", ondelete="CASCADE"),
        nullable=False,
    )
    stage_name: Mapped[str] = mapped_column(String(50), nullable=False)
    input_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    output_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    error_trace: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())

    # Relationships
    case_run: Mapped["CaseRun"] = relationship("CaseRun", back_populates="stage_logs")

    __table_args__ = (
        CheckConstraint(
            f"stage_name IN ('{",".join(STAGE_NAME_ALLOWED)}')",
            name="ck_pipeline_stage_log_stage_name",
        ),
        Index("idx_stage_case", "case_run_id"),
    )


# ---------------------------------------------------------------------------
# 6. claim
# ---------------------------------------------------------------------------

CLAIM_TYPE_ALLOWED = ("fact", "interpretation", "recommendation")


class Claim(Base):
    """Atomic legal assertion generated in Stage 5."""

    __tablename__ = "claim"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    case_run_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("case_run.id", ondelete="CASCADE"),
        nullable=False,
    )
    claim_text: Mapped[str] = mapped_column(Text, nullable=False)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False)
    claim_type: Mapped[str] = mapped_column(String(30), nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())

    # Relationships
    case_run: Mapped["CaseRun"] = relationship("CaseRun", back_populates="claims")
    evidence_bindings: Mapped[list["EvidenceBinding"]] = relationship(
        "EvidenceBinding", back_populates="claim", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint(
            f"claim_type IN ('{",".join(CLAIM_TYPE_ALLOWED)}')",
            name="ck_claim_claim_type",
        ),
        CheckConstraint(
            "confidence_score BETWEEN 0.0 AND 1.0",
            name="ck_claim_confidence_score",
        ),
    )


# ---------------------------------------------------------------------------
# 7. evidence_binding
# ---------------------------------------------------------------------------


class EvidenceBinding(Base):
    """Explicit link between a claim and a legal_chunk."""

    __tablename__ = "evidence_binding"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    claim_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("claim.id", ondelete="CASCADE"),
        nullable=False,
    )
    chunk_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("legal_chunk.id", ondelete="RESTRICT"),
        nullable=False,
    )
    binding_strength: Mapped[float] = mapped_column(Float, nullable=False)
    quote_excerpt: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())

    # Relationships
    claim: Mapped["Claim"] = relationship("Claim", back_populates="evidence_bindings")
    chunk: Mapped["LegalChunk"] = relationship("LegalChunk", back_populates="evidence_bindings")

    __table_args__ = (
        CheckConstraint(
            "binding_strength BETWEEN 0.0 AND 1.0",
            name="ck_evidence_binding_binding_strength",
        ),
        Index(
            "idx_binding_unique",
            "claim_id",
            "chunk_id",
            unique=True,
        ),
    )
