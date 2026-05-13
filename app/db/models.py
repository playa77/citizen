"""SQLAlchemy 2.0 declarative ORM models for Citizen.

Mirrors the DDL from Technical Specification §4.1 exactly:
  legal_source → legal_chunk → chunk_embedding
  case_run → pipeline_stage_log, claim → evidence_binding
"""

# Semantic Version: 0.1.0

from datetime import date, datetime
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
    UniqueConstraint,
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


def _sql_in(values: tuple[str, ...]) -> str:
    """Build a comma-separated list of SQL-safe single-quoted values."""
    return ", ".join(f"'{value}'" for value in values)


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""


# ---------------------------------------------------------------------------
# 1. legal_source
# ---------------------------------------------------------------------------

SOURCE_TYPE_ALLOWED = (
    "sgb1", "sgb2", "sgb3", "sgb9", "sgb12", "sgbx",
    "bgb", "vwvfg", "sgg",
    "weisung", "bsg",
)


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
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
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
            f"source_type IN ({_sql_in(SOURCE_TYPE_ALLOWED)})",
            name="ck_legal_source_source_type",
        ),
        Index("idx_source_type_active", "source_type", "is_active"),
        UniqueConstraint("source_type", "version_hash", name="uq_legal_source_type_version"),
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
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
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
            f"unit_type IN ({_sql_in(UNIT_TYPE_ALLOWED)})",
            name="ck_legal_chunk_unit_type",
        ),
        Index("idx_chunk_source", "source_id"),
        Index("idx_chunk_hierarchy", "hierarchy_path"),
        UniqueConstraint("source_id", "hierarchy_path", "text_content", name="uq_legal_chunk_source_hierarchy_text"),
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
        UniqueConstraint("chunk_id", "model_name", name="uq_chunk_embedding_chunk_model"),
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
    legal_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now(), onupdate=func.now()
    )
    chat_history: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    user_edits: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    # Relationships
    stage_logs: Mapped[list["PipelineStageLog"]] = relationship(
        "PipelineStageLog", back_populates="case_run", cascade="all, delete-orphan"
    )
    claims: Mapped[list["Claim"]] = relationship(
        "Claim", back_populates="case_run", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint(
            f"status IN ({_sql_in(CASE_STATUS_ALLOWED)})",
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
    "disclaimer_ack",
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
            f"stage_name IN ({_sql_in(STAGE_NAME_ALLOWED)})",
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
    user_adjudication: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    # Relationships
    case_run: Mapped["CaseRun"] = relationship("CaseRun", back_populates="claims")
    evidence_bindings: Mapped[list["EvidenceBinding"]] = relationship(
        "EvidenceBinding", back_populates="claim", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint(
            f"claim_type IN ({_sql_in(CLAIM_TYPE_ALLOWED)})",
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


# ---------------------------------------------------------------------------
# 8. cache_entry
# ---------------------------------------------------------------------------


class CacheEntry(Base):
    """Simple key-value cache for expensive operations (embeddings, triage results)."""

    __tablename__ = "cache_entry"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
    expires_at: Mapped[datetime | None] = mapped_column(nullable=True)

    __table_args__ = (
        Index("idx_cache_expires", "expires_at"),
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


# ---------------------------------------------------------------------------
# 8b. legal_parameter
# ---------------------------------------------------------------------------


class LegalParameter(Base):
    """Versioned legal parameter sourced from the legal corpus.

    Each row represents one scalar or structured value (e.g., Regelbedarf
    amount, Freibetrag band, Aufrechnung percentage) with a validity window
    and an evidence backlink to the source legal_chunk.
    """

    __tablename__ = "legal_parameter"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    parameter_key: Mapped[str] = mapped_column(String(200), nullable=False)
    value_numeric: Mapped[float | None] = mapped_column(Float, nullable=True)
    value_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    value_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    unit: Mapped[str | None] = mapped_column(String(50), nullable=True)
    domain: Mapped[str] = mapped_column(String(50), nullable=False, server_default="sgb2")
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    source_chunk_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("legal_chunk.id", ondelete="SET NULL"),
        nullable=True,
    )
    source_quote: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="proposed"
    )
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())

    # Relationships
    source_chunk: Mapped["LegalChunk | None"] = relationship("LegalChunk")

    __table_args__ = (
        CheckConstraint(
            "review_status IN ('proposed', 'validated', 'verified', 'deprecated')",
            name="ck_legal_parameter_review_status",
        ),
        Index("idx_param_key_valid", "parameter_key", "valid_from", "valid_to"),
        Index("idx_param_domain", "domain"),
    )


# ---------------------------------------------------------------------------
# 9. conversation
# ---------------------------------------------------------------------------


class Conversation(Base):
    """A multi-turn conversation with the reasoning engine."""

    __tablename__ = "conversation"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now(), onupdate=func.now(),
    )

    # Relationships
    messages: Mapped[list["ConversationMessage"]] = relationship(
        "ConversationMessage", back_populates="conversation",
        cascade="all, delete-orphan", order_by="ConversationMessage.created_at",
    )
    documents: Mapped[list["ConversationDocument"]] = relationship(
        "ConversationDocument", back_populates="conversation",
        cascade="all, delete-orphan",
    )


# ---------------------------------------------------------------------------
# 10. conversation_message
# ---------------------------------------------------------------------------

MESSAGE_ROLE_ALLOWED = ("user", "assistant", "system")


class ConversationMessage(Base):
    """A single message within a conversation."""

    __tablename__ = "conversation_message"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    conversation_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("conversation.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now(),
    )

    # Relationships
    conversation: Mapped["Conversation"] = relationship(
        "Conversation", back_populates="messages",
    )

    __table_args__ = (
        CheckConstraint(
            f"role IN ({_sql_in(MESSAGE_ROLE_ALLOWED)})",
            name="ck_conversation_message_role",
        ),
        Index("idx_message_conversation", "conversation_id"),
    )


# ---------------------------------------------------------------------------
# 11. conversation_document
# ---------------------------------------------------------------------------


class ConversationDocument(Base):
    """A document attached to a conversation — can optionally link to a case_run."""

    __tablename__ = "conversation_document"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    conversation_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("conversation.id", ondelete="CASCADE"),
        nullable=False,
    )
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    normalized_text: Mapped[str] = mapped_column(Text, nullable=False)
    case_run_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("case_run.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now(),
    )

    # Relationships
    conversation: Mapped["Conversation"] = relationship(
        "Conversation", back_populates="documents",
    )

    __table_args__ = (
        Index("idx_document_conversation", "conversation_id"),
    )
