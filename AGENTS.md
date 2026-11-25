# Repository guidance

## Purpose and sources

Citizen is an MIT-licensed Python/FastAPI backend for people preparing their
own German legal matters and advice appointments. It provides evidence-bound
analysis, deterministic checks, document drafts and appointment dossiers.
It is not a lawyer-facing product. The consumer UI belongs in the separate
`playa77/citizen-gui` repository; do not add a frontend here. The backend also
provides a local, read-only stdio MCP interface (`python -m app.mcp`).

## First implementation task — blocking

Complete [TODO.md](TODO.md), step 1, before any other implementation work,
including further legal-area modules.
[D-069](docs/decisions/D-069-module-selection-and-session-restore.md)
supersedes the former Sozialrecht default: all modules are peers and none is
preselected or automatically loaded. The GUI/desktop presents all modules for
loading selection, and offers **Restore last session** when a saved session
exists. Restoration must be explicit and must not establish a new-session
default. Backend fallback removal and GUI/session support are part of this
blocking task; they remain unimplemented until its checklist is verified.

## Project sources

Read the affected code, tests and specifications before editing. Start with:

- `pyproject.toml`: package version, dependencies and tool configuration.
- `app/core/config.py`: authoritative settings; `.env.example` is the setup
  template. `config/inference_profiles.yaml` defines inference profiles.
- `API_DOCUMENTATION.md`: HTTP/SSE contracts; `DEPLOYMENT.md`: deployment.
- `docs/MODULE-AUTHORING.md` and `docs/module-catalog.md`: module conventions
  and scope. Runtime manifests and schemas establish what is implemented.
- `DISCLAIMER_DE.md` and `DISCLAIMER_EN.md`: canonical purpose and notices.
- `.github/workflows/ci.yml`: actual CI commands and supported Python matrix.

The project has historically recorded architecture in `ARCHITECTURE.md`,
append-only decisions in `DECISIONS.md` (`D-XXX`, reversibility tag, date),
release notes in `CHANGELOG.md`, and plans in `docs/roadmap-v3.0.0.md`.
Some of these documents may be deleted in the working tree. Inspect Git
state first; use `git show HEAD:<path>` for historical context where needed,
and do not restore deleted documents as an incidental cleanup. README status
tables can lag the code; verify implementation claims against source/tests.

## Code map and architectural constraints

- `app/main.py`: application startup, middleware and route registration.
  `app/api/routes/`: versioned HTTP endpoints under `/api/v1`.
- `app/core/`: pipeline orchestration, LLM routing and settings.
  `app/services/`: retrieval, OCR, pseudonymization, evidence verification,
  document generation and other shared services.
- `app/modules/`: registry, manifests, SDK, validation and runtime module
  resolution. `modules/<id>/`: legal-area knowledge, versioned parameters,
  prompts, deadline specs, calculators, copy, goldsets and changelogs.
  `sozialrecht` is one peer module; other installed modules include
  experimental stubs. Derive area ownership, order and enablement from module
  data, and session scope from the user's explicit choice or session restore.
  Deployment enablement does not select or load modules for the user.
- `app/fristen/`: deterministic deadline engine; `app/dossier/`: dossier
  builders and schemas; `app/plain/`: deterministic plain-language rendering.
- `app/db/` and `alembic/`: PostgreSQL persistence and migrations.
  `app/citations/`, `app/updates/`, `app/mcp/`: citation verification, signed
  updates and the local MCP interface. `eval/` and `scripts/`: evaluation
  gates and maintenance commands.

Preserve these established boundaries:

- Keep legal-area rules in modules, preferably as data. Module Python code
  may import from `app.modules.sdk`, not other `app.*` internals; the module
  import lint enforces this. Do not add area-specific logic to core services.
- Calculate deadlines and amounts only with deterministic engines and
  versioned parameters, never from LLM assertions. Keep evidence bindings
  and human confirmation requirements; action documents remain drafts with
  `[BITTE PRÜFEN]` placeholders for unconfirmed material.
- Keep `/api/v1` changes additive (D-039). Update `API_DOCUMENTATION.md` in
  the same change; preserve SSE event contracts and error behavior.
- PostgreSQL 16 plus pgvector is the only database, including tests (D-024).
  Do not reintroduce SQLite or a second migration branch. Extend the single
  Alembic chain; ORM embeddings use `Vector(1536)`.
- Preserve pseudonymization, inference-profile egress restrictions and
  hard per-call timeouts. The timeout budget must keep the reverse-proxy
  timeout above the pipeline budget, and the pipeline budget above its
  sequential stage budgets. Streaming calls need hard wall-clock limits;
  an httpx read timeout alone is insufficient.
- First-party code and modules remain MIT; do not embed GPL/AGPL components
  (D-041). Such integration requires the established separate-service boundary.

## Setup and routine commands

Use Python 3.11+; CI runs 3.11 and 3.12. Reuse the existing project virtual
environment. If none exists, create one with `uv venv .venv`, activate it
with `source .venv/bin/activate`, then install with:

```bash
uv pip install -e ".[dev]"
```

OCR requires Tesseract and its German language data. Pseudonymization uses
spaCy's `de_core_news_lg` model. Provision these only when required and
authorized; do not modify system Python. Configure local settings using
`.env.example`; never print or commit `.env`, `.secret_salt` or credentials.

From the repository root, with the environment active:

```bash
ruff check app/
ruff format --check app/
mypy app/
python scripts/check_purpose_drift.py
pytest tests/unit/
pytest tests/integration/
```

- CI checks `app/` for lint, format and strict typing (100-character Ruff
  line length); its Python 3.12 job adds `--python-version 3.12` to mypy.
- Both pytest suites load `tests/conftest.py`, which starts and migrates a
  `pgvector/pgvector:pg16` testcontainer when no PostgreSQL `DATABASE_URL` is
  supplied. Docker and the dev extras are therefore required even for most
  unit-test selections. An explicit `DATABASE_URL` must identify a disposable
  test database; run `alembic upgrade head` against that database first.
- Use focused checks such as `pytest tests/unit/test_fristen.py` during
  development. `asyncio_mode = "auto"`; async tests need no explicit marker.
  Conftest establishes test settings before application imports and preloads
  module code as `citizen_modules.<id>.<file>`. Add defaults there when new
  required settings would otherwise break collection.
- API changes need `tests/unit/test_api_documentation.py` and relevant
  integration/SSE tests. Module changes need the validator and affected
  module, versioning and deterministic regression tests.
- To run the backend locally, use `uvicorn app.main:app --reload` with a
  configured development environment. `docker compose up -d --build` is the
  container alternative and requires `.env`; see `DEPLOYMENT.md` for operations.

Offline module/content checks (no database, inference or API key required):

```bash
python -m scripts.validate_module --all
python -m eval.dossier_eval --module sozialrecht
python -m eval.plain_eval --module sozialrecht
```

`python -m eval.runner --module sozialrecht` runs the real pipeline against
a database and live inference; it is not an offline smoke test. Its
`--rescore <outputs.json>` mode reuses saved outputs without LLM or DB calls.
Live inference requires a separate operator-provided test key, an explicit
child-environment allowlist, agreed call/concurrency/time/cost bounds and a
working termination mechanism. Never reuse developer-agent credentials.
Corpus ingestion and `scripts.corpus_watch` can also perform network calls
and embeddings; inspect their mode before running them.

## Privacy, notices and versioning

- In `DEPLOYMENT_MODE=dev`, startup requires
  `CITIZEN_SYNTHETIC_DATA_ONLY=true`. Document ingestion requires
  `X-Document-Tag: synthetic` or `goldset`. Use synthetic fixtures, not real
  notices, and preserve the dev guards rather than disabling them for tests.
- Protected requests require `X-Disclaimer-Ack` matching `DISCLAIMER_VERSION`.
  Every AI-text response must carry disclosure/provenance from
  `build_disclosure_and_provenance`, with the request/case area keys so the
  module versions and parameter sets are correct.
- Keep copy oriented toward people handling their own matters. Run the
  purpose-drift check for affected public documentation or module copy.
  Plain-language output comes from versioned static copy and whitelisted
  deterministic placeholders. Preserve `draft` review status until human
  review is actually completed.
- Module changes need an appropriate manifest SemVer bump and a matching
  `modules/<id>/CHANGELOG.md` entry. Corrections of published wrong values or
  copy require errata; follow `docs/MODULE-AUTHORING.md` for the version rules.
- Changing module disclaimer addenda or adding modules requires updating
  both disclaimer documents and their version, plus `DISCLAIMER_VERSION`.
  Disclaimer/disclosure changes also require re-pinning and checking
  `app/plain/core/*.yaml`. Prompt text changes bump `PROMPT_SET_VERSION` in
  `app/services/prompts.py`; update pinned prompt/golden expectations
  deliberately and evaluate changed behavior rather than blindly accepting it.

## Change discipline and handoff

Keep changes scoped and preserve unrelated edits/deletions. Record material
architectural decisions using the project's decision-ledger convention with
context, rationale, consequences, status and genuine alternatives. Follow
the existing release/changelog workflow when those records are present;
resolve deliberately removed records before recreating them.

Run the cheapest meaningful checks for the affected contracts, then the
applicable CI gates. Documentation-only changes do not require starting a
database or live inference. Report actual checks and limitations. Before
handoff, inspect Git status and report the branch, relevant changed files,
and commit/push status. Commit, push or publish only when authorized.
