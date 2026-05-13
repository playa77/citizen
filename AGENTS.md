# Citizen — Agent Context

## Project

Citizen is a local-first, evidence-constrained legal reasoning engine for German social law (SGB II/X). Python 3.11+, FastAPI, SQLAlchemy async, PostgreSQL + pgvector, vanilla HTML/JS/CSS frontend with SSE streaming.

**Key constraints:**
- All LLM calls go through `app/core/router.py` (fault-tolerant with fallback chains)
- API endpoints in `app/api/routes/`
- Database models in `app/db/models.py`, migrations via Alembic
- Frontend is vanilla JS — no frameworks
- Strict mypy, ruff formatting (line-length 100)
- Tests with pytest, asyncio_mode = auto

## Repository Map

Before working on any task, check if `codemap.md` exists in the project root or relevant subdirectories.

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
