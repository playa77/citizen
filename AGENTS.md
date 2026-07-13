# Citizen — Agent Context

## Project

Local-first, evidence-constrained legal reasoning engine for German law (multi-area: SGB,
BGB, Erbrecht, Mietrecht, Arbeitsrecht, etc.). Python 3.11+, FastAPI, SQLAlchemy async,
PostgreSQL 16 + pgvector, vanilla HTML/JS/CSS frontend with SSE streaming.

**Package manager:** `uv` (see `uv.lock` — though it's excluded from OpenCode context via
`.opencodeignore`). Dependencies are pinned in `pyproject.toml`.

**Key constraints:**
- All LLM calls go through `app/core/router.py` (OpenRouter with fallback chain:
  `PRIMARY_MODEL → FALLBACK_MODEL_1 → FALLBACK_MODEL_2`)
- API endpoints in `app/api/routes/` (12 route modules, 30+ endpoints)
- Database models in `app/db/models.py` (14 ORM models + 1 abstract base), migrations via Alembic (10 migrations)
- Frontend in `static/` — vanilla JS, no frameworks. Three modes: Analyze, Chat, Settings.
  All frontend files at v1.0.0.
- Settings loaded from `.env` via `pydantic-settings`. `settings` is a lazy singleton
  (see Gotchas below).
- Strict mypy (`pyproject.toml` `strict = true`), ruff formatting (line-length 100, rules
  `E,F,W,I,UP,B,C4,SIM,RUF`), pytest with `asyncio_mode = auto`

## Commands

```bash
# Install (uses uv)
uv pip install -e ".[dev]"

# Lint & format
ruff check app/ tests/
ruff format --check app/ tests/
mypy app/

# Tests — conftest.py sets default DATABASE_URL and OPENROUTER_API_KEY env vars
# so unit tests run without a live database or real API key.
pytest tests/unit/ -v

# Integration tests require a running PostgreSQL with pgvector + alembic applied:
alembic upgrade head
pytest tests/integration/ -v

# All tests
pytest -v

# Run the app (needs DATABASE_URL + OPENROUTER_API_KEY in .env)
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Gotchas

### `settings` singleton — don't import at module level in test files
`app/core/config.py` exposes `settings` via `__getattr__`, which lazily creates a
`Settings()` that reads `.env`. If you `from app.core.config import settings` at module
level *before* env vars are set, it picks up whatever env was active at import time.
`tests/conftest.py` sets `DATABASE_URL` and `OPENROUTER_API_KEY` as early defaults, but
if you need to override settings in a test, use `monkeypatch.setenv` *before* importing
anything from `app.core.config`.

### Alembic DB URL — ini value is dead
`alembic.ini` has a hardcoded `sqlalchemy.url`, but `alembic/env.py` overrides it with
`os.getenv("DATABASE_URL")` at runtime. Always set `DATABASE_URL` before running alembic.
The ini URL exists only as a fallback and does not match any real database.

### Disclaimer header required for all API calls
All `/api/*` routes (except `/api/v1/meta/*`, `/static`, `/health`, `/docs`, `/redoc`)
require `X-Disclaimer-Ack: v0.1.0` header. Missing header → HTTP 403. The middleware is
`app/middleware/disclaimer.py`. OPTIONS preflight requests bypass this check.

### `.corpus_sources.json` — runtime state, not tracked
User corpus source preferences are persisted to `.corpus_sources.json` in the project
root (analogous to `.secret_salt`). Both are in `.gitignore`. Don't create or modify
these files in code changes; they're runtime artifacts.

### Integration tests require live PostgreSQL + pgvector
Integration tests (`tests/integration/`) need a running database with the pgvector
extension. Run `alembic upgrade head` before them. Unit tests do not need a database.

### No CI, no pre-commit hooks
There are no GitHub Actions workflows or pre-commit config. All quality checks must
be run manually: `ruff check`, `ruff format --check`, `mypy app/`, `pytest`.

### Frontend is versioned per file
`index.html` header comment says v0.4.0. `app.js` and `style.css` say v0.3.0.
The HTML version is the authoritative frontend version.

### LLM router: single shared client via `get_shared_client()`
`app/core/router.py` exposes a single `get_shared_client()` singleton and `close_client()`.
All service modules (`reasoning.py`, `chat_reasoning.py`, `intake.py`, `case_chat.py`,
`calculation.py`) obtain the client through `get_shared_client()`. A single `close_client()`
call in the FastAPI lifespan shutdown handler closes it.

### PDF parsing: dual-fallback chain
OCR is `pdfplumber` → `PyMuPDF` → `Tesseract` (German). The OCR service is
`app/services/ocr.py`. LLM-based OCR synthesis is opt-in (`ENABLE_OCR_LLM_SYNTHESIS`
defaults to `False`).

## Design documents
`devdocs/` contains `design_document.md`, `technical_specification.md`, and
`ui_testing_guide.md`. Consult these for architectural context before making deep
changes to the pipeline, schema, or frontend.

## Directories of note

| Path | Purpose |
|---|---|
| `app/core/pipeline.py` | 9-stage SSE analysis orchestrator |
| `app/core/router.py` | OpenRouter client (inference + embeddings) |
| `app/core/config.py` | Settings singleton + app version helpers |
| `app/db/models.py` | All 13 ORM models |
| `app/db/session.py` | Async session factory (reused by tests) |
| `app/services/` | 23 service modules (reasoning, retrieval, calculation, etc.) |
| `app/middleware/` | Disclaimer + rate-limit middleware |
| `app/api/routes/` | 12 route modules |
| `static/` | Frontend: `index.html`, `app.js`, `style.css` |
| `alembic/versions/` | 6 migrations (001–006) |
| `tests/unit/` | Unit tests (no DB needed) |
| `tests/integration/` | Integration tests (DB required) |
| `scripts/` | `benchmark_analyze.py` — SSE pipeline latency measurement |

## Persistent Memory

<!-- APPEND-ONLY: Add new entries below this line. Never delete or rewrite existing entries unless correcting a documented factual error. -->
<!-- Each entry: ### YYYY-MM-DD: Topic — short summary -->
### 2026-05-13: Persistent memory system established

- Memory lives in this `AGENTS.md` file, auto-loaded by OpenCode into every session
- A `memory` skill at `~/.config/opencode/skills/memory/SKILL.md` defines the full protocol for read/write/search
- Append-only: new entries go below existing ones. Never delete or rewrite past entries
- The orchestrator has `skills: ["*"]` so the memory skill is available via the `skill` tool
- Before making any change, read this Persistent Memory section to learn what past sessions discovered
- Write to memory when: user preferences, architectural decisions, project gotchas, or patterns the user dislikes are discovered

### 2026-05-13: README comprehensively updated to match current project state

- Pipeline is now 9-stage (was documented as 7-stage): added Adversarial Review and Calculation Check
- Combined stages enabled by default: classification+decomposition (WP-006), construction+verification+generation (WP-007)
- New services: `calculation.py` (3-phase SGB II verification), `parameter_store.py` (versioned legal params), `rules_engine.py` (deterministic §11b computation)
- New utility: `tokens.py` (prompt/token budgeting)
- New model: `LegalParameter` (table 12 of 12 in DB schema)
- DB now has 12 tables (was documented as 11), migration `004_add_legal_parameter` added
- API: 18 endpoints total, including new `/corpus/health`
- Disclaimer split: `DISCLAIMER_DE.md` + `DISCLAIMER_EN.md` (single `DISCLAIMER.md` no longer exists)
- Devdocs: `roadmap.md` removed, `ui_testing_guide.md` added
- Tests: ~7100 lines across 26 files (was documented as ~4300)
- Frontend version: 0.2.0 (from index.html semantic version comment)
- Config significantly expanded: per-stage model overrides, token budget limits, retrieval mode, keyword fallback, OCR synthesis, cache settings
- OCR now supports TXT/HTML/EML in addition to PDF/JPG/PNG
- Added `scripts/benchmark_analyze.py` for SSE pipeline latency measurement
- LLM router is at `app/core/router.py` (not `app/services/openrouter_client.py` — fixed stale ref in AGENTS.md constraints)

### 2026-05-13: Runtime corpus source selection and settings page added

- New endpoints in `app/api/routes/corpus.py`: `GET /corpus/available-sources`, `GET /corpus/sources`, `PUT /corpus/sources`
- Runtime source preferences persisted to `.corpus_sources.json` (in project root, analogous to `.secret_salt`)
- `POST /corpus/update` now accepts optional `{"sources": [...]}` body for one-shot override
- `_run_corpus_update` accepts `override_sources` parameter; falls back to `get_effective_corpus_sources()` which checks `.corpus_sources.json` then `settings.CORPUS_SOURCES`
- `CORPUS_SOURCE_METADATA` dict in `app/services/corpus.py` defines all 11 source types with full_name, description, tooltip, has_scraper, checked_by_default, source URL origin
- Weisung PDF scraper scaffold added to `app/services/corpus.py`: `scrape_weisungen()`, `_find_weisung_pdf_links()`, `_scrape_weisung_pdf()`, `_split_weisung_into_paragraphs()`. Uses pdfplumber (already a dependency). Index URL: `arbeitsagentur.de/ueber-uns/veroeffentlichungen/weisungen/weisungen-nach-rechtsnorm`
- `scrape_and_chunk()` now dispatches by source_type: `"weisung"` → `scrape_weisungen()`; all others → gesetze-im-internet.de HTML parser
- Frontend: new Settings mode as third mode alongside Analyze and Chat. Toggle button in header. Dedicated settings page with:
  - Checkbox list of all 11 source types with full names, source origin badges, descriptions, and ? tooltips (title attribute)
  - Select-all checkbox with indeterminate state
  - "Auswahl speichern" (PUT) and "Corpus mit Auswahl neu laden" (POST with sources + progress polling) buttons
  - Source count display, loading/error/success states
- CSS: `.btn-secondary` style added, `.settings-*` class family for source list items, tooltips, status messages
- Source type `"weisung"` now has metadata, display name, and scraper (previously only DB-level recognition with no scraper)
- Source type `"bsg"` has metadata but `has_scraper: false` — shown as disabled in settings UI with "(noch nicht verfügbar)" badge
- All 334 tests pass (324 unit + 10 integration). Old `_SOURCE_DISPLAY_NAMES` dict in routes removed in favor of `CORPUS_SOURCE_METADATA`

### 2026-05-13: Case Chat feature implemented (replaces static results view)

- New "Case Chat" interface replaces the static `#results-section` in Analyze mode with an interactive, persistent case session
- `POST /analyze` now persists `CaseRun` + `PipelineStageLog` + `Claim` + `EvidenceBinding` on completion, includes `case_run_id` in final SSE event for auto-navigation
- 9 new API endpoints at `/api/v1/cases`: CRUD, chat (SSE), targeted re-evaluation (SSE), claim editing, adjudication, export (JSON/Markdown)
- DB: `CaseRun` gains `title`, `updated_at`, `chat_history` (JSONB), `user_edits` (JSONB). `Claim` gains `user_adjudication` (JSONB). Migration `005_add_case_chat_fields.py`
- New service: `app/services/case_chat.py` — chat grounded in pipeline output, targeted re-evaluation with downstream dependency map
- Frontend: sidebar case session list, section toolbar actions (re-run, edit, flag, confirm, copy, export), dark-theme chat, comparison overlay with diff highlighting
- Entry points: auto-navigate after fresh analysis, or select from case session list
- Version bumped: 0.2.0 → 0.3.0 in index.html, style.css, app.js

### 2026-07-10: AGENTS.md restructured — operational sections added

- Package manager is `uv` (not pip — `uv.lock` exists but is excluded from OpenCode context)
- Frontend version: all three files (index.html, app.js, style.css) at v1.0.0
- No CI, no pre-commit hooks — all quality checks manual
- Alembic `env.py` overrides `alembic.ini` DB URL with `DATABASE_URL` env var; the ini URL is dead code
- `settings` singleton in `app/core/config.py` uses lazy `__getattr__` — dangerous to import at module level before env is configured
- All `/api/*` routes require `X-Disclaimer-Ack` header (except `/api/v1/meta/*`, `/static`, `/health`, `/docs`, `/redoc`)
- `.corpus_sources.json` is runtime state in project root, analogous to `.secret_salt` — not tracked in git
- LLM router: single shared `OpenRouterClient` via `get_shared_client()`; all service modules use it
- DB now 13 tables (added `intake_session` + `case_run_area` via migration 006)
- 16 supported statute source types (added erbstg, hoefev, kschg, burlg, tvg)
- DB now 14 tables (added `intake_session` + `case_run_area` via migration 006)
- 16 supported statute source types (added erbstg, hoefev, kschg, burlg, tvg)
- devdocs/ has 3 files: design, technical spec, UI testing guide

### 2026-07-13: Documentation refreshed to match v1.0.0

- pyproject.toml version: 1.0.0. Frontend: all three files at v1.0.0. App: 0.2.0 (main.py).
- 12 API route modules, 23 service modules, 14 DB tables, 10 Alembic migrations.
- 33 test files (~11,700 lines), 696 unit test functions collected (plus integration tests hidden by missing sqlite-vec dependency).
- LLM router consolidated to single `get_shared_client()` singleton (WP-00.5).
- New services since 2026-07-10: `document_generators`, `fristen`, `inference_profiles`, `ocr_quality`, `presets`, `pseudonymization`, `regime`. New routes: `documents`, `eval_reports`, `goldset`, `ocr`.
- DISCLAIMER_DE.md at v1.1.0 with inference profiles section. DISCLAIMER_EN.md being brought to parity.
- README.md AGENTS.md counts corrected to match current implementation.
