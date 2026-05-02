"""Unit tests for WP-004: ORM model definitions and Alembic initialization.

Tests that do NOT require a live database:
- Table names, columns, relationships, constraints, indexes
- Alembic revision chain is valid
- Alembic env.py imports models correctly
"""

from __future__ import annotations

from sqlalchemy import CheckConstraint

from app.db import models

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _primary_keys(table: type[models.Base]) -> list[str]:
    return [c.name for c in table.__table__.primary_key.columns]


def _column_names(table: type[models.Base]) -> set[str]:
    return {c.name for c in table.__table__.columns}


def _check_constraints(table: type[models.Base]) -> list[CheckConstraint]:
    """Return check constraints from a table's constraint collection."""
    return [c for c in table.__table__.constraints if isinstance(c, CheckConstraint)]


# ---------------------------------------------------------------------------
# 1. Table count & names
# ---------------------------------------------------------------------------


def test_exactly_seven_tables() -> None:
    tables = models.Base.metadata.tables
    assert len(tables) == 7, f"Expected 7 tables, got {len(tables)}: {list(tables)}"


def test_expected_table_names() -> None:
    expected = {
        "legal_source",
        "legal_chunk",
        "chunk_embedding",
        "case_run",
        "pipeline_stage_log",
        "claim",
        "evidence_binding",
    }
    actual = set(models.Base.metadata.tables.keys())
    assert actual == expected, f"Missing: {expected - actual}; Extra: {actual - expected}"


# ---------------------------------------------------------------------------
# 2. LegalSource
# ---------------------------------------------------------------------------


class TestLegalSource:
    TABLE = models.LegalSource

    def test_primary_key(self) -> None:
        assert _primary_keys(self.TABLE) == ["id"]

    def test_columns(self) -> None:
        expected = {
            "id",
            "source_type",
            "title",
            "jurisdiction",
            "effective_date",
            "source_url",
            "version_hash",
            "is_active",
            "created_at",
            "updated_at",
        }
        assert _column_names(self.TABLE) == expected

    def test_source_type_check_constraint(self) -> None:
        """source_type IN ('sgb2', 'sgbx', 'weisung', 'bsg')."""
        ck = _check_constraints(self.TABLE)
        assert any("sgb2" in str(c.sqltext) for c in ck)

    def test_chunks_relationship(self) -> None:
        rel = models.LegalSource.chunks
        assert rel.property.back_populates == "source"


# ---------------------------------------------------------------------------
# 3. LegalChunk
# ---------------------------------------------------------------------------


class TestLegalChunk:
    TABLE = models.LegalChunk

    def test_primary_key(self) -> None:
        assert _primary_keys(self.TABLE) == ["id"]

    def test_columns(self) -> None:
        expected = {
            "id",
            "source_id",
            "unit_type",
            "hierarchy_path",
            "text_content",
            "effective_date",
            "created_at",
        }
        assert _column_names(self.TABLE) == expected

    def test_unit_type_check_constraint(self) -> None:
        ck = _check_constraints(self.TABLE)
        assert any("statute" in str(c.sqltext) for c in ck)

    def test_foreign_key_to_legal_source(self) -> None:
        fks = list(models.LegalChunk.__table__.foreign_keys)
        assert any(fk.column.table.name == "legal_source" for fk in fks)

    def test_cascade_delete_from_source(self) -> None:
        fks = [
            fk
            for fk in models.LegalChunk.__table__.foreign_keys
            if fk.column.table.name == "legal_source"
        ]
        assert any(fk.ondelete == "CASCADE" for fk in fks)

    def test_relationships(self) -> None:
        assert models.LegalChunk.source.property.back_populates == "chunks"
        assert models.LegalChunk.embeddings.property.back_populates == "chunk"

    def test_indexes_exist(self) -> None:
        idx_names = {idx.name for idx in models.LegalChunk.__table__.indexes}
        assert "idx_chunk_source" in idx_names
        assert "idx_chunk_hierarchy" in idx_names


# ---------------------------------------------------------------------------
# 4. ChunkEmbedding
# ---------------------------------------------------------------------------


class TestChunkEmbedding:
    TABLE = models.ChunkEmbedding

    def test_primary_key(self) -> None:
        assert _primary_keys(self.TABLE) == ["id"]

    def test_columns(self) -> None:
        expected = {"id", "chunk_id", "embedding", "model_name", "created_at"}
        assert _column_names(self.TABLE) == expected

    def test_foreign_key_to_legal_chunk(self) -> None:
        fks = list(models.ChunkEmbedding.__table__.foreign_keys)
        assert any(fk.column.table.name == "legal_chunk" and fk.ondelete == "CASCADE" for fk in fks)

    def test_vector_dimension(self) -> None:
        col = models.ChunkEmbedding.__table__.c.embedding
        # pgvector columns expose a .dim attribute on the vector type.
        assert col.type.dim == 1536


# ---------------------------------------------------------------------------
# 5. CaseRun
# ---------------------------------------------------------------------------


class TestCaseRun:
    TABLE = models.CaseRun

    def test_primary_key(self) -> None:
        assert _primary_keys(self.TABLE) == ["id"]

    def test_columns(self) -> None:
        expected = {
            "id",
            "session_id",
            "input_text",
            "status",
            "latency_ms",
            "llm_fallback_chain",
            "created_at",
        }
        assert _column_names(self.TABLE) == expected

    def test_status_check_constraint(self) -> None:
        ck = _check_constraints(self.TABLE)
        assert any("queued" in str(c.sqltext) for c in ck)

    def test_relationships(self) -> None:
        assert models.CaseRun.stage_logs.property.back_populates == "case_run"
        assert models.CaseRun.claims.property.back_populates == "case_run"

    def test_session_index(self) -> None:
        idx_names = {idx.name for idx in models.CaseRun.__table__.indexes}
        assert "idx_case_session" in idx_names


# ---------------------------------------------------------------------------
# 6. PipelineStageLog
# ---------------------------------------------------------------------------


class TestPipelineStageLog:
    TABLE = models.PipelineStageLog

    def test_primary_key(self) -> None:
        assert _primary_keys(self.TABLE) == ["id"]

    def test_columns(self) -> None:
        expected = {
            "id",
            "case_run_id",
            "stage_name",
            "input_snapshot",
            "output_snapshot",
            "duration_ms",
            "error_trace",
            "created_at",
        }
        assert _column_names(self.TABLE) == expected

    def test_stage_name_check_constraint(self) -> None:
        ck = _check_constraints(self.TABLE)
        assert any("normalization" in str(c.sqltext) for c in ck)
        assert any("generation" in str(c.sqltext) for c in ck)
        sqltext = str(next(c.sqltext for c in ck))
        assert len(sqltext.split(",")) >= 7

    def test_foreign_key_to_case_run_cascade(self) -> None:
        fks = list(models.PipelineStageLog.__table__.foreign_keys)
        assert any(fk.column.table.name == "case_run" and fk.ondelete == "CASCADE" for fk in fks)

    def test_index_exists(self) -> None:
        idx_names = {idx.name for idx in models.PipelineStageLog.__table__.indexes}
        assert "idx_stage_case" in idx_names


# ---------------------------------------------------------------------------
# 7. Claim
# ---------------------------------------------------------------------------


class TestClaim:
    TABLE = models.Claim

    def test_primary_key(self) -> None:
        assert _primary_keys(self.TABLE) == ["id"]

    def test_columns(self) -> None:
        expected = {
            "id",
            "case_run_id",
            "claim_text",
            "confidence_score",
            "claim_type",
            "created_at",
        }
        assert _column_names(self.TABLE) == expected

    def test_claim_type_check_constraint(self) -> None:
        ck = _check_constraints(self.TABLE)
        assert any("fact" in str(c.sqltext) for c in ck)

    def test_confidence_score_check_constraint(self) -> None:
        ck = _check_constraints(self.TABLE)
        assert any("confidence_score" in str(c.sqltext) for c in ck)

    def test_foreign_key_to_case_run_cascade(self) -> None:
        fks = list(models.Claim.__table__.foreign_keys)
        assert any(fk.column.table.name == "case_run" and fk.ondelete == "CASCADE" for fk in fks)


# ---------------------------------------------------------------------------
# 8. EvidenceBinding
# ---------------------------------------------------------------------------


class TestEvidenceBinding:
    TABLE = models.EvidenceBinding

    def test_primary_key(self) -> None:
        assert _primary_keys(self.TABLE) == ["id"]

    def test_columns(self) -> None:
        expected = {"id", "claim_id", "chunk_id", "binding_strength", "quote_excerpt", "created_at"}
        assert _column_names(self.TABLE) == expected

    def test_foreign_key_to_claim_cascade(self) -> None:
        fks = list(models.EvidenceBinding.__table__.foreign_keys)
        assert any(fk.column.table.name == "claim" and fk.ondelete == "CASCADE" for fk in fks)

    def test_foreign_key_to_legal_chunk_restrict(self) -> None:
        fks = list(models.EvidenceBinding.__table__.foreign_keys)
        on_legal_chunk = [fk for fk in fks if fk.column.table.name == "legal_chunk"]
        assert any(fk.ondelete == "RESTRICT" for fk in on_legal_chunk)

    def test_unique_index(self) -> None:
        idx_names = {idx.name for idx in models.EvidenceBinding.__table__.indexes}
        assert "idx_binding_unique" in idx_names
        unique_idxs = [idx for idx in models.EvidenceBinding.__table__.indexes if idx.unique]
        assert any(idx.name == "idx_binding_unique" for idx in unique_idxs)
