# AGENTS.md

Guidance for coding agents. Authoritative sources: `DECISIONS.md` (append-only decision ledger, R1/R2/R3 tags), `CHANGELOG.md`, `.env.example` (may lag `app/core/config.py` — trust config.py).

## What this is

Local-first FastAPI service analyzing German social-law benefit notices (SGB II/X): evidence-bound LLM pipeline + deterministic engines (deadlines `services/fristen.py`, benefit math `services/rules_engine.py`) + Postgres audit storage. Vanilla-JS frontend in `static/` (3 files). Electron variant runs on SQLite.

## Commands

```bash
uv pip install -e ".[dev]"                          # setup; Python 3.11+
pytest tests/unit/                                  # no DB required
alembic upgrade head && pytest tests/integration/   # needs Postgres 16 + pgvector via DATABASE_URL
ruff check app/ && ruff format --check app/ && mypy app/   # CI order; CI checks only app/, mypy strict
python scripts/check_purpose_drift.py               # doc lint, fails CI on hits
python -m spacy download de_core_news_lg            # one-time PII model
```

- Single test: `pytest tests/unit/test_fristen.py::<name>`. pytest `asyncio_mode = "auto"` — async tests need no marker.
- Eval harness: `python -m eval.runner eval/goldsets/goldset-v0.2.0.yaml [--case GS-xxx] [--baseline <report>]` — runs the real pipeline against live DB + LLM API; exit 1 if regression gate fails. The README's `citizen-eval` command does not exist as such.
- Docker stack: `docker compose up -d --build`, then migrations inside the container (`docker compose exec citizen-app alembic upgrade head`).

## Dual-database reality (biggest trap)

- Production/Docker: PostgreSQL 16 + pgvector. Unit tests and Electron: SQLite (+ sqlite-vec). `IS_SQLITE` in `app/db/session.py` picks the code path at import time from `DATABASE_URL`.
- Vector-query changes must be mirrored in BOTH backends of `app/db/vector_backend.py` (`_cosine_distance_sqlite` / `_cosine_distance_pgvector`), including column aliasing (`"lc.x" AS lc_x`). Unit tests never exercise the pgvector path — pgvector-only regressions (D-014, D-016) surfaced only in deployment. Run integration tests for any vector-backend change.
- Alembic has TWO migration DAGs: PG chain `001→006→011_pg`, SQLite chain `007_sqlite_baseline→010→011_sqlite`. Every schema change needs a migration pair, one per branch. `alembic/env.py` auto-stamps the SQLite baseline when the URL is sqlite.

## Compliance posture (enforced, not decorative)

- `DEPLOYMENT_MODE` = `dev|self|provider` (default `dev`). In `dev`, startup refuses to run unless `CITIZEN_SYNTHETIC_DATA_ONLY=true` (`app/services/dev_guard.py`), and document uploads require header `X-Document-Tag: synthetic|goldset` → otherwise 403.
- Purpose-drift lint scans `README*.md`, `STATEMENT.md`, `COMPLIANCE*.md`, `docs/pitch*` and fails CI on authority-side phrasings ("Behörden ... prüfen/bewerten Leistungen"). Declared purpose is claimant-side self-help only (D-020) — keep all copy consistent with that.
- Corpus/mutating endpoints require `X-Disclaimer-Ack` matching `DISCLAIMER_VERSION` (`app/middleware/disclaimer.py`).

## Conventions

- Source files carry a `Semantic Version:` comment header — bump it when meaningfully changing a file.
- Log decisions in `DECISIONS.md` at decision time (not batched); append change sets to `CHANGELOG.md`.
- Settings: pydantic-settings in `app/core/config.py`; env loading via `.env`. LLM routing through versioned profiles in `config/inference_profiles.yaml` (`INFERENCE_PROFILE`, default `eu-avv`); egress guard blocks non-approved endpoints.
- Timeout chain must stay ordered (D-017): nginx proxy timeout > `PIPELINE_TIMEOUT_SEC` > sum of per-stage timeouts. Per-call hard limits use `asyncio.wait_for` in `app/core/router.py` because httpx read timeouts never fire on streaming responses.
- `tests/conftest.py` sets `DATABASE_URL`, dummy API key, disclaimer version, and dev-posture flags **before** imports. Any new setting consumed at import time needs a conftest default or collection fails.
