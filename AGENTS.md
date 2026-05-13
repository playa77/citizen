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
