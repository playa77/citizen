"""SQLAlchemy 2.0 declarative ORM models for Citizen.

Mirrors the DDL from Technical Specification §4.1 exactly:
  legal_source → legal_chunk → chunk_embedding
  case_run → pipeline_stage_log, claim → evidence_binding

Plus (migration 006):
  intake_session — multi-turn intake interview state
  case_run_area  — many-to-many link between a case_run and one or more
                   legal_areas (sozialrecht, erbrecht, …)
  legal_chunk.legal_area — explicit area tag for retrieval filtering

Plus (migration 013, WP-94):
  legal_module — one row per installed module, synced by the registry
  case_run_area.module_id / module_version — the module (and its version)
                   a case ran with; the area-key CHECK is gone (D-057)
"""

# Semantic Version: 0.7.0 | 2026-11-17 — P11: ModuleUpdate (WP-111), CorpusSourceWatch
# (WP-113), migration 015.
# 0.6.0 | 2026-11-16 — WP-100: CaseDossier (case_dossier
# table, migration 014, D-064).
# 0.5.0 | 2026-11-16 — WP-94: LegalModule; CaseRunArea
# module_id (FK) + module_version, area CHECK dropped; LEGAL_AREA_ALLOWED /
# LEGAL_AREA_TIER removed (registry is the source of truth); legal_parameter
# domain holds the module id, column default dropped.

import uuid
from datetime import date, datetime
from typing import Any

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
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
    "sgb1",
    "sgb2",
    "sgb3",
    "sgb9",
    "sgb12",
    "sgbx",
    "bgb",
    "vwvfg",
    "sgg",
    "weisung",
    "bsg",
    # New: general-legal-assistant legal areas (migration 006).
    "erbstg",
    "hoefev",
    "kschg",
    "burlg",
    "tvg",
    # D-071 / WP-130: additive source catalog, migration 016.
    "zpo",
    "inso",
    "rdg",
    "rvg",
    # WP-131: tenancy statutes and explicitly imported state-source evidence.
    "betrkv",
    "heizkostenv",
    "landes_mietrecht",
    # D-074 / WP-132: federal employment sources, migration 018.
    "tzbfg",
    "entgfg",
    "milog",
    "muschg",
    "arbzg",
    "arbgg",
    # D-075 / WP-133: contract sources, migration 019.
    "egbgb",
    "eu261",
)


class LegalSource(Base):
    """Root record for a legal document."""

    __tablename__ = "legal_source"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    jurisdiction: Mapped[str] = mapped_column(String(100), nullable=False, server_default="DE")
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    version_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa.text("1"))
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

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("legal_source.id", ondelete="CASCADE"),
        nullable=False,
    )
    unit_type: Mapped[str] = mapped_column(String(20), nullable=False)
    hierarchy_path: Mapped[str] = mapped_column(Text, nullable=False)
    text_content: Mapped[str] = mapped_column(Text, nullable=False)
    text_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    legal_area: Mapped[str | None] = mapped_column(String(50), nullable=True)
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
        Index("idx_legal_chunk_legal_area", "legal_area"),
        UniqueConstraint(
            "source_id",
            "hierarchy_path",
            "text_hash",
            name="uq_legal_chunk_source_hierarchy_hash",
        ),
    )


# ---------------------------------------------------------------------------
# 3. chunk_embedding
# ---------------------------------------------------------------------------


class ChunkEmbedding(Base):
    """Dense vector representation of a legal_chunk."""

    __tablename__ = "chunk_embedding"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("legal_chunk.id", ondelete="CASCADE"),
        nullable=False,
    )
    # pgvector column — single backend since D-024. The former
    # LargeBinary-for-dialect-portability mapping forced raw-SQL `::vector`
    # cast workarounds (D-014); with Vector typed directly, ORM inserts bind
    # list[float] correctly.
    embedding: Mapped[Any] = mapped_column(Vector(VECTOR_DIM), nullable=False)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())

    # Relationships
    chunk: Mapped["LegalChunk"] = relationship("LegalChunk", back_populates="embeddings")

    __table_args__ = (
        UniqueConstraint("chunk_id", "model_name", name="uq_chunk_embedding_chunk_model"),
    )


# ---------------------------------------------------------------------------
# 4. case_run
# ---------------------------------------------------------------------------

CASE_STATUS_ALLOWED = ("queued", "running", "completed", "failed")


class CaseRun(Base):
    """Represents a single analysis session."""

    __tablename__ = "case_run"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    session_id: Mapped[str] = mapped_column(String(100), nullable=False)
    input_text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    llm_fallback_chain: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    legal_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now(), onupdate=func.now()
    )
    chat_history: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    user_edits: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    pii_mapping: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

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
    "adversarial_review",
    "calculation_check",
)


class PipelineStageLog(Base):
    """Immutable audit record for each pipeline stage."""

    __tablename__ = "pipeline_stage_log"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    case_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("case_run.id", ondelete="CASCADE"),
        nullable=False,
    )
    stage_name: Mapped[str] = mapped_column(String(50), nullable=False)
    input_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    output_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
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

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    case_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("case_run.id", ondelete="CASCADE"),
        nullable=False,
    )
    claim_text: Mapped[str] = mapped_column(Text, nullable=False)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False)
    claim_type: Mapped[str] = mapped_column(String(30), nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
    user_adjudication: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

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
    value_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
    expires_at: Mapped[datetime | None] = mapped_column(nullable=True)

    __table_args__ = (Index("idx_cache_expires", "expires_at"),)


# ---------------------------------------------------------------------------
# 7. evidence_binding
# ---------------------------------------------------------------------------


class EvidenceBinding(Base):
    """Explicit link between a claim and a legal_chunk."""

    __tablename__ = "evidence_binding"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    claim_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("claim.id", ondelete="CASCADE"),
        nullable=False,
    )
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
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

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    parameter_key: Mapped[str] = mapped_column(String(200), nullable=False)
    value_numeric: Mapped[float | None] = mapped_column(Float, nullable=True)
    value_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    value_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    unit: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # Owning module id (WP-94: stored `sgb2` rewritten to the module id). No
    # server default: the writer (module parameter loader) always names the
    # module — a default would hard-code one area of law into the schema.
    domain: Mapped[str] = mapped_column(String(50), nullable=False)
    regime: Mapped[str | None] = mapped_column(String(50), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    source_chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
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

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    messages: Mapped[list["ConversationMessage"]] = relationship(
        "ConversationMessage",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="ConversationMessage.created_at",
    )
    documents: Mapped[list["ConversationDocument"]] = relationship(
        "ConversationDocument",
        back_populates="conversation",
        cascade="all, delete-orphan",
    )


# ---------------------------------------------------------------------------
# 10. conversation_message
# ---------------------------------------------------------------------------

MESSAGE_ROLE_ALLOWED = ("user", "assistant", "system")


class ConversationMessage(Base):
    """A single message within a conversation."""

    __tablename__ = "conversation_message"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("conversation.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=func.now(),
    )

    # Relationships
    conversation: Mapped["Conversation"] = relationship(
        "Conversation",
        back_populates="messages",
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

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("conversation.id", ondelete="CASCADE"),
        nullable=False,
    )
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    normalized_text: Mapped[str] = mapped_column(Text, nullable=False)
    case_run_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("case_run.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=func.now(),
    )

    # Relationships
    conversation: Mapped["Conversation"] = relationship(
        "Conversation",
        back_populates="documents",
    )

    __table_args__ = (Index("idx_document_conversation", "conversation_id"),)


# ---------------------------------------------------------------------------
# 12. intake_session
# ---------------------------------------------------------------------------

INTAKE_STATUS_ALLOWED = ("active", "completed", "abandoned")


class IntakeSession(Base):
    """Persistent state for a multi-turn intake interview.

    Every case is preceded by a 2–8 turn interview where the LLM asks
    focused legal questions to disambiguate the case. This table records
    the conversation, the turn count, and the eventual ``intake_result``
    containing the chosen ``primary_area`` and ``secondary_areas``.

    The same row is referenced from ``case_run_area.intake_session_id``
    so the pipeline can later trace which intake produced a case.
    """

    __tablename__ = "intake_session"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    session_id: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default="active",
    )
    turn_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="0",
    )
    max_turns: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="8",
    )
    messages: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSON,
        nullable=True,
    )
    intake_result: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
    )
    primary_area: Mapped[str | None] = mapped_column(String(50), nullable=True)
    secondary_areas: Mapped[list[str] | None] = mapped_column(
        JSON,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    case_run_areas: Mapped[list["CaseRunArea"]] = relationship(
        "CaseRunArea",
        back_populates="intake_session",
    )

    __table_args__ = (
        CheckConstraint(
            f"status IN ({_sql_in(INTAKE_STATUS_ALLOWED)})",
            name="ck_intake_session_status",
        ),
        CheckConstraint(
            "turn_count >= 0 AND turn_count <= max_turns",
            name="ck_intake_session_turn_count",
        ),
        Index("idx_intake_session_id", "session_id"),
    )


# ---------------------------------------------------------------------------
# 13. case_run_area
# ---------------------------------------------------------------------------


class CaseRunArea(Base):
    """Many-to-many link between a ``case_run`` and a ``legal_area``.

    A single case can span one or more legal areas (e.g. an Erbrecht +
    Familienrecht succession dispute). The ``is_primary`` flag marks
    the area the LLM selected as the dominant one.
    """

    __tablename__ = "case_run_area"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    case_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("case_run.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Area key as requested/selected (module id, legacy alias or core
    # procedural key). No DB CHECK since WP-94: the key set is module data,
    # validated by the writer against the area tables (D-057).
    legal_area: Mapped[str] = mapped_column(String(50), nullable=False)
    # Owning module and the version the case ran with. NULL module_id only
    # for keys served by the core procedural library; NULL module_version
    # for rows written before WP-94 (version was not recorded).
    module_id: Mapped[str | None] = mapped_column(
        String(50),
        ForeignKey("legal_module.id", name="fk_case_run_area_module_id", ondelete="RESTRICT"),
        nullable=True,
    )
    module_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    is_primary: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=sa.text("0"),
    )
    intake_session_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("intake_session.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=func.now(),
    )

    # Relationships
    intake_session: Mapped["IntakeSession | None"] = relationship(
        "IntakeSession",
        back_populates="case_run_areas",
    )

    __table_args__ = (
        UniqueConstraint(
            "case_run_id",
            "legal_area",
            name="uq_case_run_area_case_area",
        ),
        Index("idx_case_run_area_case", "case_run_id"),
        Index("idx_case_run_area_area", "legal_area"),
        Index("idx_case_run_area_module", "module_id"),
    )


# ---------------------------------------------------------------------------
# 14. legal_module (WP-94)
# ---------------------------------------------------------------------------

#: Mirrors the manifest schema's ``tier`` enum (app/modules/manifest.schema.json).
MODULE_TIER_ALLOWED = ("planned", "experimental", "verified", "community")


class LegalModule(Base):
    """One row per installed module, synced by the registry at startup.

    Rows are never deleted by the sync: ``case_run_area.module_id`` keeps
    referencing a module that was uninstalled later (``enabled`` turns
    false). ``installed_at`` is the time the current manifest (version +
    ``manifest_sha256``) was first seen. ``manifest_sha256`` is NULL only
    for rows seeded by migration 013 that no sync has touched yet.
    """

    __tablename__ = "legal_module"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    tier: Mapped[str] = mapped_column(String(20), nullable=False)
    manifest_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    installed_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa.text("false"))

    __table_args__ = (
        CheckConstraint(
            f"tier IN ({_sql_in(MODULE_TIER_ALLOWED)})",
            name="ck_legal_module_tier",
        ),
    )


# ---------------------------------------------------------------------------
# 15. case_dossier (WP-100)
# ---------------------------------------------------------------------------


class CaseDossier(Base):
    """One built appointment dossier per row (roadmap P10, D-064).

    A separate table rather than ``case_run.dossier_json``: every build is
    kept as a numbered ``revision`` (what the person printed stays
    reproducible), and ``/cases`` list queries never load dossier payloads.
    ``dossier_json`` validates against ``schema_version``
    (``citizen-dossier-vMAJOR.MINOR``); ``content_sha256`` is the SHA-256 of
    its canonical JSON (sorted keys, UTF-8). The PDF is rendered from the
    stored JSON on demand and not stored. Rows go with their case
    (``ON DELETE CASCADE``).
    """

    __tablename__ = "case_dossier"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    case_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("case_run.id", name="fk_case_dossier_case_run_id", ondelete="CASCADE"),
        nullable=False,
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    schema_version: Mapped[str] = mapped_column(String(40), nullable=False)
    dossier_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("case_run_id", "revision", name="uq_case_dossier_case_revision"),
        CheckConstraint("revision >= 1", name="ck_case_dossier_revision_positive"),
        Index("idx_case_dossier_case", "case_run_id"),
    )


# ---------------------------------------------------------------------------
# 16. module_update (WP-111) and corpus_source_watch (WP-113)
# ---------------------------------------------------------------------------


class ModuleUpdate(Base):
    """One applied signed update feed (roadmap P11, migration 015).

    ``(module_id, serial)`` is unique and the apply path only accepts a
    serial above the module's highest applied one (anti-rollback/replay).
    ``parameters`` lists the ``legal_parameter`` identities the feed wrote
    (``key``, ``valid_from``, ``action``); the file seeder leaves them alone.
    No FK to ``legal_module``: the CLI may apply before the first sync.
    """

    __tablename__ = "module_update"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    module_id: Mapped[str] = mapped_column(String(50), nullable=False)
    serial: Mapped[int] = mapped_column(Integer, nullable=False)
    feed_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    key_id: Mapped[str] = mapped_column(String(32), nullable=False)
    issued_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    applied_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    module_version: Mapped[str] = mapped_column(String(50), nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    parameters: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    corpus_notices: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)

    __table_args__ = (
        UniqueConstraint("module_id", "serial", name="uq_module_update_module_serial"),
        CheckConstraint("serial >= 1", name="ck_module_update_serial_positive"),
        Index("idx_module_update_module", "module_id"),
    )


class CorpusSourceWatch(Base):
    """Last observed upstream state of one corpus source (WP-113).

    Written by the daily change detection (``python -m scripts.corpus_watch``):
    presence in ``gii-toc.xml`` and the HTTP validators of the source's XML
    archive. ``changed_at`` is the last time a validator differed.
    """

    __tablename__ = "corpus_source_watch"

    source_type: Mapped[str] = mapped_column(String(50), primary_key=True)
    toc_link: Mapped[str | None] = mapped_column(Text, nullable=True)
    etag: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_modified: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_length: Mapped[int | None] = mapped_column(sa.BigInteger, nullable=True)
    in_toc: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa.text("true"))
    checked_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    changed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
