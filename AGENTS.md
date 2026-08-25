# AGENTS.md

Guidance for coding agents. Authoritative sources: `DECISIONS.md` (append-only decision ledger, R1/R2/R3 tags), `CHANGELOG.md`, `app/core/config.py` (`.env.example` mirrors it as of 2026-08-25; config.py stays authoritative). Deploy flow lives in `DEPLOYMENT.md`; dev-instance ops rules in `devdocs/DEV-INSTANCE.md`.

## What this is

API-only FastAPI service analyzing German social-law benefit notices (SGB II/X): evidence-bound LLM pipeline + deterministic engines (deadlines `services/fristen.py`, benefit math `services/rules_engine.py`) + Postgres audit storage. The REST API under `/api/v1` is the only external interface; contract documented in `API_DOCUMENTATION.md` (D-025). No web UI, no GUI client in this repo.

## Commands

```bash
uv pip install -e ".[dev]"                          # setup; Python 3.11+ (.venv at repo root), Docker required for tests
pytest tests/unit/                                  # auto-starts a pgvector testcontainer unless DATABASE_URL is set
alembic upgrade head && pytest tests/integration/   # own DATABASE_URL needs manual migration; the auto-container migrates itself
ruff check app/ && ruff format --check app/ && mypy app/   # CI order; CI checks only app/, mypy strict, Python 3.11 + 3.12
python scripts/check_purpose_drift.py               # doc lint, fails CI on hits
```

System deps for OCR runtime/tests: `tesseract-ocr` + `tesseract-ocr-deu`. One-time model: `python -m spacy download de_core_news_lg`.

- Tests are PostgreSQL-only (D-024): unit tests run production SQL via testcontainers; a pre-set `DATABASE_URL` overrides the container. SQLite URLs are rejected.
- `API_DOCUMENTATION.md` is guarded: `tests/unit/test_api_documentation.py` fails when routes drift from the doc.
- Single test: `pytest tests/unit/test_fristen.py::<name>`. pytest `asyncio_mode = "auto"` — async tests need no marker.
- Eval harness: `python -m eval.runner eval/goldsets/goldset-v0.2.0.yaml [--case GS-xxx] [--baseline <report>] [--save]` — runs the real pipeline against live DB + LLM API; exit 1 if regression gate fails; `--save` writes versioned reports to `eval/results/`. There is no `citizen-eval` command despite older docs saying so.
- Maintenance scripts: `scripts/seed_legal_parameters.py` (legal_parameter seeding), `scripts/benchmark_analyze.py --base-url <url>` (pipeline timings against a *running* instance).
- Docker stack: `docker compose up -d --build` **requires a `.env` file** (`env_file:` fails without one), then migrations inside the container (`docker compose exec citizen-app alembic upgrade head`).

## Database: PostgreSQL-only (resolved D-024)

One backend everywhere — server, Docker, CI, and all tests: PostgreSQL 16 + pgvector. The former SQLite/sqlite-vec dual path (`IS_SQLITE` branches, dual migration DAGs, raw-SQL `::vector` workarounds) was removed with its last consumer (the Electron client); do not reintroduce SQLite anywhere, including tests. Single linear migration DAG: `001 → … → 006 → 011_pg → 012`; `012_pg_collapse_sqlite_branch` carries the schema content of the deleted SQLite-only migrations 008–010 and is idempotent. New migrations extend this single chain; keep the ORM column types authoritative (`ChunkEmbedding.embedding` is `pgvector.sqlalchemy.Vector(1536)`).

## Compliance posture (enforced, not decorative)

- `DEPLOYMENT_MODE` = `dev|self|provider` (default `dev`). In `dev`, startup refuses to run unless `CITIZEN_SYNTHETIC_DATA_ONLY=true` (`app/services/dev_guard.py`), and document uploads require header `X-Document-Tag: synthetic|goldset` → otherwise 403.
- Purpose-drift lint (`scripts/check_purpose_drift.py`) scans its configured glob targets — currently `README*.md`, `STATEMENT.md`, `COMPLIANCE*.md`, `docs/pitch*`; the latter two no longer exist since the disclaimer merge, so the effective scan set is README*.md + docs/pitch*. It fails CI on authority-side phrasings ("Behörden ... prüfen/bewerten Leistungen"). Declared purpose is claimant-side self-help only (D-020) — keep all copy consistent with that.
- Legal/compliance copy lives in the merged `DISCLAIMER_DE.md` / `DISCLAIMER_EN.md` (v2.0.0: statement + legal notice + AI Act classification in one document per language). The former `STATEMENT.md`, `COMPLIANCE.md`, `COMPLIANCE-EN.md` are gone — do not re-create them; link to the disclaimer sections instead. Note: `DISCLAIMER_*.md` is NOT in the lint's default target list (coverage gap logged in DECISIONS.md).
- Corpus/mutating endpoints require `X-Disclaimer-Ack` matching `DISCLAIMER_VERSION` (`app/middleware/disclaimer.py`).

## Conventions

- Source files carry a `Semantic Version:` comment header — bump it when meaningfully changing a file.
- Log decisions in `DECISIONS.md` at decision time (not batched); append change sets to `CHANGELOG.md`.
- Settings: pydantic-settings in `app/core/config.py`; env loading via `.env`. LLM routing through versioned profiles in `config/inference_profiles.yaml` (`INFERENCE_PROFILE`, default `eu-avv`); egress guard blocks non-approved endpoints.
- Timeout chain must stay ordered (D-017): nginx proxy timeout > `PIPELINE_TIMEOUT_SEC` > sum of per-stage timeouts. Per-call hard limits use `asyncio.wait_for` in `app/core/router.py` because httpx read timeouts never fire on streaming responses.
- `tests/conftest.py` sets `DATABASE_URL`, dummy API key, disclaimer version, and dev-posture flags **before** imports. Any new setting consumed at import time needs a conftest default or collection fails.
