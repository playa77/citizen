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

---

### D-015 R2 — 2026-07-19
**Decision:** Replace the unique constraint on `(source_id, hierarchy_path, text_content)` with one on `(source_id, hierarchy_path, text_hash)` where `text_hash = md5(text_content)`.
**Rejected alternative:** SHA-256 would require the `pgcrypto` extension on PostgreSQL. MD5 is sufficient for deduplication (collision probability negligible) and is built into PostgreSQL via the `md5()` function.
**Rationale:** PostgreSQL's btree index row size is limited to ~2704 bytes (v4 btree). When `text_content` is large (8643+ chars for BGB § 309), the index row exceeds this limit and raises `ProgramLimitExceededError` during corpus ingestion. MD5 produces a 32-character hex hash, well within btree limits, and is sufficient for deduplication (the unique constraint is only used for idempotency, not security). Two independent migrations created: `011_pg` (PG branch, `down_revision=006`) and `011_sqlite` (SQLite branch, `down_revision=010`).

### D-016 R2 — 2026-07-19
**Decision:** Fix two bugs causing the Prüfstand goldset demo to always show "Pipeline abgeschlossen, aber keine Ausgabe erhalten": (1) `_cosine_distance_pgvector()` in `app/db/vector_backend.py` now aliases dotted `extra_columns` (e.g. `"lc.text_content"` → `"lc.text_content AS lc_text_content"`) mirroring the SQLite backend, so both dialects produce the same row-dict key structure that `retrieval.py` expects; (2) the Prüfstand SSE handler in `static/app.js` (`startDemoAnalysis`) is restructured to separate `JSON.parse` errors from pipeline error events — real backend errors now propagate to the user instead of being silently swallowed by a catch that only re-threw messages containing the literal `'Pipeline'`.
**Rejected alternative:** (a) Changing `retrieval.py` to access `row["text_content"]` instead of `row["lc_text_content"]` — would break the SQLite backend which correctly aliases, and would create ambiguity when multiple joined tables have a `text_content` column. (b) For the SSE handler, using a custom `PipelineError` class with `instanceof` check — more complex than necessary; separating parse from event handling is the standard pattern and also fixes the drain-buffer section which had the same bug. (c) Removing the `includes('Pipeline')` guard entirely without restructuring — would cause genuine JSON parse errors to surface as user-facing error messages.
**Rationale:** The pgvector aliasing bug is the root cause of the production failure — it only manifests on PostgreSQL, not SQLite, which is why unit tests passed but the deployed app failed. The SQLite backend already had the correct aliasing logic; pgvector was missing it. The SSE swallowing bug is what made the failure a "blackbox": the backend correctly emitted an error event with the real `KeyError` detail, but the frontend silently discarded it. The user explicitly demanded transparent, non-blackbox workflow processing. R2 because the vector backend query generation changes, but the public interface (`cosine_distance()` signature and return type) is preserved, and 6 new regression tests lock in the cross-dialect consistency contract.

### D-017 R2 — 2026-07-19
**Decision:** Overhaul the timeout stack. (1) Wrap `chat_completion()`'s HTTP call in `asyncio.wait_for(timeout)` in `app/core/router.py` to enforce a HARD wall-clock timeout that does not depend on httpx's read timeout (which never fires on streaming/chunked responses because each chunk resets the timer). (2) Add an elapsed-time check inside `chat_completion_stream()`'s token loop that raises `httpx.TimeoutException` when wall-clock time exceeds the timeout. (3) Increase timeout values in `app/core/config.py`: `PIPELINE_TIMEOUT_SEC` 120→480, `TRIAGE_TIMEOUT_SEC` 20→45, `FINAL_TIMEOUT_SEC` 75→150, `EMBEDDING_TIMEOUT_SEC` 15→30, `CALCULATION_TIMEOUT_SEC` 45→90. (4) Increase nginx `proxy_read_timeout`/`proxy_send_timeout` 300s→540s for `/api/v1/analyze` and `/api/v1/goldset`.
**Rejected alternative:** (a) Just increasing `PIPELINE_TIMEOUT_SEC` without fixing the per-call enforcement — would still allow a single streaming LLM call to hang indefinitely until the pipeline-level `asyncio.wait_for` kills it, wasting the entire budget on one stage. (b) Using httpx's `Timeout(read=X)` — does not work for streaming responses because httpx resets the read timer with each chunk received; this is the root cause of the 75s per-call timeout never firing in production. (c) Setting per-call timeouts via `asyncio.wait_for` at each call site in `reasoning.py`/`calculation.py` — would require changing every call site; centralizing in `router.py` is cleaner and covers all callers. (d) Reducing per-call timeouts to fit under the old 120s pipeline budget — would make the pipeline useless for real legal analysis (deepseek-v4-pro takes 60-120s for complex grounded answers).
**Rationale:** The old timeout chain was mathematically impossible: pipeline budget (120s) < sum of per-call timeouts (20+75+75+45=215s), so the pipeline was designed to fail. The per-call httpx timeouts never fired on streaming responses, meaning the only effective timeout was the pipeline-level `asyncio.wait_for(120s)`. The new chain satisfies: nginx (540s) > pipeline (480s) > sum of per-call (45+150+150+90=435s), and per-call timeouts are now HARD wall-clock limits enforced via `asyncio.wait_for`. Verified on production: GS-001 pipeline completed end-to-end in ~215s with all 8 `final_output` sections populated. R2 because the router's internal timeout mechanism changes, but the public interface (`chat_completion`/`chat_completion_stream` signatures) is preserved and all existing tests pass.

### D-018 R2 — 2026-07-20
**Decision:** Fix two critical pipeline failures discovered by Prüfstand goldset testing: (A) model exhaustion due to single-model chain with no fallback and MAX_RETRIES=1; (B) §-reference retrieval failure due to parenthetical stripping and greedy regex in `_extract_norm_references()`.

**(A) Model Fallback:** Changed `FALLBACK_MODEL_1` from duplicate of PRIMARY (`deepseek/deepseek-v4-pro`) to `deepseek/deepseek-chat` and `FALLBACK_MODEL_2` from invalid `/openrouter/free` to `anthropic/claude-3.5-sonnet`. Increased `MAX_RETRIES` from 1 to 3. Changed all 6 LLM call sites in `reasoning.py` from `model=` (single-model no-fallback) to `models=` with the full client fallback chain. Increased per-call timeouts: `TRIAGE_TIMEOUT_SEC` 45→60, `FINAL_TIMEOUT_SEC` 150→180.

**(B) Retrieval Bugs:** Removed `re.sub(r'\s*\([^)]*\)', '', cleaned)` in `_extract_norm_references()` that destroyed §-references inside parentheticals (e.g., `(§ 32 SGB II)`). Changed statute regex from `{0,3}` to `{0,1}` to prevent greedy capture of trailing prose as statute name. Added §-reference direct lookup to the single-area retrieval path in `pipeline.py` (previously only in multi-area path). Relaxed `MAX_COSINE_DISTANCE` 0.55→0.65 and `MAX_CHUNKS_FOR_FINAL` 6→12.

**Rejected alternative:** (a) Fixing only the model exhaustion without the retrieval regex — would let pipeline complete but still produce useless "norms not in chunks" output. (b) Fixing only the regex without the model fallback — pipeline would still die on transient errors. (c) Adding more fallback models without changing `model=` to `models=` in reasoning.py — the single-model override would bypass any fallback chain.

**Rationale:** The model exhaustion was the product of three independent design flaws conspiring: (1) `model=` creates single-model chain bypassing fallbacks, (2) `MAX_RETRIES=1` with no retry headroom, (3) `FALLBACK_MODEL_1` == PRIMARY deduplicated to nothing and `FALLBACK_MODEL_2` was invalid. The retrieval bug was a textbook regex error — the parenthetical stripping intended to clean citation noise was instead destroying §-references, and the greedy `{0,3}` compounded it. Fixing both was mandatory; either alone leaves the pipeline either dead or blind. R2 because the model chain and retrieval regex are internal and the public API is unchanged.
