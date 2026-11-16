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

### D-019 R2 — 2026-08-07
**Decision:** Introduce a single authoritative `DEPLOYMENT_MODE` setting with
three values — `dev`, `self`, `provider` — as the technical embodiment of the
provider/deployer classification. `dev` (author, testing, synthetic data
only) and `self` (author using it on the author's own real Bescheide) rest on
the Art. 2(8) development exemption and the personal-use framing respectively;
`provider` (deployed so that any third party can obtain an analysis) makes the
author a provider under Art. 3(3) and switches on all Art. 50 obligations.
**Rejected:** (a) Inferring provider status implicitly from whether auth is
configured — too fragile, and couples a legal determination to an operational
accident. (b) Treating every deployment as `provider` unconditionally — would
impose provider obligations on the author's own machine, which the personal-use
and development exemptions do not require.
**Rationale:** The obligation set is discontinuous at one event; a single
explicit switch makes that event auditable and prevents silent drift into
provider status. Every compliance feature in P7 keys off this one setting.
Recorded in WP-60; the setting itself is implemented in WP-66.

### D-022 R1 — 2026-08-07
**Decision:** Add `AI-USAGE.md` to the repository root documenting that the
codebase is predominantly AI-generated, and add a one-line notice to the
README. This is voluntary content-authorship transparency, distinct from and
additional to the Art. 50 runtime obligations.
**Rejected:** Folding it into `DISCLAIMER_DE.md`. The disclaimer governs the
*legal character of the software's output*; authorship of the *source* is a
separate concern and belongs in its own file.
**Rationale:** Cheap, honest, and forecloses a later "undisclosed" objection.
Also carries the § 2 Abs. 2 UrhG note that AI-generated code without personal
intellectual creation is not copyright-protected, which is relevant to anyone
forking or commercializing the repo.
Recorded in WP-60; the file itself is created in WP-63.

### D-020 R1 — 2026-08-07
**Decision:** Fix the system's stated intended purpose (Zweckbestimmung, Art. 3(12)) as **claimant-side self-help and advisor assistance** and prohibit any documentation, pitch, or UI copy that describes Citizen as a tool used *by or on behalf of* an authority to evaluate benefit eligibility.
**Rejected:** Leaving the purpose statement implicit. The Annex III(5)(a) high-risk trigger is authority-side eligibility evaluation; the classification turns on the declared purpose, so an undeclared purpose is an unmanaged risk.
**Rationale:** Keeping the declared purpose claimant-side is what keeps the system out of the high-risk regime (Kapitel III). This is a cheap, decisive guardrail, but only if it is written down and enforced against copy drift.
Recorded in WP-61; enforcement is the purpose-drift lint (`scripts/check_purpose_drift.py`).

---

### D-023 R2 — 2026-08-07
**Decision:** Land the `DEPLOYMENT_MODE` setting (D-019) and the new
`CITIZEN_SYNTHETIC_DATA_ONLY` flag in `app/core/config.py` as part of WP-62
(the roadmap allows the setting to land here when WP-66 has not yet run).
Default `DEPLOYMENT_MODE=dev`, default `CITIZEN_SYNTHETIC_DATA_ONLY=false`.
A startup assertion in `app/main.py` refuses to run in `dev` mode unless the
flag is explicitly `true`; document uploads on the dev instance additionally
require `X-Document-Tag: synthetic|goldset`.
**Rejected:** (a) Defaulting `CITIZEN_SYNTHETIC_DATA_ONLY=true` — would let a
dev instance process synthetic-tagged data without an explicit operator
decision, silently defeating the auditable-posture goal of D-019. (b) Putting
the dev-only guard behind an implicit inference (e.g., "running on a VPS")
— exactly the fragility D-019 rejects.
**Rationale:** WP-62's exit criteria require that the dev instance cannot
ingest real data and carries a documented no-real-use posture. An explicit
flag plus startup assertion makes the posture auditable and prevents silent
drift. Tests updated in `tests/conftest.py` to set the flag so the existing
suite keeps running against the dev posture.

### D-024 R3 — 2026-08-25
**Decision:** Resolve the dual-database reality by standardizing on
PostgreSQL 16 + pgvector for server, CI, and ALL tests (unit included).
Delete the SQLite code path entirely: `IS_SQLITE` branches, sqlite-vec,
the SQLite alembic chain (007→010, 011_sqlite), and the raw-SQL `::vector`
workarounds. The ORM `ChunkEmbedding.embedding` column becomes pgvector's
`Vector(1536)`.
**Rejected:** Keeping both backends with cross-dialect parity tests. After
the Electron client is removed from this repository (D-025), SQLite has zero
remaining deployment consumers — parity testing would preserve permanent
double-maintenance of every SQL fragment and both migration DAGs for no user.
**Rationale:** Human decision, given verbatim: "Postgres-only everywhere".
Stated consequences accepted: developers need Docker (or a reachable PG) to
run any test; existing SQLite `citizen.db` files become unsupported with no
data-migration path. This is the direction already outlined in
`LETSFIXSTUPIDDBDESIGN.md`; with Electron gone, its "isolate SQLite for
desktop" clause is moot. Unit tests now execute the exact production SQL,
closing the blind spot that produced D-014/D-016.

### D-025 R2 — 2026-08-25
**Decision:** Refactor Citizen into an API-only service. Remove all web UI
(`static/`, HTML-serving routes, static mount) and all GUI client code
(`electron/` tree incl. PyInstaller spec, `scripts/apprun.sh`). The only
external interface is the existing REST API under `/api/v1`. Task instructed
by the repository owner ("a GUI client will no longer live in this
repository").
**Rejected:** Keeping a thin web shell or moving the frontend to a separate
repository — neither was requested; a separate repo is a future decision.
**Rationale:** Owner-instructed. `/health`, `/robots.txt` (WP-62 compliance),
and FastAPI's self-description endpoints (`/docs`, `/redoc`, `/openapi.json`)
are retained: they are machine-facing or compliance surfaces, not end-user
web UI. Full contract to be documented in `API_DOCUMENTATION.md`.

### D-026 R2 — 2026-08-25
**Decision:** Unit tests obtain PostgreSQL via a session-scoped
testcontainers fixture (`pgvector/pgvector:pg16`). A pre-set `DATABASE_URL`
overrides the container (CI points at its service container directly).
**Rejected:** Requiring an explicit externally-running PostgreSQL with no
fallback — breaks `pytest tests/unit/` ergonomics for anyone without a local
PG; testcontainers keeps one-command test runs at the cost of Docker being
required (accepted in D-024).
**Rationale:** Keeps the AGENTS.md promise of a single test command while
making unit tests run production SQL per D-024.

---

## Invariants — api-only-refactor task (derived 2026-08-25)

**Guarded** (guard test installed + green before completion):
- **G1 Route surface:** every pre-refactor `/api/*` route + `/health` +
  `/robots.txt` survives unchanged in method and path; zero HTML/static
  routes remain. Guard: route-surface test asserting the explicit expected
  list equals `app.openapi()` routes.
- **G2 Single migration DAG:** fresh PostgreSQL reaches head via singular
  `alembic upgrade head`; exactly one head revision exists.
  Guard: extended `tests/unit/alembic/`.
- **G3 Vector round-trip on production SQL:** embed → upsert →
  `cosine_distance()` with aliased extra columns succeeds against real
  PostgreSQL (entrenches D-014/D-016 fixes as the only path).
  Guard: integration retrieval test.
- **G4 Doc-route parity:** every endpoint documented in
  `API_DOCUMENTATION.md` corresponds 1:1 to `app.openapi()` routes.
  Guard: parity test parsing the doc's path table.
- **G5 Toolchain:** full pytest (unit+integration), ruff check/format, mypy
  strict, purpose-drift lint all green.

**Triggered** (review-flagged paths, diff checked):
- **T1** Root URL `/` changes from serving HTML to 404 JSON — intentional,
  owner-approved breaking change (D-025).
- **T2** Existing SQLite desktop databases become unsupported, no migration
  path — accepted consequence of D-024.
- **T3** `python -m app.main --data-dir` desktop launcher removed with the
  desktop block in `main.py`.

### D-027 R2 — 2026-08-25
**Decision:** Migration `012_pg_collapse_sqlite_branch` re-admits
`'disclaimer_ack'` to the `pipeline_stage_log.stage_name` CHECK constraint,
alongside the nine pipeline stages carried over from former migration 008.
**Rejected:** (a) Removing the `disclaimer_ack` insert from
`app/services/audit.py` instead — changes documented WP-015 audit semantics
("7 stages + 1 disclaimer_ack") and is a business-behavior change out of
scope for this refactor. (b) Leaving the constraint at nine values — every
audit-trail insert violates it on PostgreSQL, so no CaseRun/stage logs are
ever persisted (surfaced by `test_full_pipeline_execution`: FK/Check
violations, case_count 0).
**Rationale:** The writer (`services/audit.py`) defines the data contract;
former migration 008 narrowed the constraint without updating the writer.
Aligning the constraint is the minimal data-model fix. Idempotent DDL keeps
it safe on production databases already carrying manual-DDL state (D-005).

### D-028 R2 — 2026-08-25
**Decision:** Test-harness repairs applied where tests had rotted behind
production evolution (no business logic touched): disclaimer ack headers use
`DISCLAIMER_VERSION` rather than the package version; uploads send
`X-Document-Tag: synthetic`; pipeline stubs match current call signatures;
stage-sequence assertions follow `_STAGES`; integration suite gains an
event-loop/pool isolation fixture (`tests/integration/conftest.py`);
corpus seeding uses asyncpg against `DATABASE_URL`.
**Rejected:** Leaving the suite red and reporting it as pre-existing debt —
the task gates delivery on a passing suite, and every repair was confined to
test code.
**Rationale:** The suite had drifted into 39 latent failures (13 unit, 26
integration) invisible because prior local environments ran stale package
installs. Post-repair: 878 passed / 0 failed against real PostgreSQL.

### D-029 R2 — 2026-08-25
**Decision:** Consolidate all disclaimer/notice/statement documents into two
files: `DISCLAIMER_DE.md` and `DISCLAIMER_EN.md` (v2.0.0), each containing
three parts — A project statement (former `STATEMENT.md`), B legal notice and
disclaimer (former `DISCLAIMER_*.md` v1.1.0), C AI Act classification (former
`COMPLIANCE.md` / `COMPLIANCE-EN.md` v1.1.0). The three source files are
deleted. Content aligned to the current implementation while merging:
B.12 acknowledgment mechanics now describe the actual logging (version via
`X-Disclaimer-Ack`, audit row per analysis run — no document checksum, which
no code computes); active-profile display via `GET /meta/active-profile`;
`DEPLOYMENT_MODE` described as implemented incl. startup/ingest guards;
UI references removed (D-025); nonexistent `AI-USAGE.md` marked planned.
**Rejected:** Keeping three separate documents and only cross-linking — the
task explicitly required one complete document per language; three files with
overlapping scope had already produced divergent claims about what the app
logs.
**Rationale:** Owner-instructed consolidation ("condense/merge all
disclaimer/notice/statement documents into DISCLAIMER_EN.md and
DISCLAIMER_DE.md"). Accepted consequences: README/devdocs inbound links
updated; the purpose-drift lint's default glob targets `STATEMENT.md` and
`COMPLIANCE*.md` no longer match anything (script prints warnings, still
exits 0 — behavior unchanged by design this sweep); `DISCLAIMER_*.md` is not
in the lint's default target list, so merged compliance copy is currently
outside its automatic scan — flagged as a coverage gap for a future code
change.

### D-030 R1 — 2026-08-25
**Decision:** Documentation-reconciliation sweep against the executable
sources; no production code changed. Updates: README (API-only wording,
rate-limiter-not-mounted, tsvector→ILIKE keyword fallback, real documents
routes, current defaults PIPELINE_TIMEOUT_SEC=480 / RETRIEVAL_MODE=
per_question / 8 migrations / 37 test files, disclaimer links, no-checksum
acknowledgment, corpus source hosts); `.env.example` rewritten to mirror
`app/core/config.py` 1:1 (removes phantom `CORS_ORIGINS`, corrects all
defaults); DEPLOYMENT.md (drop nonexistent `SECRET_KEY`, nginx SSE timeouts
300s→540s per D-017); devdocs/DEV-INSTANCE.md (banner via API field,
references to deleted COMPLIANCE.md and never-created PROVIDER-GO-NOGO.md
fixed); historical status banners on docs/ planning artifacts;
LETSFIXSTUPIDDBDESIGN.md marked RESOLVED via D-024..D-026; .gitignore gains
`.corpus_sources.json` and `docker-compose.override.yml`, trailing-space fix.
**Rationale:** Code is authoritative; docs had drifted behind the v2.0.0
refactor. Guarded invariants: purpose-drift lint green over the new
disclaimer pair; `test_api_documentation.py` parity green (doc untouched);
README route table matches `app.openapi()` routes.

### D-031 R1 — 2026-08-25
**Decision:** Remove orphaned/stale documentation: `LETSFIXSTUPIDDBDESIGN.md`
(resolved outline for the already-implemented DB overhaul), six v1.0.0-era
planning artifacts in `docs/` (design_document, design_v1.0.0,
technical_specification, GAP-REPORT, ARCHITECTURE-ACTUAL,
wp-1.6-pruefstand — all banner-marked superseded, describing the removed
web UI/Electron/SQLite state, and referenced only by each other), and
`docs/goldset-v0.1.0.yaml` (byte-identical duplicate of
`eval/goldsets/goldset-v0.1.0.yaml`; all code/config references point to
`eval/goldsets/`). `docs/roadmap-v2.0.0.md` is kept: it has live inbound
references from `DISCLAIMER_DE.md`, `DISCLAIMER_EN.md`, and
`devdocs/DEV-INSTANCE.md`; removing it would require editing versioned
compliance documents, which is out of scope for a cleanup sweep.
Append-only ledgers (DECISIONS.md, CHANGELOG.md) keep their historical
mentions of the removed files.
**Rejected:** Keeping the docs as banner-marked historical artifacts
(the D-030 posture) — owner instructed removal; git history preserves them.
Also rejected: deleting `roadmap-v2.0.0.md` with its referencing lines —
that rewrites compliance copy (v2.0.0 disclaimer pair) without a content
decision.
**Rationale:** Every deleted file was either fully implemented/resolved or
describes a repository state that no longer exists; their "current truth"
pointers already name surviving documents (AGENTS.md,
API_DOCUMENTATION.md). Reversible via git at zero cost (R1).

### D-032 R1 — 2026-08-25 — Art. 50 AI Act disclosure & provenance fields
**Decision:** Implement Art. 50 VO (EU) 2024/1689 disclosure/provenance embedding
(owner-delegated task spec). One new module `app/services/disclosure.py` holds the
Pydantic models (`DisclosureInfo`, `ProvenanceMarker`), the canonical DE/EN
disclosure constants (`DISCLOSURE_VERSION = "1.0"`,
`PROVENANCE_SPEC_VERSION = "citizen-provenance-v1.0"`), and the single shared
helper `build_disclosure_and_provenance(settings)` (no I/O, never raises — every
field extraction falls back to `"unknown"` with a warning). Embedded on exactly
the three AI-content surfaces named by the spec: analyze SSE terminal event,
conversation chat `done` event (`generate_chat_response`), and
`GeneratedDocument.provenance`; plus new `GET /api/v1/meta/disclosure`
(response_model declared so openapi.json reflects it) and a `disclosure_version`
key added to `GET /api/v1/meta/version`. API_DOCUMENTATION.md updated (G4 parity
guard requires it for the new route).
**Sub-decisions (all R1 unless noted):**
- `X-Disclaimer-Ack` enforcement on `/meta/disclosure` via a route-level FastAPI
  dependency, NOT via the middleware — editing `DisclaimerMiddleware` is
  forbidden by the task, and the middleware currently excludes ALL of
  `/api/v1/meta*` (the task text claimed only `disclaimer/version` is exempt;
  `test_meta_endpoints_bypass_disclaimer` confirms). Existing meta endpoints stay
  unprotected — changing their contract is forbidden.
- `model_profile` sourced from `settings.INFERENCE_PROFILE` (getattr fallback
  `"unknown"`), not `get_active_profile()` — avoids YAML file I/O and the
  ValueError path inside a must-not-raise function.
- `timestamp_utc`: ISO 8601 UTC, second precision, `Z` suffix
  (`_utc_now_iso()` factored out so tests can freeze the clock).
- Conversation first-message pipeline terminal event
  (`run_first_message_pipeline`) and case-chat `done` (`case_chat.py:236`) are
  intentionally NOT extended: spec names three surfaces; both are logged here as
  observed Art. 50(2) coverage gaps for a future decision, not silently skipped.
**Rejected:** Editing middleware EXCLUDED_PREFIXES (forbidden); adding
`response_model` to existing dict-returning endpoints (changes existing OpenAPI
contracts); putting disclosure on `GeneratedDocument` (spec forbids — document
generation is downstream of an already-disclosed analysis).
**Invariants derived from the task spec:**
- guarded G-50-A: `/meta/disclosure` returns 200 `{version="1.0",
  must_display_before="results", texts={de,en}}` with correct ack header; 403
  without/mismatched header.
- guarded G-50-B: `/meta/version` includes `disclosure_version:"1.0"`;
  existing keys unchanged.
- guarded G-50-C: analyze terminal SSE event has top-level `disclosure` +
  `provenance` with required fields/types; error events carry neither.
- guarded G-50-D: chat `done` event carries both fields.
- guarded G-50-E: `/documents/generate` response carries `provenance`; carries
  no `disclosure`.
- guarded G-50-F: helper returns valid instances and never raises on a broken
  settings object (fallbacks + warning log).
- guarded G-50-G: models serialize to valid JSON (model_dump_json round-trip);
  openapi.json parses and contains the new path/schema.
- triggered T-50-H: disclaimer system untouched (middleware, disclaimer/*
  endpoints, DISCLAIMER_*.md) — any diff touching these is flagged.
- triggered T-50-I: no disclosure/provenance on error/corpus/goldset/eval/
  intake/presets routes; DEPLOYMENT_MODE/X-Document-Tag/dev-guard logic
  unchanged; all payload changes additive-only (existing keys untouched).

### D-033 R1 — 2026-08-25 — Connection-leak fix in get_case_endpoint (D-032 follow-up)
**Decision:** While writing G-50-E, every 200-response from
`POST /documents/generate` leaked one pooled asyncpg connection until GC
(exit-time `SAWarning: non-checked-in connection`; one run even failed with a
cross-loop Future error before the test harness was made single-loop). Root
cause found in pre-existing app code: `get_case_endpoint` executed its
`legal_areas` query against the session AFTER the ``async with`` block had
closed it (cases.py), silently reopening the session whose transaction kept
the connection checked out forever. Fixed by moving the query (and the
``case is None`` guard) back inside the session block; response payload is
byte-identical. Flagged to the owner as an out-of-original-scope but
task-exposed defect repair; no contract change, no behavior change.
**Rejected:** Leaving it unfixed with a documented warning — the leak fires on
every `GET /cases/{id}` and `POST /documents/generate` in production, and
shipping tests that normalize connection-leak noise would defeat the audit
trail the disclosure work is meant to strengthen.
**Rationale:** Three-line scoping fix, fully reversible (R1); verified by the
leak-free test run (`pytest tests/unit/test_disclosure.py` — no SAWarning) and
the full green suite (854 unit + 37 integration).

---

## Re-founding on the free public path (2026-11-16)

Owner decisions given in conversation on 2026-11-16 (answers to clarifying
questions): free public path; Sozialrecht becomes a pluggable module and stays
the default; ten further area modules queued; roadmap v3.0.0 with `/api/v1`
kept additive; full free-path scope incl. dossier, UI, funding. This sweep is
**documentation and architecture only** — no production code changed.
Artefacts: `ARCHITECTURE.md`, `docs/roadmap-v3.0.0.md`,
`docs/module-catalog.md`.

### D-034 R2 — 2026-11-16 — Free public path
**Decision:** Citizen follows the free public path (landscape survey
addendum "05 — free public path", 2026-11-15): the whole project stays MIT and
free, makes no money, and is not built for lawyers. Product center: a
client-side preparation assistant that lets a person arrive at a lawyer or
advice-center appointment with the information the professional needs; the
central deliverable is the Mandatsvorbereitungs-Dossier.
**Rejected:** (a) Path 1 — open core plus friction plus paid services;
(b) Path 2 — clean-room closed commercial product. Both require purpose
revisions, carry commercial RDG/UWG exposure, and do not serve the declared
claimant-side purpose as directly.
**Rationale:** Owner decision. Lowest regulatory friction (own-matter RDG
posture, FOSS carve-out with Art. 50 already implemented), zero running cost,
direct social impact; keeps every later option open. Accepted consequence:
sustainability depends on grants, institutional adopters and bounded
community contributions, not sales (roadmap v3.0.0 Track G).

### D-035 R2 — 2026-11-16 — Declared purpose widened (amends D-020)
**Decision:** The intended purpose (Art. 3(12) KI-VO) becomes:
**citizen-side self-help and appointment preparation for natural persons in
their own legal matters, across the enabled legal-area modules, plus
assistance to advice centers acting within their own RDG basis.** The D-020
prohibition is generalised: no documentation, pitch or UI copy may describe
Citizen or any module as a tool that an authority, court, law-enforcement or
migration body (or a contractor acting for one) uses to evaluate, decide on or
enforce against individuals. Each module adds its own deny phrases (e.g. Annex III(6)
law enforcement for Strafrecht, Annex III(7) migration for Aufenthaltsrecht).
**Rejected:** Keeping D-020's SGB-II-only wording and adding areas under it —
the purpose statement would no longer describe the system, which is exactly
the unmanaged-classification risk D-020 exists to prevent.
**Rationale:** Widening breadth is a purpose change and must be declared, not
drifted into. Takes effect in compliance copy with DISCLAIMER v3.0.0
(roadmap WP-96); until then the disclaimer pair and `DISCLAIMER_VERSION` stay
unchanged, and non-Sozialrecht modules remain `experimental`.

### D-036 R2 — 2026-11-16 — Core + module architecture; Sozialrecht default
**Decision:** Restructure into a domain-neutral core plus legal-area modules
(contract: `ARCHITECTURE.md` § 2). The existing SGB II/X implementation is
extracted into `modules/sozialrecht` as the first module and is the default
via a new setting `DEFAULT_MODULE` (default `sozialrecht`): any request that
names no module runs exactly as in v2.0.0. Modules are predominantly data and
content; code only for deterministic calculators through a typed SDK. The
Fristen engine is split into a generic core (calendar, Bekanntgabe fictions,
rollover) and per-module deadline specs as data.
**Rejected:** (a) One fork/deployment per area — multiplies maintenance of the
compliance core. (b) Keeping area logic in core services behind
`if area == …` branches — that is the v2.0.0 state that this decision
dissolves; it does not scale past one verified area.
**Rationale:** Owner instruction. The hard parts of Citizen (evidence binding,
quote verification, deterministic engines on versioned parameters, regime
handling, goldset gating, compliance posture) are already German-law-generic;
the area knowledge is the variable part and belongs in reviewable packages.
P9 exit gate: zero goldset regression vs a frozen v2.0.0 baseline.

### D-037 R2 — 2026-11-16 — Module enablement defaults follow DEPLOYMENT_MODE
**Decision:** If `ENABLED_MODULES` is unset, the enabled set is: in `dev` and
`self` every installed module of tier `experimental` or `verified`; in
`provider` only `verified` modules. `community` modules are never enabled
implicitly. `DEFAULT_MODULE` must be in the enabled set or startup fails.
**Rejected:** (a) Default `["sozialrecht"]` everywhere — would turn today's
accepted experimental-area requests into errors in `dev`/`self`, a breaking
change to `/api/v1`. (b) All installed modules everywhere — would expose
ungated modules to third parties in `provider` mode, against the duty of care
for vulnerable users.
**Rationale:** Re-uses the one auditable switch of D-019 for the one
question that matters at deployment: are third parties served by an unverified
module. Preserves current v2.0.0 behaviour in the default `dev` posture.

### D-038 R1 — 2026-11-16 — Module queue and legacy area keys
**Decision:** Queue ten modules beside Sozialrecht, in this default order:
M1 `schuldnerrecht`, M2 `mietrecht`, M3 `arbeitsrecht`, M4 `vertragsrecht`
(Verbraucher-/Vertragsrecht), M5 `verkehrsrecht`, M6 `familienrecht`,
M7 `aufenthaltsrecht`, M8 `steuerrecht` (ESt natural persons), M9 `erbrecht`,
M10 `strafrecht` (profiles: `docs/module-catalog.md`). Legacy v2.0.0 keys:
`schenkungsrecht` → alias of `erbrecht`; `vertragsrecht` → id kept for M4;
`verwaltungsrecht` → core procedural library, not a module; `andere` →
engine-less catch-all at `experimental`.
**Rejected:** Ordering by author interest or by existing experimental code —
the addendum requires necessity first; the order is a necessity hypothesis
(clientele overlap with Sozialrecht, existential stakes, deadline shortness,
deterministic tractability), to be re-ordered by decision when adopter
evidence arrives (roadmap OQ-4). Aufenthaltsrecht is placed after the
multilingual UI layer because it cannot serve its clientele without it.
**Rationale:** Owner selected the area set (proposed set plus Strafrecht);
module ids reuse existing keys where they exist to avoid data migration.

### D-039 R2 — 2026-11-16 — API stays /api/v1; versioning scheme
**Decision:** No `/api/v2`. Module support is additive to `/api/v1`:
`legal_areas` values are module ids, empty → `DEFAULT_MODULE`; new
`/modules*` and `/cases/{id}/dossier` routes; new error codes
`MODULE_NOT_ENABLED`, `MODULE_UNKNOWN`; additive response keys only. Core
package version becomes 3.0.0 at P9 exit (declared-purpose change is a
major event). Modules carry their own semver with a `core_api` compatibility
range; parameter sets, goldsets, dossier schema (`citizen-dossier-v1.0`),
provenance spec (`citizen-provenance-v1.1`, adds module ids/versions) and
disclaimer are versioned independently (`ARCHITECTURE.md` § 6). Every
`case_run` records the module versions it ran with.
**Rejected:** Module-scoped `/api/v2/{module}/…` routes — a breaking change
with no client benefit while one generic route set serves all modules.
**Rationale:** Owner decision on versioning; existing clients and the
G4 doc-parity guard keep working; reproducibility of every date and amount
requires pinning every input.

### D-040 PENDING — 2026-11-16 — Consumer UI location
**Status:** Recommended: the consumer UI lives in a separate repository
(`citizen-web`) that consumes `/api/v1`; D-025 (no UI in this repository)
stands. Alternative: reverse D-025 and serve a local-first web app from this
backend. Owner decision required before roadmap WP-120; D-025 was
owner-instructed and is not reversed by this sweep.

### D-041 R1 — 2026-11-16 — Module licensing and third-party code
**Decision:** All first-party modules are MIT. Inbound contributions are
MIT-in = MIT-out with DCO sign-off; no CLA (the CLA requirement belonged to
the closed-variant paths). AGPL/GPL components (e.g. gettsim for tax/benefit
math, CourtListener) are never embedded in the core or a module; they may be
used only as unmodified sidecars behind an API, or replaced by law-derived
MIT reimplementations.
**Rejected:** Embedding gettsim in the Steuerrecht module — would make the
distribution AGPL.
**Rationale:** Keeps the whole project unambiguously MIT, which is what makes
module contribution and institutional reuse frictionless.

### D-021 R2 — 2026-11-16 — RDG single-case invariant (ratification; carry-over C-1)
**Decision:** Treat the RDG single-case boundary as a hard product invariant:
every output is Rechtsinformation plus building blocks requiring human
adjudication; no output is presented as a completed legal assessment of the
individual case, and the generated action documents remain drafts with
`[BITTE PRÜFEN]` placeholders for anything unadjudicated. The provider-mode
deployment path for advice centers is documented against § 6/§ 8 RDG
(unentgeltliche Rechtsdienstleistung / anerkannte Beratungsstellen), not
against a claim that the tool itself renders no Rechtsdienstleistung.
**Rejected:** Relying solely on the existing § 2 RDG disclaimer text. A
disclaimer does not change what the software functionally does; the invariant
has to live in the product behavior, not only in the notice.
**Rationale:** This is the highest residual legal risk. The mitigation must be
structural (human-in-the-loop enforced by the pipeline) and must survive the
transition to advice-center use, where the RDG analysis actually shifts.
**Note (WP-90):** Ratification event, not a new decision — D-021 was proposed
in roadmap v2.0.0 § 1 and cited as built (WP-67, generator invariant) but was
never appended to this ledger. Owner confirmed ratification 2026-11-16
(roadmap v3.0.0 § 2, item C-1); wording unchanged from roadmap v2.0.0 § 1.

---

## P9 first batch — WP-90/91/92 (2026-11-16)

### D-042 R1 — 2026-11-16 — Module contract shape at core_api 3.0 (WP-91)
**Decision:** `manifest.schema.json` requires only `id`, `version`,
`core_api`, `title`, `tier` and permits (not requires) the content sections
(`scope`, `corpus`, `parameters`, `fristen`, `calculators`, `documents`,
`intake`, `dossier`, `regimes`, `goldset`, `compliance`, `legacy_aliases`).
`sdk.py` exports `SDK_VERSION = "3.0"` and nothing else. The registry exposes
`discover_modules`, `compute_enabled_set`, `load_registry`,
`load_registry_from_settings`, `ModuleRegistry.resolve` → `ModuleResolution`.
**Rejected:** (a) Making all § 2.2 sections required now — WP-91 ships
manifest-only modules ahead of WP-93; requiring files that cannot exist yet
would make the shipped sozialrecht manifest invalid, contradicting WP-91's
own exit criterion. (b) Pre-defining `Calculator`/`RegimeProvider` protocols
in the SDK before any module code exists — speculative API that WP-93 would
immediately change; the surface grows with the first real consumer.
**Rationale:** The schema is the review boundary for community modules; a
minimal required set plus `additionalProperties: false` keeps manifests
strict where the core already consumes them and open where content is still
moving. Structural validation of declared files (corpus/fristen paths) is
deferred to WP-93 with the files themselves.

### D-043 R1 — 2026-11-16 — Enablement edge cases and conftest default (WP-91)
**Decision:** (a) An `ENABLED_MODULES` id that is not installed raises
`UnknownEnabledModuleError` at startup instead of being ignored — the
audit-relevant enablement list naming a non-existent module is a
configuration error. (b) `tests/conftest.py` sets only `DEFAULT_MODULE`;
`ENABLED_MODULES` is deliberately left unset because its configured default
*is* "unset" (the D-037 tier rule) — setting it in conftest would mask the
default path in every test. (c) Built-in legacy alias `schenkungsrecht →
erbrecht` (D-038) lives in the registry and resolves even while `erbrecht`
is not yet installed; a manifest-declared alias always shadows the built-in
map. (d) Discovery skips directories without `module.yaml` (staging/scratch)
but the first invalid manifest aborts discovery — startup must refuse a
partially-known module set rather than silently run with a subset.
**Rejected:** Treating unknown enabled ids as a warning — in `provider`
mode a typo would silently narrow the served set against D-037's intent.
**Rationale:** Startup refusal is the cheapest point to catch configuration
drift; WP-95's `MODULE_NOT_ENABLED`/`MODULE_UNKNOWN` error codes handle the
request-time cases instead.

### D-044 R1 — 2026-11-16 — jsonschema dependency for manifest validation (WP-91)
**Decision:** Add `jsonschema>=4.21,<5.0` to `pyproject.toml` dependencies;
manifests are validated with `Draft202012Validator` against
`app/modules/manifest.schema.json` (validator instance cached per
`core_api` version).
**Rejected:** (a) Hand-rolling a validator — the schema artefact is part of
the module contract (WP-91 scope) and must be validated *as* JSON Schema,
not just enforced by ad-hoc checks. (b) `fastjsonschema` — smaller, but the
standard `jsonschema` library keeps the schema readable and error reporting
consistent.
**Rationale:** Module manifests are the compliance-relevant contract for
community contributions; validation quality outweighs the dependency cost.

### D-045 R1 — 2026-11-16 — Fristen core split and spec-shape extensions (WP-92)
**Decision:** Generic machinery moves to `app/fristen/` (calendar,
`fictions`, `rollover`, `rbb`, `specs`, `evaluator`, `results`); the SGB
X/SGG rules are data in `modules/sozialrecht/fristen.yaml` and are evaluated
by the generic evaluator. Two spec keys extend the § 2.3 example:
`fristbeginn_basis` (the area's Fristbeginn citation, e.g. "§ 64 Abs. 1
SGG, § 187 Abs. 1 BGB") and `not_applicable` (`frist_typ` +
area-specific explanation text for the non-applicable case, e.g. § 31 SGB
X "kein Verwaltungsakt"). Library ids a module may declare but that no
implementation covers (`vwvfg_41_2`, `ao_122_2`, `zpo_222`, `vwgo_57`,
`stpo_43`, `ao_108`) raise `NotImplementedError`, and unsupported trigger
values fail at spec-load time.
**Rejected:** (a) Keeping the non-VA and Fristbeginn wording in the core —
both quote area law (§ 31 SGB X, § 64 Abs. 1 SGG) and would be the first
area-specific strings back in the core, against the split's own rule.
(b) Pre-implementing the other procedure codes' rollovers from memory
(e.g. § 108 Abs. 2 AO's Saturday-as-Werktag semantics) — unverified legal
constants in a correctness-critical core; each lands with its module and
golden date tests. (c) A partially-tolerant evaluator that silently
degrades unknown ids — a deadline engine must fail loudly, never guess.
**Rationale:** Output contract shape is unchanged (`FristResult`, extended
additively with `module_id`/`spec_id`, default `None`); every existing
caller keeps working, and the existing `tests/unit/test_fristen.py` runs
unchanged through the spec path.

### D-046 R1 — 2026-11-16 — Compatibility shim in app/services/fristen.py (WP-92)
**Decision:** `app/services/fristen.py` becomes a thin shim:
`compute_widerspruchsfrist` keeps its exact signature and delegates to
`evaluate_spec` with the `widerspruch_sgg_84` spec from
`modules/sozialrecht/fristen.yaml` (loaded once, cached); the moved
calendar helpers are re-exported under their historical underscore names
(`_is_holiday`, `_is_workday`, `_next_workday`, `_same_day_next_month`).
**Rejected:** (a) Updating all callers now — the callers (document
generators, eval metrics) move into the module at WP-93; re-pointing them
twice is churn. (b) Deleting the underscore aliases and editing
`tests/unit/test_fristen.py` — the batch invariant requires that test file
to pass *unchanged*.
**Rationale:** The shim is transitional and clearly marked; WP-93 removes
it. One transitional wrinkle, accepted: the core shim reads module *data*
(YAML) by path — a data dependency in the direction core → module that
dissolves when the caller moves at WP-93; it is not area-specific code in
the core.

### D-047 R1 — 2026-11-16 — types-PyYAML in dev extras (WP-91/92 gate repair)
**Decision:** Add `types-PyYAML>=6.0` to the `[dev]` extras. Without the
stubs, `mypy app/` (strict) fails on every PyYAML import — including on
untouched `main` (`app/services/inference_profiles.py`,
`eval/goldset_loader.py`), where the gate was already red.
**Rejected:** Disabling the `import-untyped` error code for `yaml` — hides
the finding instead of fixing it.
**Rationale:** The batch invariant requires a green strict typecheck; the
missing stub package is an environment gap, not a code defect. Verified:
main fails with the same error class before this change.

**Recorded alongside (no D-entry, measured fact):** on untouched `main`,
`ruff check app/` reports 73 pre-existing violations and `ruff format
--check app/` flags `app/core/config.py` (reformatting it would introduce
new E501s — the file currently fails both gates). This batch introduces no
new ruff violations, and `app/fristen/`, `app/modules/` and
`app/services/fristen.py` are check- and format-clean.

### D-048 R1 — 2026-11-16 — OQ-1 alternate deadline follows the governing duration (WP-92, review finding)
**Decision:** When the § 37 Abs. 2 SGB X fiction lands on a non-workday
(OQ-1) *and* the Rechtsbehelfsbelehrung is defective, the
`oq1_alternate_ende` alternate is computed with the **governing** duration
(one year), not with the regular one-month duration. Pinned by
`test_oq1_alternate_uses_governing_duration`.
**Rejected:** Restoring the pre-split engine's behavior (alternate always
+1 month): there the "citizen-favorable" alternate (e.g. 08.02.2024) falls
*before* the primary end (07.01.2025) — incoherent for a citizen-favorable
reading. (b) Leaving the drift unrecorded: a silent semantic change against
the batch's own zero-behavior-change criterion is exactly what the
decision ledger exists to prevent.
**Rationale:** Found by the fresh-context reviewer via differential
execution (385,704 input combinations; this was the only behavioral
difference, ~3.5% of the grid, uncovered by the unchanged test suite). The
new behavior is a correction, not a regression; it is now recorded and
pinned. Affects only the informational `oq1_alternate_ende` field and the
Alternativberechnung line — never the primary `frist_ende`.

### D-049 R1 — 2026-11-16 — core_api range is enforced against the running SDK version (WP-91, review finding)
**Decision:** `load_registry` refuses startup with `ModuleContractError`
when an *enabled* module's `core_api` range does not admit the running
`app.modules.sdk.SDK_VERSION` ("3.0"). Range forms follow the schema
pattern (`">=3.0,<4.0"`, `">=3.0"`, exact pins); an unparsable range is a
`ModuleManifestError`, never silently compatible. Duplicate module ids
(two directories declaring one id) also abort discovery instead of
silently overwriting.
**Rejected:** Deferring contract-version matching to WP-93 — D-042 deferred
structural *file* validation, not the contract check; without it the
`core_api` field validates format only and an incompatible community
module surfaces as runtime breakage instead of the designed startup
refusal (ARCHITECTURE.md § 6.1).
**Rationale:** Reviewer finding; the contract field exists precisely to
make the compatibility boundary explicit and enforced.
