# Citizen — Project AGENTS.md

<!-- Version: 1.0.0 | 2026-07-19 -->

## Architecture

- **Backend:** Python 3.11+ FastAPI with Uvicorn (SSE streaming), async SQLAlchemy 2.0
- **Frontend:** Vanilla HTML/JS/CSS in `static/` (no framework) — served as static files from the FastAPI app
- **Desktop wrapper:** Electron app at `electron/` spawns the Python backend as a subprocess and wraps it in a BrowserWindow
- **Database:** Dual backend — PostgreSQL 16+pgvector (server/prod) **or** SQLite+sqlite-vec (desktop/CI testing)
- **Inference:** LLM calls via OpenRouter API, governed by versioned inference profiles at `config/inference_profiles.yaml`
- **Dev docs:** `devdocs/ARCHITECTURE-ACTUAL.md` (auto-generated reference), `devdocs/design_v1.0.0.md` (design spec), `devdocs/goldset-v0.1.0.yaml` (eval goldset spec)

## Setup & Environment

- **Package manager is `uv`** — never use pip directly. Dependencies: `pyproject.toml`. Lock: `uv.lock`.
- Install: `uv sync` or `uv pip install -e ".[dev]"` inside a venv
- **Spacy model required:** `python -m spacy download de_core_news_lg` (PII NER for pseudonymization)
- **OCR deps:** Tesseract + `tesseract-ocr-deu` language pack must be installed on the host
- Copy `.env.example` → `.env` and set `OPENROUTER_API_KEY` (required, won't start without it)
- `.secret_salt` is auto-generated on first boot, persisted, and gitignored

## Developer Commands

```bash
# Lint + format check
ruff check app/ tests/
ruff format --check app/ tests/

# Type check (strict mode, line-length 100)
mypy app/

# Unit tests — no database needed
pytest tests/unit/ -v

# Single test file/function
pytest tests/unit/test_fristen.py -v
pytest tests/unit/test_fristen.py::test_widerspruchsfrist -v

# Integration tests — requires running PostgreSQL with alembic applied
alembic upgrade heads              # if on SQLite
alembic upgrade 006_add_intake_and_legal_areas  # if on PG
pytest tests/integration/ -v

# Eval against goldset
citizen-eval run --goldset v0.2.0 --profile eu-avv \
  --accept-disclaimer v1.1.0 --report eval/reports/
```

## Alembic Migration Gotcha

**`alembic upgrade head` does NOT work.** There are two independent migration branches:
- PostgreSQL branch: 001→006
- SQLite baseline branch: 007→010

`alembic upgrade head` fails with "Multiple head revisions are present." Use dialect-specific targets:

```bash
# PostgreSQL: target revision 006
alembic upgrade 006_add_intake_and_legal_areas

# SQLite: use the "heads" target (covers 007→010)
alembic upgrade heads
```

The app's `lifespan` handler in `app/main.py` already does this automatically at startup, but you need it for manual migration runs. See `DECISIONS.md` D-004 for rationale.

**Never create a migration that adds PostgreSQL columns by importing from an existing migration's `down_revision`** on the PG branch — it'll break the SQLite upgrade path. The pending D-007 migration (011) should bridge both branches cleanly.

## Dual Database: PostgreSQL vs SQLite

Code detects dialect at runtime: `IS_SQLITE` flag in `app/db/session.py`.

- **Server/prod/Docker:** PostgreSQL 16 with `pgvector` extension. Full async support via `asyncpg`. `DB_POOL_SIZE` env var controls pool.
- **Desktop/testing:** SQLite with `sqlite-vec` for vector search. `aiosqlite` async driver. WAL mode enabled automatically.
- Unit tests run against `sqlite+aiosqlite:///:memory:` (set in `tests/conftest.py`).
- The `conftest.py` also sets a dummy `OPENROUTER_API_KEY` so settings don't fail at import time.

## Electron Desktop

- Backend port: **8512** (not 8000), bound to `127.0.0.1`
- Dev mode: Electron spawns `uv run python -m app.main --port 8512 --data-dir <userData>/data`
- The `--data-dir` flag overrides `DATABASE_URL` to use SQLite at that path
- Production mode: expects a PyInstaller binary at `resources/backend/citizen-backend` (built separately)
- Preload script (`electron/src/preload.ts`) exposes `window.electronAPI` via contextBridge — IPC for file dialogs, menu actions, API key management
- `electron-builder` packages for Linux: AppImage and .deb (see `electron/package.json`)
- The AppImage sandbox fix is in `scripts/apprun.sh` — wired at packaging time, never edited post-build

## First-Run / Disclaimer

- The `DisclaimerMiddleware` in `app/middleware/disclaimer.py` blocks API access until the user acknowledges the legal disclaimer
- For corpus updates and analysis, pass header: `X-Disclaimer-Ack: v1.1.0`
- In the browser UI, the disclaimer is enforced by a client-side gate before any analysis starts
- Current disclaimer version: check `GET /api/v1/meta/disclaimer/version`

## Key Services (app/services/)

- `fristen.py` — Deterministic deadline engine (LLM-free, unit-tested). Handles Bekanntgabefiktion, §84 SGG, Werktag-Rollover, Feiertagskalender, etc.
- `rules_engine.py` — Deterministic SGB II §11b calculation cascade (hardcoded fallback logic)
- `parameter_store.py` — Versioned legal parameters with Geltungszeitraum; cache populated at startup in `lifespan`
- `pseudonymization.py` — PII detection and replacement before external inference; reinjection in final documents
- `inference_profiles.py` — Loads and validates `config/inference_profiles.yaml`; active profile validated at startup
- `verification.py` — String-match verification of LLM citations against source chunks
- `document_generators.py` — Produces Widerspruch, §44, §25 action documents
- `regime.py` — Intertemporal law selection per Leistungszeitraum (pre/post 2026-07-01 reform)

## Config Files

- `.env.example` — all environment variables with defaults; copy to `.env`
- `config/inference_profiles.yaml` — inference profile definitions (endpoints, AVV status, model per pipeline stage, egress allowlist)
- `.opencodeignore` — blocks OpenCode from reading build artifacts, lockfiles, venvs, DB files, uploads, logs

## Testing

- 30 unit test files in `tests/unit/`, 5 integration test files in `tests/integration/`
- `pytest.ini_options.asyncio_mode = "auto"` — all async tests work without `@pytest.mark.asyncio`
- `ruff` config: line-length 100, target py311, select = E,F,W,I,UP,B,C4,SIM,RUF
- `mypy` config: strict mode, `python_version = "3.11"`, `ignore_missing_imports = true`
- Test data (sample PDFs, images, etc.) lives in `tests/test_data/`
- `tests/generate_test_files.py` creates synthetic test documents

## Production Deployment

- See `DEPLOYMENT.md` — target: VPS 37.60.240.152, domain workbench.gronowski.cc
- Two compose files: `docker-compose.yml` (base) + `docker-compose.override.yml` (production overrides — DB credentials, port 8000→8001, restart policy)
- Docker HEALTHCHECK calls `/health` every 15s
- Alpine startup deadlock with `asyncio.to_thread` + `alembic_command.upgrade` → resolved by using `asyncio.create_subprocess_exec` instead (`DECISIONS.md` D-006)
- Auto-migration runs at container startup; no manual `alembic upgrade` needed in production

## Conventions

- **Add-only codebase:** Never remove existing functionality or endpoints without explicit permission
- **Decision logging:** Non-trivial decisions go in `DECISIONS.md` with reversibility tag (R1/R2/R3). See existing entries for format.
- **Changelog:** All changes appended to `CHANGELOG.md`
- **German-language UI:** The frontend is entirely in German; legal domain terms must remain in German
- **Version headers:** Files use Semantic Version + date at the top (see existing code for pattern)
- **ISO 8601 logging:** All log timestamps in `YYYY-MM-DDTHH:MM:SS` format
