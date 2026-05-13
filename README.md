# Citizen — German Social Law Reasoning & Drafting System

## THIS SOFTWARE IS IN A PROTOTYPE STAGE. NOT FOR PRODUCTIVE USE. USE AT YOUR OWN RISK!

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115.0-009688.svg)](https://fastapi.tiangolo.com)

Citizen is a local-first, evidence-constrained legal reasoning engine designed to help individuals navigate German social bureaucracy (e.g., Jobcenter, Sozialamt). It processes scanned administrative correspondence, cross-references demands against current statutes (SGB II/X) and case law, performs deterministic benefits calculations, and generates a structured, evidence-backed legal assessment.

## Core Features

* **Local-First OCR Pipeline:** Fully local document ingestion (PDF/JPG/PNG/TXT/HTML/EML) up to 25 MB. Uses a deterministic fallback chain (`pdfplumber` → `PyMuPDF` → `Tesseract`) with dual-pass image preprocessing (conversion to 300 dpi JPG, contrast enhancement, optional binarization). Optional LLM synthesis for reconciling dual-OCR results.
* **Hierarchical Legal Corpus:** Automated scraping of German legal texts from gesetze-im-internet.de and Fachliche Weisungen PDFs from arbeitsagentur.de, chunked at four granularity levels (Statute → § → Absatz → Satz) to preserve exact legal boundaries for precise citation. Includes 11 source types (SGB I/II/III/IX/X/XII, BGB, VwVfG, SGG, Fachliche Weisungen, BSG-Rechtsprechung) with runtime-selectable sources via the settings page. Sensible defaults: SGB II, SGB X, SGB I, Weisungen checked by default.
* **9-Stage Reasoning Pipeline:** A deterministic orchestrator enforcing a strict, sequential analysis flow with optimizations: Normalization → Classification+Decomposition (combined) → Retrieval (pgvector + keyword fallback) → Construction+Verification+Generation (combined) → Adversarial Review → Calculation Check. Each stage is streamed in real time via Server-Sent Events (SSE), with optional token-by-token output streaming.
* **Adversarial Legal Review:** Multi-perspective review by a "Rechtsprüfungsrat" — evaluates claims from defense, authority, and judicial perspectives to surface hidden weaknesses or counterarguments.
* **Deterministic SGB II Calculation Engine:** Three-phase numerical verification for benefits calculations (Regelbedarf, income offsets, Freibeträge, KdU arithmetic). LLM extracts structured monetary values → deterministic rules engine applies § 11b SGB II tiers and lookup tables → LLM explains findings. Catches arithmetic errors in official Bescheide.
* **Evidence-Bound Output:** Every factual assertion and legal interpretation is explicitly bound to retrieved legal sources through `pgvector` similarity search, with confidence scoring and direct quote excerpts stored in the database.
* **Deterministic LLM Routing:** Fault-tolerant OpenRouter client with an automated fallback chain (`deepseek/deepseek-v4-flash` → `deepseek/deepseek-v4-flash` → `/openrouter/free`), configurable via environment variables. Supports per-stage model overrides (triage, final, calculation).
* **Audit Trail:** Full pipeline execution auditing — every case run, stage log, claim, and evidence binding is persisted to PostgreSQL for traceability and compliance.
* **Zero-Friction Compliance:** GDPR-compliant audit logging with automatically generated, persistent cryptographic salts on first boot. No manual security configuration required.
* **Multi-Turn Conversational Reasoning:** Iterative chat interface for discussing uploaded documents across multiple turns. First message triggers the full pipeline; subsequent messages use focused RAG + conversation history for grounded responses. Conversations and documents persist across sessions.
* **Embedding Cache:** SHA-256 keyed cache for LLM embeddings and triage results with configurable TTL, reducing redundant API calls.
* **Token Budgeting:** Configurable character limits for LLM prompts (`MAX_TRIAGE_INPUT_CHARS`, `MAX_FINAL_INPUT_CHARS`, `MAX_CHUNK_CONTEXT_CHARS`, `MAX_CHUNKS_FOR_FINAL`) prevent accidental giant prompts.
* **Browser-Based UI:** Vanilla HTML/CSS/JS frontend with disclaimer acceptance, drag-and-drop document upload, dedicated settings page for corpus source selection (11 source types with tooltips and sensible defaults), real-time pipeline progress visualization, structured result display, and a dedicated chat mode with conversation sidebar.

## Architecture

The system is built on a modern, asynchronous Python stack:

* **Backend:** FastAPI, Uvicorn
* **Database:** PostgreSQL 16 with `pgvector` extension for vector similarity search, plus `tsvector` for keyword fallback retrieval
* **ORM & Migrations:** SQLAlchemy 2.0 (asyncio), Alembic
* **Frontend:** Vanilla HTML/JS/CSS (Server-Sent Events for streaming)
* **Tooling:** ruff (formatting & linting), mypy (strict type checking), pytest (unit & integration tests with coverage)

## Prerequisites

Before you begin, install these dependencies on your system:

### Required for local development

| Dependency | Version | Install (Ubuntu/Debian) |
|---|---|---|
| Python | 3.11+ | `sudo apt install python3.11 python3.11-venv` |
| Tesseract OCR | 5.x | `sudo apt install tesseract-ocr libtesseract-dev tesseract-ocr-deu` |
| PostgreSQL | 16 | `sudo apt install postgresql-16` |
| pgvector extension | 0.7.x | `sudo apt install postgresql-16-pgvector` |
| OpenRouter API key | — | Sign up at [openrouter.ai](https://openrouter.ai) |

### Required for Docker-only deployment

* [Docker](https://docs.docker.com/engine/install/) & [Docker Compose](https://docs.docker.com/compose/install/)
* OpenRouter API key

---

## Quickstart: Run with Docker Compose

The fastest way to get Citizen running. Provisions the FastAPI app and a PostgreSQL 16 + pgvector database in two containers.

```bash
# 1. Clone the repository
git clone https://github.com/your-org/citizen.git
cd citizen

# 2. Create your environment file
cp .env.example .env

# 3. Edit .env and insert your OpenRouter API key
#    Open .env in any editor and set:
#    OPENROUTER_API_KEY=sk-or-v1-...

# 4. Start the stack (builds the multi-stage image + starts PostgreSQL)
docker compose up -d --build

# 5. Wait for the database health check to pass, then run migrations
docker compose exec -it citizen-app alembic upgrade head

# 6. Open the application
#    http://localhost:8000
```

The app is now running. Interactive API docs are at:

* **Swagger UI:** [http://localhost:8000/docs](http://localhost:8000/docs)
* **ReDoc:** [http://localhost:8000/redoc](http://localhost:8000/redoc)

To stop everything:

```bash
docker compose down
```

---

## Local Development Setup

For active development, run the app directly on your machine while the database runs in Docker.

### Step 1 — Start the database

```bash
# From the project root, start PostgreSQL + pgvector in Docker
docker compose up -d db

# Verify the database is accepting connections
docker compose ps
# Look for: db   running (healthy)
```

### Step 2 — Set up the Python environment

```bash
# Create a virtual environment (Python 3.11+)
python3.11 -m venv .venv
source .venv/bin/activate

# Install the project and all dev dependencies in editable mode
pip install -e ".[dev]"

# Alternatively, if you use uv (uv.lock provided):
# uv sync --all-extras
```

### Step 3 — Configure environment variables

```bash
# Copy the example environment file
cp .env.example .env

# Edit .env and set:
#   DATABASE_URL=postgresql+asyncpg://testuser:testpassword@localhost:5432/testdb
#   OPENROUTER_API_KEY=sk-or-v1-...
#
# The DATABASE_URL above matches the docker-compose.yml defaults.
```

### Step 4 — Run database migrations

```bash
alembic upgrade head
```

Verify the schema was created:

```bash
psql -h localhost -U testuser -d testdb -c "\dt"
# Should list 12 tables: cache_entry, case_run, chunk_embedding, claim,
#   conversation, conversation_document, conversation_message,
#   evidence_binding, legal_chunk, legal_parameter, legal_source, pipeline_stage_log
```

### Step 5 — Start the development server

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Open [http://localhost:8000](http://localhost:8000) in your browser.

---

## Running Tests

The project includes an extensive test suite (~7,100 lines) with unit and integration tests, plus benchmarking support.

### Unit tests (no database required)

These tests use mocks and stubs — they run anywhere, no connection needed:

```bash
# Run all unit tests
pytest tests/unit/ -v

# Run a specific test file
pytest tests/unit/test_middleware.py -v

# Run with coverage report
pytest tests/unit/ -v --cov=app --cov-report=term-missing
```

Unit test files:

| File | Covers |
|---|---|
| `test_alembic_config.py` | Alembic migration configuration validation |
| `test_calculation.py` | Benefits calculation extraction, rules engine, explanation |
| `test_chunker.py` | Legal text hierarchical chunking |
| `test_config.py` | Settings validation and salt generation |
| `test_corpus_endpoint.py` | Corpus API route logic |
| `test_db/test_models.py` | ORM model constraints and relationships (12 tables) |
| `test_middleware.py` | Disclaimer and rate-limiting middleware |
| `test_ocr.py` | 3-tier OCR fallback pipeline |
| `test_pdf.py` | PDF extraction utilities |
| `test_pipeline.py` | 9-stage pipeline orchestrator |
| `test_reasoning.py` | LLM reasoning service (triage, combined stages, adversarial review) |
| `test_router.py` | OpenRouter client and fallback chain |
| `test_rules_engine.py` | Deterministic SGB II calculation rules |
| `test_session.py` | Async database session factory |
| `test_verification.py` | Deterministic claim-against-chunk verification |

### Integration tests (requires a running database)

These tests exercise the full pipeline against a live PostgreSQL instance:

```bash
# 1. Make sure the database is running
docker compose up -d db
# Wait for the health check to pass: docker compose ps

# 2. Run migrations (if you haven't already)
alembic upgrade head

# 3. Run all integration tests
pytest tests/integration/ -v

# 4. Run a specific test
pytest tests/integration/test_pipeline.py::TestFullPipelineExecution::test_full_pipeline_execution -v
```

Integration test files:

| File | Covers |
|---|---|
| `test_api_routes.py` | Full API endpoint round-trips |
| `test_corpus.py` | Corpus scraping, chunking, and embedding |
| `test_pipeline.py` | End-to-end pipeline with live DB |
| `test_retrieval.py` | pgvector similarity search |

### All tests at once

```bash
# Database must be running and migrated
alembic upgrade head
pytest -v
```

### Code quality

```bash
# Formatting & linting
ruff check app/ tests/
ruff format --check app/ tests/

# Type checking (strict mode)
mypy app/

# Benchmarking
pytest --benchmark-only tests/

# SSE pipeline benchmark (requires running server)
python scripts/benchmark_analyze.py
```

---

## API Endpoints

| Group | Method | Path | Description |
|---|---|---|---|
| **ingest** | `POST` | `/api/v1/ingest` | Upload and OCR a document (PDF/JPG/PNG/TXT/HTML/EML) |
| **analyze** | `POST` | `/api/v1/analyze` | Execute the full 9-stage pipeline on raw text, streaming SSE |
| **conversations** | `POST` | `/api/v1/conversations` | Create a conversation (optionally with initial document) |
| **conversations** | `GET` | `/api/v1/conversations` | List all conversations |
| **conversations** | `GET` | `/api/v1/conversations/{id}` | Get a conversation with messages and documents |
| **conversations** | `DELETE` | `/api/v1/conversations/{id}` | Delete a conversation and all associated data |
| **conversations** | `POST` | `/api/v1/conversations/{id}/messages` | Send a message, streaming SSE response |
| **conversations** | `POST` | `/api/v1/conversations/{id}/documents` | Attach a document to a conversation |
| **conversations** | `GET` | `/api/v1/conversations/{id}/documents` | List documents attached to a conversation |
| **conversations** | `DELETE` | `/api/v1/conversations/{id}/documents/{doc_id}` | Remove a document from a conversation |
| **corpus** | `POST` | `/api/v1/corpus/update` | Trigger legal corpus scrape & embedding (background: accepts optional `{"sources": [...]}` body) |
| **corpus** | `GET` | `/api/v1/corpus/status/{job_id}` | Check corpus update progress with substage tracking |
| **corpus** | `GET` | `/api/v1/corpus/health` | Corpus health check (chunk/source counts, warnings) |
| **corpus** | `GET` | `/api/v1/corpus/available-sources` | List all 11 source types with names, descriptions, tooltips, scraper status |
| **corpus** | `GET` | `/api/v1/corpus/sources` | Get current runtime source selection |
| **corpus** | `PUT` | `/api/v1/corpus/sources` | Persist source selection to disk (survives restarts) |
| **meta** | `GET` | `/api/v1/meta/disclaimer/version` | Current disclaimer version |
| **meta** | `GET` | `/api/v1/meta/disclaimer/text` | Full disclaimer text (German, HTML) |
| **meta** | `GET` | `/api/v1/meta/version` | API and disclaimer version info |
| **health** | `GET` | `/health` | Liveness probe |

---

## Directory Structure

```
citizen/
├── alembic/                          # Database migrations
│   ├── versions/
│   │   ├── 001_init_schema.py        # Initial schema (7 tables)
│   │   ├── 002_add_cache_entry.py    # Cache entry table
│   │   ├── 003_add_conversations.py  # Conversation, message, document tables
│   │   └── 004_add_legal_parameter.py # Legal parameter table (versioned SGB II values)
│   ├── env.py
│   └── script.py.mako
├── app/                              # Application source
│   ├── api/
│   │   └── routes/
│   │       ├── analyze.py            # POST /analyze (SSE pipeline streaming)
│   │       ├── conversations.py      # Conversation CRUD, chat messages (SSE), documents
│   │       ├── corpus.py             # POST /corpus/update, GET /corpus/status, /corpus/health, /corpus/available-sources, /corpus/sources
│   │       ├── ingest.py             # POST /ingest (document upload & OCR)
│   │       └── meta.py               # GET /meta/* (disclaimer, version)
│   ├── core/
│   │   ├── config.py                 # Settings & validation (Pydantic)
│   │   ├── pipeline.py               # 9-stage orchestrator (SSE streaming)
│   │   └── router.py                 # LLM router + fallback chain
│   ├── db/
│   │   ├── models.py                 # SQLAlchemy ORM models (12 tables)
│   │   └── session.py                # Async DB session factory
│   ├── middleware/
│   │   ├── disclaimer.py             # Consent enforcement middleware
│   │   └── rate_limit.py             # Token-bucket rate limiter
│   ├── services/
│   │   ├── audit.py                  # Audit trail persistence (case runs, claims, evidence)
│   │   ├── cache.py                  # SHA-256 keyed cache for embeddings and triage results
│   │   ├── calculation.py            # 3-phase SGB II calculation verification (extract→compute→explain)
│   │   ├── chat_reasoning.py         # Conversational reasoning (pipeline + RAG chat)
│   │   ├── conversation.py           # Conversation CRUD service
│   │   ├── corpus.py                 # Legal corpus scraper (11 source types: gesetze-im-internet.de HTML + BA Weisung PDFs), hierarchical chunker, embedder, runtime source config
│   │   ├── ocr.py                    # 3-tier OCR fallback pipeline with dual-pass preprocessing
│   │   ├── parameter_store.py        # Versioned legal parameter lookup (Regelbedarf, etc.)
│   │   ├── reasoning.py              # LLM-based reasoning service (triage, combined stages, adversarial)
│   │   ├── retrieval.py              # pgvector similarity search + keyword fallback
│   │   ├── rules_engine.py           # Deterministic SGB II calculation rules (§ 11b tiers, lookup tables)
│   │   └── verification.py           # Deterministic quote/evidence verification
│   ├── utils/
│   │   ├── image.py                  # Image normalization (300 dpi JPG)
│   │   ├── pdf.py                    # PDF extraction utilities
│   │   ├── text.py                   # Text normalization helpers
│   │   └── tokens.py                 # Prompt/token budgeting utilities
│   ├── __init__.py
│   └── main.py                       # FastAPI app entry point (lifespan, middleware, routers)
├── devdocs/                          # Architecture documentation
│   ├── design_document.md            # High-level design & system goals
│   ├── technical_specification.md    # Detailed technical spec for implementation
│   └── ui_testing_guide.md           # Comprehensive manual UI testing checklist
├── scripts/                          # Utility scripts
│   └── benchmark_analyze.py          # SSE pipeline latency benchmark
├── static/                           # Frontend assets (vanilla HTML/JS/CSS)
│   ├── index.html                    # Main page (Analyze + Chat + Settings modes)
│   ├── app.js                        # SSE streaming, corpus UI, pipeline UI, chat UI, settings UI
│   └── style.css                     # Responsive styles (light + chat dark theme + settings)
├── tests/
│   ├── unit/                         # Unit tests (15 files, no DB needed)
│   ├── integration/                  # Integration tests (4 files, DB required)
│   ├── conftest.py                   # Shared fixtures
│   └── generate_test_files.py        # Test data generator
├── alembic.ini                       # Alembic configuration
├── AGENTS.md                         # AI agent context and persistent memory
├── DISCLAIMER_DE.md                  # Liability disclaimer (German)
├── DISCLAIMER_EN.md                  # Liability disclaimer (English)
├── docker-compose.yml                # Docker Compose stack (db + citizen-app)
├── Dockerfile                        # Multi-stage application container
├── LICENSE                           # MIT license
├── pyproject.toml                    # Project metadata & dependencies
├── uv.lock                           # Lockfile for uv package manager
├── .env.example                      # Environment variable template
└── README.md                         # This file
```

## Key Configuration

All settings are managed via environment variables or `.env` file (see `app/core/config.py` for defaults).

| Category | Setting | Default | Description |
|---|---|---|---|
| **LLM** | `PRIMARY_MODEL` | `deepseek/deepseek-v4-flash` | Primary reasoning model |
| | `EMBEDDING_MODEL` | `openai/text-embedding-3-small` | Embedding model |
| | `TRIAGE_MODEL` | — | Optional override for triage stages |
| | `FINAL_MODEL` | — | Optional override for final stages |
| | `CALCULATION_MODEL` | — | Optional override for calculation check |
| **Pipeline** | `COMBINE_TRIAGE_STAGES` | `True` | Merge classification + decomposition into one LLM call |
| | `COMBINE_FINAL_STAGES` | `True` | Merge construction + verification + generation into one LLM call |
| | `ENABLE_CALCULATION_CHECK` | `True` | Run SGB II calculation verification (Stage 9) |
| **Retrieval** | `RETRIEVAL_MODE` | `combined` | `combined` or `per_question` embedding |
| | `TOP_K_RETRIEVAL` | `10` | Max chunks returned per query |
| | `RETRIEVAL_KEYWORD_FALLBACK` | `True` | Enable tsvector keyword fallback |
| **OCR** | `ENABLE_OCR_LLM_SYNTHESIS` | `False` | Use LLM to reconcile dual-OCR results |
| | `OCR_MAX_PAGES` | `10` | Max PDF pages for image-based OCR (0 = unlimited) |
| **Budget** | `MAX_TRIAGE_INPUT_CHARS` | `8000` | Max chars sent to triage LLM |
| | `MAX_CHUNKS_FOR_FINAL` | `6` | Max chunks in final generation context |
| **Cache** | `ENABLE_CACHE` | `True` | Enable embedding/triage result cache |
| | `CACHE_TTL_SEC` | `86400` | Cache TTL (24 hours) |
| **Corpus** | `CORPUS_SOURCES` | `["sgb2", "sgbx"]` | Default source types (env fallback); overridable at runtime via Settings page (persisted to `.corpus_sources.json`) |

See `.env.example` for the complete list of configurable settings.

## Security & Privacy Posture

* **Data Locality:** All document processing, OCR, and database operations run locally. Only normalized text (stripped of EXIF/metadata) is transmitted to OpenRouter for LLM inference.
* **Consent Enforcement:** The API and UI mandate explicit acknowledgment of a liability disclaimer before execution. The disclaimer is versioned and the frontend persists acknowledgment in `localStorage`.
* **Data Minimization:** To comply with DSGVO/GDPR, IP addresses are never stored in plain text. The system automatically generates a local `.secret_salt` file on first boot to securely hash session data in the audit logs.
* **Port Binding:** All services bind to `127.0.0.1` (localhost) by default, preventing external network access.
* **Rate Limiting:** An in-memory sliding-window rate limiter is enabled by default (configurable requests/window), guarding against runaway or abusive requests.

## API Documentation

Once the server is running, interactive API documentation is available at:

* **Swagger UI:** [http://localhost:8000/docs](http://localhost:8000/docs)
* **ReDoc:** [http://localhost:8000/redoc](http://localhost:8000/redoc)

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

**Disclaimer:** This software provides automated legal reasoning based on provided texts. It does not constitute binding legal advice. Users must acknowledge the liability disclaimer before utilizing the API or UI.
