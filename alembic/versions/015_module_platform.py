"""P11: module_update (signed update channel ledger) and corpus_source_watch.

``module_update`` (WP-111): one row per applied signed update feed. The
unique ``(module_id, serial)`` pair plus the "serial must grow" rule in the
apply path is the anti-rollback/anti-replay ledger; ``parameters`` records
which ``legal_parameter`` identities the feed wrote, so a later file seed
does not silently revert a published correction; ``corpus_notices`` keeps
the feed's corpus change notices for ``GET /modules/{id}``. No FK to
``legal_module``: an update may be verified and applied by the CLI before
the service ever synced the module row; ``module_id`` is checked against the
installed registry instead.

``corpus_source_watch`` (WP-113): last observed state per corpus source of
the daily gesetze-im-internet change detection (``gii-toc.xml`` presence,
``ETag``/``Last-Modified``/length of the source's XML archive).

Idempotent (D-005/D-027 practice): replaying the upgrade is a no-op.

Revision ID: 015_module_platform
Revises: 014_case_dossier
Create Date: 2026-11-17 00:00:00.000000
"""

# Semantic Version: 1.0.0

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "015_module_platform"
down_revision: str | None = "014_case_dossier"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "CREATE TABLE IF NOT EXISTS module_update ("
        " id UUID NOT NULL,"
        " module_id VARCHAR(50) NOT NULL,"
        " serial INTEGER NOT NULL,"
        " feed_sha256 VARCHAR(64) NOT NULL,"
        " key_id VARCHAR(32) NOT NULL,"
        " issued_at TIMESTAMP WITH TIME ZONE NOT NULL,"
        " applied_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),"
        " module_version VARCHAR(50) NOT NULL,"
        " source TEXT NOT NULL,"
        " parameters JSON NOT NULL,"
        " corpus_notices JSON NOT NULL,"
        " CONSTRAINT module_update_pkey PRIMARY KEY (id),"
        " CONSTRAINT uq_module_update_module_serial UNIQUE (module_id, serial),"
        " CONSTRAINT ck_module_update_serial_positive CHECK (serial >= 1)"
        ")"
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_module_update_module ON module_update (module_id)")
    op.execute(
        "CREATE TABLE IF NOT EXISTS corpus_source_watch ("
        " source_type VARCHAR(50) NOT NULL,"
        " toc_link TEXT,"
        " etag TEXT,"
        " last_modified TEXT,"
        " content_length BIGINT,"
        " in_toc BOOLEAN NOT NULL DEFAULT true,"
        " checked_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),"
        " changed_at TIMESTAMP WITH TIME ZONE,"
        " CONSTRAINT corpus_source_watch_pkey PRIMARY KEY (source_type)"
        ")"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS corpus_source_watch")
    op.execute("DROP INDEX IF EXISTS idx_module_update_module")
    op.execute("DROP TABLE IF EXISTS module_update")
