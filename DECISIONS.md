# Citizen — Decision Ledger

**Append-only. Never delete or reorder entries.**

Format: `### D-XXX REVERSIBILITY — Date`
Each entry lists: decision, rejected alternative, rationale.

---

### D-001 R1 — 2026-07-13
**Decision:** Add `asyncpg>=0.29.0` to `pyproject.toml` dependencies.
**Rejected:** None — required dependency for PostgreSQL async driver, not previously declared.
**Rationale:** Build failed with `ModuleNotFoundError: asyncpg`. It's a transitive
dependency of SQLAlchemy's async PostgreSQL support but must be declared explicitly.

### D-002 R1 — 2026-07-13
**Decision:** Add `pgvector>=0.3.0` to `pyproject.toml` dependencies.
**Rejected:** None — required for vector column types in SQLAlchemy models, not previously declared.
**Rationale:** Alembic migrations reference pgvector types; the Python package must be installed.

### D-003 R1 — 2026-07-13
**Decision:** Map container port 8000 to host port 8001 via docker-compose.override.yml.
**Rejected:** Debugging the "address already in use" error on 8000 (no listener found).
**Rationale:** Docker repeatedly reported port 8000 in use despite nothing binding.
Port 8001 has no conflict and the nginx proxy_pass is updated to match. Cost of
investigating the phantom port conflict > cost of changing the port.

### D-004 R2 — 2026-07-13
**Decision:** Target `006_add_intake_and_legal_areas` (not `head`) for PostgreSQL
auto-migration at startup. SQLite uses `heads`.
**Rejected:** Refactoring the migration DAG to merge branches (high risk, changes
existing migration files that may have been applied in other environments).
**Rationale:** The migration history has two independent branches from `<base>`:
PostgreSQL (001→006) and SQLite baseline (007→010). `alembic upgrade head` (singular)
fails with "Multiple head revisions are present." Branch-aware targeting handles both
dialects without modifying existing migrations.

### D-005 R2 — 2026-07-13
**Decision:** Manually applied DDL from migrations 008–010 (CHECK constraint update,
`regime`/`notes` columns on `legal_parameter`, `pii_mapping` on `case_run`) to
the production PostgreSQL database.
**Rejected:** Creating a merge migration that depends on both 006 and 007, or
changing the down_revision of 008 to 006 (would break SQLite upgrade path).
**Rationale:** Migrations 008–010 are on the SQLite-only branch but their schema
changes are needed for PostgreSQL. Creating a proper bridge migration (011) is
pending for future fresh deploys; for the current production DB, manual DDL is
fastest and safe. A future migration 011 should consolidate these changes.

### D-006 R2 — 2026-07-13
**Decision:** Run alembic migrations at startup via `asyncio.create_subprocess_exec`
instead of `asyncio.to_thread(alembic_command.upgrade, ...)`.
**Rejected:** Using `asyncio.to_thread` with a timeout (timeout can't interrupt a
thread blocked inside greenlet-based asyncpg).
**Rationale:** `alembic_command.upgrade` called via `asyncio.to_thread` from inside
uvicorn's lifespan handler deadlocks. The alembic env.py calls `asyncio.run()` to
create a new event loop inside the thread, but asyncpg+greenlet internals conflict
with the uvicorn-managed parent event loop across thread boundaries. A subprocess
provides a fully independent Python interpreter, avoiding the greenlet conflict
entirely. Migration still completes in ~1 second.

---

## Open / Pending

### D-007 PENDING — 2026-07-13
**Status:** Create migration 011 that depends on 006 and applies the cumulative
schema changes from 008+009+010 (CHECK constraint, regime/notes, pii_mapping).
This provides a clean PostgreSQL upgrade path for future fresh deployments.
