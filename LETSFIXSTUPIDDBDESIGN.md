# LET'S FIX THE STUPID DB DESIGN

**Status:** Outline only — not in scope for the current session.
**Created:** 2026-07-19
**Trigger:** The Prüfstand pgvector aliasing bug (D-016) slipped through because
unit tests run on SQLite while production runs on PostgreSQL. The two backends
diverged on column aliasing, and no test exercised the pgvector code path.
This is a structural blind spot, not a one-off mistake.

---

## The Problem

The Citizen codebase runs two different databases depending on context:

| Context | Database | Vector backend | Code path |
|---|---|---|---|
| Server / production / Docker | PostgreSQL 16 + pgvector | `<=>` operator | `_cosine_distance_pgvector()` |
| Electron desktop app | SQLite + sqlite-vec | `vec_distance_cosine()` | `_cosine_distance_sqlite()` |
| **Unit tests** | **SQLite in-memory** | **sqlite-vec** | **`_cosine_distance_sqlite()`** |

The `IS_SQLITE` flag in `app/db/session.py` (set at import time from
`DATABASE_URL`) selects the code path. This means:

1. **Tests never exercise the production code path.** Any bug specific to the
   pgvector backend (SQL syntax, column aliasing, type casts, operator behavior)
   is invisible to the test suite. D--014 (pgvector upsert cast), D-016
   (pgvector column aliasing), and the original `<=>` operator integration
   were all untested.

2. **Two code paths must be kept in sync by hand.** Every vector query, every
   raw SQL fragment, every column aliasing rule must be duplicated across
   `_cosine_distance_sqlite` and `_cosine_distance_pgvector`. The SQLite path
   is the "reference" only because tests run on it — not because it is more
   correct.

3. **Two alembic migration branches.** PostgreSQL (001→006, plus 011_pg) and
   SQLite (007→010, plus 011_sqlite) are independent DAGs. `alembic upgrade
   head` fails with "Multiple head revisions." D-004 worked around this with
   dialect-specific targets; D-007 (pending) is supposed to bridge them. This
   complexity exists solely to support the SQLite branch.

4. **Conditional ORM types.** `ChunkEmbedding.embedding` is mapped as
   `LargeBinary` (BYTEA) for dialect portability, but the actual PostgreSQL
   column is pgvector `Vector`. This forced the raw-SQL-with-`::vector`-cast
   workaround in both `vector_backend.py` and `corpus.py` (D-014). A
   single-backend design would use pgvector's `Vector` type directly in the
   ORM.

5. **The desktop app is the only reason SQLite exists.** The server, CI, and
   tests could all use PostgreSQL. SQLite exists because the Electron desktop
   wrapper ships an embedded DB to avoid requiring the user to install
   PostgreSQL. This is a legitimate desktop-app constraint — but it should not
   dictate the test or server database.

---

## The Goal

**One database backend for server, CI, and tests: PostgreSQL + pgvector.**
Eliminate the `IS_SQLITE` code path from all non-desktop code. Tests must
exercise the exact same SQL that production runs.

The Electron desktop app may retain SQLite as a separate, isolated deployment
target — but it must not share code paths with the server, and its tests must
not be the server's tests.

---

## Scope of Changes (Outline)

### 1. Test infrastructure: PostgreSQL test container

- Replace `sqlite+aiosqlite:///:memory:` in `tests/conftest.py` with a
  PostgreSQL+pgvector instance. Options:
  - **testcontainers-python** (`PostgresqlContainer` with `pgvector/pgvector:pg16`
    image) — spins up a fresh container per test session, tears down after.
    Cleanest isolation; matches production image exactly.
  - **Local PG instance** — faster, but requires developers to have PostgreSQL
    + pgvector installed locally. Fragile across machines.
  - **Recommendation:** testcontainers. It mirrors the production Docker image
    (`pgvector/pgvector:pg16`) and requires no local PG install.
- Add `testcontainers[postgres]` to dev dependencies in `pyproject.toml`.
- Session-scoped fixture: start container, run alembic migrations (PG branch
  only), yield engine, tear down. Per-test transaction rollback for isolation.
- Remove the dummy `DATABASE_URL` override in `conftest.py` (or make it the
  fallback only when testcontainers is unavailable).

### 2. Eliminate `IS_SQLITE` from server code

- `app/db/session.py`: remove `IS_SQLITE` flag and all conditional engine
  creation logic. Server always uses `asyncpg`.
- `app/db/vector_backend.py`: remove `_cosine_distance_sqlite()` entirely.
  Remove the `IS_SQLITE` branch in `cosine_distance()`. The function always
  calls `_cosine_distance_pgvector()`. Remove `load_sqlite_vec_extension()`.
- `app/db/models.py`: change `ChunkEmbedding.embedding` from `LargeBinary` to
  pgvector's `Vector(dim)` type. This removes the raw-SQL `::vector` cast
  workaround in `corpus.py` (`_upsert_embedding`) and `vector_backend.py`.
- `app/services/corpus.py`: simplify `_upsert_embedding()` to use ORM insert
  with the typed Vector column. Remove the raw SQL path (D-014 workaround).
- `app/main.py`: remove the SQLite-vs-PG migration target branching. Always
  target the PG migration head. Remove `asyncio.create_subprocess_exec`
  workaround for alembic (D-006) if it's no longer needed — verify first.
- `app/core/config.py`: remove SQLite-specific settings (`DB_POOL_SIZE` stays;
  remove any SQLite-only knobs).

### 3. Collapse the alembic migration DAG

- Delete the SQLite migration branch (007, 008, 009, 010, 011_sqlite).
- Keep the PG branch (001→006, 011_pg) as the single linear history.
- D-007 (the bridge migration) becomes unnecessary — there's nothing to bridge.
- Update `app/main.py` lifespan to call `alembic upgrade head` (singular) —
  no more dialect-specific targeting.
- Update `AGENTS.md` "Alembic Migration Gotcha" section — the gotcha no longer
  exists.

### 4. Electron desktop app: isolate SQLite

- The desktop app keeps SQLite (legitimate constraint: can't ship PostgreSQL
  inside Electron).
- **But:** the desktop app must not import `app/db/vector_backend.py` or
  `app/db/session.py` directly if those modules are PG-only. Options:
  - **Option A:** Keep a separate `app/db/vector_backend_sqlite.py` for the
    desktop app, imported only by the desktop entrypoint. The server never
    imports it. Clear separation, no shared conditional code.
  - **Option B:** The desktop app runs its own embedded PostgreSQL (e.g. via
    `embedded-postgres` or a bundled PG binary). Heavier, but eliminates
    SQLite entirely. Probably overkill for a desktop wrapper.
  - **Recommendation:** Option A. Desktop SQLite is a separate, isolated
    deployment target with its own vector backend module. Server code is
    PG-only.
- The desktop app's SQLite migrations (007-010) move to an
  `electron/db/migrations/` directory, separate from the server's alembic
  tree.

### 5. CI pipeline

- CI runs the full test suite against PostgreSQL (via testcontainers or a
  service container in the CI config).
- Remove any SQLite-specific CI steps.
- Add a lint check that fails if `IS_SQLITE` or `sqlite_vec` is referenced
  outside `electron/` — prevents the conditional code from creeping back into
  server code.

### 6. Documentation

- Update `AGENTS.md`: remove the "Dual Database" section. Replace with
  "Database: PostgreSQL 16 + pgvector (server, CI, tests). SQLite for
  Electron desktop only (isolated)."
- Update `DEPLOYMENT.md`: remove SQLite references in the migration section.
- Update `DECISIONS.md`: log the overhaul as R3 (one-way door: removes a
  supported backend, changes migration history, affects desktop app
  architecture).

---

## Risks

- **R3 (one-way door):** Removing the SQLite migration branch is irreversible
  without restoring deleted migration files. Must be logged as an R3 decision
  and approved by the user with a named invariant.
- **Desktop app breakage:** The Electron app currently shares server code
  paths. Isolating SQLite requires care to avoid breaking the desktop build.
- **testcontainers overhead:** Adds ~5-10s per test session for container
  startup. Acceptable for CI; may annoy local dev. Mitigate with a
  session-scoped fixture (one container per session, not per test).
- **Migration history rewrite:** Deleting SQLite migrations means anyone with
  a SQLite desktop DB from an older version can't upgrade. The desktop app
  needs a fresh-DB path or a one-time data migration script.

---

## Estimated Effort

- Test infrastructure (testcontainers + fixture): ~2-3 hours
- Remove `IS_SQLITE` from server code: ~1-2 hours (mechanical, but must
  verify each call site)
- Collapse alembic DAG: ~1 hour (delete files, update lifespan)
- Electron SQLite isolation: ~3-4 hours (separate module, separate migrations,
  verify desktop build)
- CI updates: ~1 hour
- Documentation: ~1 hour

**Total: ~9-12 hours of focused work.** This is a refactor, not a feature —
it should be done as a single work package with its own branch and full test
suite gates.

---

## Decision Needed (R3)

This overhaul removes a supported database backend from the server and test
paths. Per the decision ledger, this is R3 (one-way door: persisted migration
history, affects desktop app architecture). It requires explicit user approval
with a named invariant before work begins.

The invariant most at risk: **"The Electron desktop app must continue to
function with an embedded database after the server code is PG-only."** If
this invariant is not preserved, the desktop app breaks.
