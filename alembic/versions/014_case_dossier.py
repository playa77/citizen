"""WP-100: case_dossier table (appointment dossier storage, D-064).

One row per built dossier: ``revision`` counts builds per case from 1,
``dossier_json`` holds the document (``schema_version`` names its JSON
Schema, ``citizen-dossier-v1.0``), ``content_sha256`` pins its canonical
JSON. The table instead of a ``case_run.dossier_json`` column keeps every
revision (a printed dossier stays reproducible) and keeps payloads out of
the ``case_run`` rows that list queries load.

Idempotent (D-005/D-027 practice): replaying the upgrade is a no-op.

Revision ID: 014_case_dossier
Revises: 013_legal_module
Create Date: 2026-11-16 00:00:00.000000
"""

# Semantic Version: 1.0.0

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "014_case_dossier"
down_revision: str | None = "013_legal_module"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "CREATE TABLE IF NOT EXISTS case_dossier ("
        " id UUID NOT NULL,"
        " case_run_id UUID NOT NULL,"
        " revision INTEGER NOT NULL,"
        " schema_version VARCHAR(40) NOT NULL,"
        " dossier_json JSON NOT NULL,"
        " content_sha256 VARCHAR(64) NOT NULL,"
        " created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),"
        " CONSTRAINT case_dossier_pkey PRIMARY KEY (id),"
        " CONSTRAINT fk_case_dossier_case_run_id FOREIGN KEY (case_run_id)"
        " REFERENCES case_run (id) ON DELETE CASCADE,"
        " CONSTRAINT uq_case_dossier_case_revision UNIQUE (case_run_id, revision),"
        " CONSTRAINT ck_case_dossier_revision_positive CHECK (revision >= 1)"
        ")"
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_case_dossier_case ON case_dossier (case_run_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_case_dossier_case")
    op.execute("DROP TABLE IF EXISTS case_dossier")
