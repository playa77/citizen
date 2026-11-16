"""WP-94: legal_module table, case_run_area module binding, sgb2 → sozialrecht.

Data-model half of the core/module split (ARCHITECTURE.md § 4, D-057):

* ``legal_module`` — one row per installed module, synced by the registry at
  startup (``app/modules/sync.py``). This migration seeds the eight module
  ids that the pre-WP-94 area keys map to, so the foreign key below can be
  created on a database that already holds ``case_run_area`` rows. Seed rows
  carry ``manifest_sha256 = NULL`` ("not synced yet") and ``enabled = false``;
  the first startup sync fills in the live manifest data.
* ``case_run_area`` — the CHECK ``ck_case_run_area_legal_area`` (closed list
  of ten area keys) is dropped; ``legal_area`` keeps the stored area key
  unchanged (API output of ``/cases`` is unchanged, D-039). New columns
  ``module_id`` (FK → ``legal_module.id``; NULL only for keys served by the
  core procedural library) and ``module_version`` (NULL for rows written
  before this migration — the version was never recorded). Existing rows are
  backfilled from the frozen v2.0.0 key → module map below.
* ``legal_parameter.domain`` — ``sgb2`` rewritten to the module id
  ``sozialrecht``; the column default (``'sgb2'``) is dropped: the module
  parameter loader always names the module, and a default would hard-code
  one area of law into the schema.

Every statement is idempotent (D-005/D-027 practice): replaying the upgrade
on a database that already has the changes is a no-op.

The frozen maps are deliberately literal copies, not imports of app code: a
migration must keep producing the same schema/data when the code moves on.

Revision ID: 013_legal_module
Revises: 012_pg_collapse_sqlite_branch
Create Date: 2026-11-16 00:00:00.000000
"""

# Semantic Version: 1.0.0

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "013_legal_module"
down_revision: str | None = "012_pg_collapse_sqlite_branch"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Module rows referenced by v2.0.0 area keys: (id, version, tier) as shipped
# by the in-tree manifests at WP-93. The startup sync overwrites version/tier.
_SEED_MODULES = (
    ("sozialrecht", "1.0.0", "verified"),
    ("erbrecht", "0.1.0", "experimental"),
    ("familienrecht", "0.1.0", "experimental"),
    ("mietrecht", "0.1.0", "experimental"),
    ("arbeitsrecht", "0.1.0", "experimental"),
    ("vertragsrecht", "0.1.0", "experimental"),
    ("strafrecht", "0.1.0", "experimental"),
    ("andere", "0.1.0", "experimental"),
)

# v2.0.0 area keys that are not module ids (D-038). A key mapped to None is
# served by the core procedural library and has no module.
_KEY_TO_MODULE_EXCEPTIONS: dict[str, str | None] = {
    "schenkungsrecht": "erbrecht",
    "verwaltungsrecht": None,
}

# The closed v2.0.0 key list, needed only to restore the CHECK on downgrade.
_V2_AREA_KEYS = (
    "sozialrecht",
    "erbrecht",
    "schenkungsrecht",
    "familienrecht",
    "mietrecht",
    "arbeitsrecht",
    "vertragsrecht",
    "verwaltungsrecht",
    "strafrecht",
    "andere",
)


def _sql_list(values: Sequence[str]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def upgrade() -> None:
    # 1. legal_module
    op.execute(
        "CREATE TABLE IF NOT EXISTS legal_module ("
        " id VARCHAR(50) NOT NULL,"
        " version VARCHAR(50) NOT NULL,"
        " tier VARCHAR(20) NOT NULL,"
        " manifest_sha256 VARCHAR(64),"
        " installed_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),"
        " enabled BOOLEAN NOT NULL DEFAULT false,"
        " CONSTRAINT legal_module_pkey PRIMARY KEY (id),"
        " CONSTRAINT ck_legal_module_tier"
        " CHECK (tier IN ('planned', 'experimental', 'verified', 'community'))"
        ")"
    )
    seed_values = ", ".join(f"('{mid}', '{ver}', '{tier}')" for mid, ver, tier in _SEED_MODULES)
    op.execute(
        f"INSERT INTO legal_module (id, version, tier) VALUES {seed_values} "
        "ON CONFLICT (id) DO NOTHING"
    )

    # 2. case_run_area: drop the closed-list CHECK, add the module binding.
    op.execute("ALTER TABLE case_run_area DROP CONSTRAINT IF EXISTS ck_case_run_area_legal_area")
    op.execute("ALTER TABLE case_run_area ADD COLUMN IF NOT EXISTS module_id VARCHAR(50)")
    op.execute("ALTER TABLE case_run_area ADD COLUMN IF NOT EXISTS module_version VARCHAR(50)")

    exceptions = " ".join(
        f"WHEN '{key}' THEN {('NULL' if mid is None else repr(mid))}"
        for key, mid in _KEY_TO_MODULE_EXCEPTIONS.items()
    )
    # Only rows that have no binding yet; procedural keys stay NULL anyway.
    op.execute(
        "UPDATE case_run_area SET module_id = "
        f"CASE legal_area {exceptions} ELSE legal_area END "
        "WHERE module_id IS NULL"
    )

    op.execute(
        "DO $$ BEGIN "
        "IF NOT EXISTS (SELECT 1 FROM pg_constraint "
        "WHERE conname = 'fk_case_run_area_module_id') THEN "
        "ALTER TABLE case_run_area ADD CONSTRAINT fk_case_run_area_module_id "
        "FOREIGN KEY (module_id) REFERENCES legal_module (id) ON DELETE RESTRICT; "
        "END IF; END $$"
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_case_run_area_module ON case_run_area (module_id)")

    # 3. legal_parameter.domain: parameter namespace = module id.
    op.execute("UPDATE legal_parameter SET domain = 'sozialrecht' WHERE domain = 'sgb2'")
    op.execute("ALTER TABLE legal_parameter ALTER COLUMN domain DROP DEFAULT")


def downgrade() -> None:
    # Reverse of upgrade. Restoring the CHECK fails loudly if rows with area
    # keys outside the v2.0.0 list were written after the upgrade — such
    # rows must be resolved by hand; silently deleting audit rows is not an
    # option.
    op.execute("ALTER TABLE legal_parameter ALTER COLUMN domain SET DEFAULT 'sgb2'")
    op.execute("UPDATE legal_parameter SET domain = 'sgb2' WHERE domain = 'sozialrecht'")

    op.execute("DROP INDEX IF EXISTS idx_case_run_area_module")
    op.execute("ALTER TABLE case_run_area DROP CONSTRAINT IF EXISTS fk_case_run_area_module_id")
    op.execute("ALTER TABLE case_run_area DROP COLUMN IF EXISTS module_version")
    op.execute("ALTER TABLE case_run_area DROP COLUMN IF EXISTS module_id")
    op.execute("ALTER TABLE case_run_area DROP CONSTRAINT IF EXISTS ck_case_run_area_legal_area")
    op.execute(
        "ALTER TABLE case_run_area ADD CONSTRAINT ck_case_run_area_legal_area "
        f"CHECK (legal_area IN ({_sql_list(_V2_AREA_KEYS)}))"
    )

    op.execute("DROP TABLE IF EXISTS legal_module")
