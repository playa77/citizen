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

### D-008 R1 — 2026-07-19
**Decision:** Fix `.env.example` EMBEDDING_MODEL from `text-embedding-3-small` to `openai/text-embedding-3-small`.
**Rejected:** None — the short model name without provider prefix caused OpenRouter to return 404; the prefix is required by OpenRouter's API contract.
**Rationale:** The default in `config.py` was already correct (`openai/text-embedding-3-small`), but `.env.example` had the wrong value. When the production `.env` was copied from `.env.example`, it overrode the default and broke all embedding calls (corpus update, retrieval).

### D-009 R1 — 2026-07-19
**Decision:** Don't call `handleApiError()` in `fetchGoldset()`; handle Prüfstand-specific errors inline.
**Rejected:** Showing the disclaimer modal on any 403 (including `fetchGoldset()` which fires on passive tab navigation). This hid the entire `#app` container, making the UI unusable.
**Rationale:** The disclaimer modal should only appear on explicit user actions (file upload, analysis start), not on passive tab navigation. `fetchGoldset()` now shows a Prüfstand-local error message. The `fetchEvalReports()` call in the same handler was already safe — it silently returns on non-OK responses.

### D-010 R1 — 2026-07-19
**Decision:** Add a dedicated nginx `location /api/v1/goldset` block with `proxy_buffering off` and `proxy_read_timeout 300s`.
**Rejected:** Increasing the default `proxy_read_timeout` on the generic `/` location (too broad, affects non-SSE endpoints). Adding the goldset path to the existing `/api/v1/analyze` location (would conflate two distinct SSE endpoints).
**Rationale:** The Prüfstand demo analysis at `/api/v1/goldset/{case_id}/analyze` was not covered by the existing `/api/v1/analyze` nginx location, falling through to the default 60s timeout. The deepseek-r1 pipeline runs 5+ LLM calls and can easily exceed 60s. 300s gives generous headroom. Also bumped the main `/api/v1/analyze` timeout from 180s to 300s for the same reason.

### D-012 R2 — 2026-07-19
**Decision:** Restyle the Chat mode (`#chat-mode`) and Case Chat (`#case-chat-section`) to use the app's uniform light theme (`--color-*` variables) instead of the divergent dark `--chat-*` palette. The `--chat-*` variables in `:root` are redefined to alias the `--color-*` tokens (e.g. `--chat-bg: var(--color-background)`, `--chat-surface: var(--color-surface)`), so every existing `var(--chat-*)` reference automatically becomes light-themed without hunting every usage. The chat content is wrapped in `<main>` with the same `max-width: 900px; margin: 0 auto; padding` as the other modes. The shared `<footer id="app-footer">` is now visible in chat mode (was hidden via `setAppFooterVisible(false)`). The `.case-chat-layout` `height: 100vh` bug (which overflowed the analyze-mode section) is fixed to `height: 600px`.
**Rejected:** (a) Hunting every `var(--chat-*)` usage and replacing each with `var(--color-*)` (high-risk, tedious, error-prone — the variable remap achieves the same effect with one edit). (b) Keeping the dark theme for chat and hiding the footer (the user explicitly demanded the chat "fully fit/comply with the app's coherent/uniform UI layout"). (c) Removing the `--chat-*` variables entirely (would break any future code that references them; the aliasing approach preserves backward compat). (d) Removing the `.chat-header` element entirely (the JS references `#chat-header` by ID — preserved as a slim in-panel toolbar instead).
**Rationale:** The user explicitly wants the chat to "fully fit/comply with the app's coherent/uniform UI layout." The variable-aliasing approach is the lowest-risk way to flip the entire chat to light theme: it's a single `:root` edit that cascades to all 100+ `var(--chat-*)` references. Targeted fixes are applied only where hardcoded `rgba()` assumptions leaked through (code block backgrounds, system message borders, error borders, drag-over highlight). The `height: 100vh` bug on `.case-chat-layout` was a clear defect — it caused the case chat to overflow the analyze-mode section and push content below the fold. R2 (not R1) because the change touches the visual identity of two major surfaces (chat mode + case chat) and could affect user perception of the app's consistency — but no external contract or functionality is affected (pure frontend restyling, all element IDs and JS-toggled classes preserved).

### D-011 R2 — 2026-07-19
**Decision:** Extract the per-mode `<header>` blocks (duplicated in `#analyze-mode`, `#settings-mode`, `#pruefstand-mode` with divergent structure and CSS) into a single shared `<header class="app-header">` as the first child of `#app`. Same for the footer (`<footer id="app-footer">`). The subtitle updates dynamically via `switchMode()` in `app.js` based on the active mode. The footer is hidden in chat mode (chat has its own disclaimer line at the bottom of the input area).
**Rejected:** (a) Patching each per-mode header to match the Analyze header's structure (would preserve the duplication that caused the divergence in the first place — the next mode added would diverge again). (b) Keeping Prüfstand's light "paper" header theme (the user explicitly asked for a "coherent/uniform layout throughout the whole app"). (c) Hiding the shared header in chat mode (less uniform; the chat sidebar/main already sit below the header without conflict).
**Rationale:** The user explicitly wants a "coherent/uniform layout throughout the whole app" — the current duplication-per-mode has caused divergence (Prüfstand missing `.header-actions`, `.rechtsstand`, `.profile-banner`; Settings missing the Prüfstand button entirely; Prüfstand using a completely different light header theme). A shared header eliminates the root cause: there is exactly one of each element ID (`rechtsstand-indicator`, `rechtsstand-value`, `profile-banner`, `profile-banner-label`, and the 4 mode button IDs), so `fetchRechtsstand()` and `fetchActiveProfile()` populate the visible header in every mode. The subtitle is the only per-mode text and is trivially updated in JS. R2 (not R1) because the HTML structure change touches every mode container and could affect downstream selectors — but no external contract is affected (this is pure frontend layout).

### D-013 R2 — 2026-07-19
**Decision:** Rewrite `get_embeddings_batch()` to use the OpenRouter batch embedding API (`input: [str, ...]` in a single HTTP request) instead of N individual requests. Add `EMBEDDING_BATCH_SIZE=64` and `EMBEDDING_BATCH_CONCURRENCY=4` config. Increase `CORPUS_INGESTION_TIMEOUT_SEC` from 900 to 1800. Add `progress_cb` callbacks throughout the embedding and upsert pipeline, with `chunks_embedded` / `chunks_upserted` counters in `_job_store`. Frontend shows `done / total (pct%)` with a determinate progress bar.
**Rejected:** (a) Keeping individual requests and just increasing concurrency from 2 to 8+ (still 8582 HTTP round-trips, still slow, still no progress granularity). (b) Increasing the timeout to 3600s without fixing the root cause (just delays the failure). (c) Using a third-party batch library (unnecessary — OpenRouter natively supports array input per its API schema).
**Rationale:** OpenRouter's `/api/v1/embeddings` officially supports `input: string[]` (confirmed in API schema and cookbook). Batch_size=64 is well under OpenAI's 2048-item native limit. With 8582 chunks: 134 batch requests at concurrency=4 → ~17s (was ~1287s at concurrency=2). Pricing is per-token not per-request, so batching is free in cost. The progress callback adds ~477 updates (was 3) — ~159x more granular, satisfying the "two orders of magnitude" requirement. R2 because the embedding transport layer changes, but the interface (`get_embeddings_batch` returns `list[list[float]]` in input order) is preserved and all existing tests pass.

### D-014 R2 — 2026-07-19
**Decision:** Rewrite `_upsert_embedding()` PostgreSQL path to use raw SQL with explicit `(:vec)::vector` cast instead of ORM `insert()`. The ORM model maps `embedding` as `LargeBinary` (BYTEA) for dialect portability, but the actual DB column is pgvector `Vector` type — the ORM sends `$3::BYTEA` which PostgreSQL rejects with `DatatypeMismatchError`.
**Rejected:** (a) Changing the ORM model to use pgvector's `Vector` type (would break SQLite path and require conditional model definitions). (b) Registering a custom asyncpg codec for the vector type (complex, fragile, and only solves the encoding side — the SQL type annotation would still be wrong). (c) Using `sqlalchemy.cast()` with the ORM insert (the `LargeBinary` column type still overrides the cast in the generated SQL).
**Rationale:** Raw SQL with `(:param)::vector` cast is the proven pattern already used in `vector_backend.py`'s `_cosine_distance_pgvector()` (line 207). Wrapping params in parentheses before `::cast` is required because the asyncpg dialect's parameter parser misinterprets `:param::type` without parentheses. This was a pre-existing bug masked by the 900s timeout — the embedding stage never completed before, so the upsert stage was never reached. R2 because the upsert implementation changes, but the interface (`_upsert_embedding` is a private helper) and all existing tests are preserved.

### D-007 PENDING — 2026-07-13
**Status:** Create migration 011 that depends on 006 and applies the cumulative
schema changes from 008+009+010 (CHECK constraint, regime/notes, pii_mapping).
This provides a clean PostgreSQL upgrade path for future fresh deployments.
