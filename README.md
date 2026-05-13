# Citizen — German Social Law Reasoning & Drafting System

## THIS SOFTWARE IS IN A PROTOTYPE STAGE. NOT FOR PRODUCTIVE USE. USE AT YOUR OWN RISK!

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115.0-009688.svg)](https://fastapi.tiangolo.com)

Citizen is a local-first, evidence-constrained legal reasoning engine designed to help individuals navigate German social bureaucracy (e.g., Jobcenter, Sozialamt). It processes scanned administrative correspondence, cross-references demands against current statutes (SGB II/X) and case law, and generates a structured, evidence-backed legal assessment.

## Core Features

* **Local-First OCR Pipeline:** Fully local document ingestion (PDF/JPG/PNG) up to 25 MB, utilizing a deterministic fallback chain (`pdfplumber` → `PyMuPDF` → `Tesseract`) with image preprocessing (conversion to 300 dpi JPG, contrast enhancement, optional binarization).
* **Hierarchical Legal Corpus:** Automated scraping of German legal texts from gesetze-im-internet.de, chunked at four granularity levels (Statute → § → Absatz → Satz) to preserve exact legal boundaries for precise citation. Includes statutes (SGB II, SGB X), administrative directives (Weisungen), and case law (BSG decisions).
* **7-Stage Reasoning Pipeline:** A deterministic orchestrator enforcing a strict, sequential analysis flow: Normalization → Classification → Decomposition → Retrieval → Construction → Verification → Generation. Each stage is streamed in real time via Server-Sent Events (SSE).
* **Evidence-Bound Output:** Every factual assertion and legal interpretation is explicitly bound to retrieved legal sources through `pgvector` similarity search, with confidence scoring and direct quote excerpts stored in the database.
* **Deterministic LLM Routing:** Fault-tolerant OpenRouter client with an automated fallback chain (`deepseek/deepseek-v4-flash` → `deepseek/deepseek-v4-flash` → `/openrouter/free`), configurable via environment variables.
* **Audit Trail:** Full pipeline execution auditing — every case run, stage log, claim, and evidence binding is persisted to PostgreSQL for traceability and compliance.
* **Zero-Friction Compliance:** GDPR-compliant audit logging with automatically generated, persistent cryptographic salts on first boot. No manual security configuration required.
* **Multi-Turn Conversational Reasoning:** Iterative chat interface for discussing uploaded documents across multiple turns. First message triggers the full pipeline; subsequent messages use focused RAG + conversation history for grounded responses. Conversations and documents persist across sessions.
* **Browser-Based UI:** Vanilla HTML/CSS/JS frontend with disclaimer acceptance, drag-and-drop document upload, corpus management controls, real-time pipeline progress visualization, structured result display, and a dedicated chat mode with conversation sidebar.

## Architecture

The system is built on a modern, asynchronous Python stack:

* **Backend:** FastAPI, Uvicorn
* **Database:** PostgreSQL 16 with `pgvector` extension for vector similarity search
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

# Alternatively, if you use uv:
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
# Should list 11 tables: cache_entry, case_run, chunk_embedding, claim,
#   conversation, conversation_document, conversation_message,
#   evidence_binding, legal_chunk, legal_source, pipeline_stage_log
```

### Step 5 — Start the development server

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Open [http://localhost:8000](http://localhost:8000) in your browser.

---

## Running Tests

The project includes an extensive test suite (~4300 lines) with unit and integration tests, plus benchmarking support.

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
| `test_chunker.py` | Legal text hierarchical chunking |
| `test_config.py` | Settings validation and salt generation |
| `test_corpus_endpoint.py` | Corpus API route logic |
| `test_db/test_models.py` | ORM model constraints and relationships |
| `test_middleware.py` | Disclaimer and rate-limiting middleware |
| `test_ocr.py` | 3-tier OCR fallback pipeline |
| `test_pdf.py` | PDF extraction utilities |
| `test_pipeline.py` | 7-stage pipeline orchestrator |
| `test_reasoning.py` | LLM reasoning service |
| `test_router.py` | OpenRouter client and fallback chain |
| `test_session.py` | Async database session factory |

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
```

---

## API Endpoints

| Group | Prefix | Endpoints | Description |
|---|---|---|---|
| **ingest** | `/api/v1` | `POST /ingest` | Upload and OCR a document (PDF/JPG/PNG) |
| **analyze** | `/api/v1` | `POST /analyze` | Execute the full 7-stage pipeline on raw text, streaming SSE |
| **conversations** | `/api/v1` | `POST /conversations`, `GET /conversations`, `GET /conversations/{id}`, `DELETE /conversations/{id}` | CRUD for multi-turn conversations |
| **conversations** | `/api/v1` | `POST /conversations/{id}/messages` | Send a message in a conversation, streaming SSE response |
| **conversations** | `/api/v1` | `POST /GET /DELETE /conversations/{id}/documents` | Attach, list, or remove documents in a conversation |
| **corpus** | `/api/v1` | `POST /corpus/update`, `GET /corpus/status/{job_id}` | Trigger legal corpus scrape & embedding, check progress |
| **meta** | `/api/v1` | `GET /meta/disclaimer/version`, `GET /meta/disclaimer/text`, `GET /meta/version` | Disclaimer and version metadata |
| **health** | `/` | `GET /health` | Liveness probe |

---

## Directory Structure

```
citizen/
├── alembic/                          # Database migrations
│   ├── versions/
│   │   ├── 001_init_schema.py        # Initial schema (7 tables)
│   │   ├── 002_add_cache_entry.py    # Cache entry table
│   │   └── 003_add_conversations.py  # Conversation, message, document tables
│   ├── env.py
│   └── script.py.mako
├── app/                              # Application source
│   ├── api/
│   │   └── routes/
│   │       ├── analyze.py            # POST /analyze (SSE pipeline streaming)
│   │       ├── conversations.py      # POST /conversations/* (chat, documents, SSE)
│   │       ├── corpus.py             # POST /corpus/update, GET /corpus/status
│   │       ├── ingest.py             # POST /ingest (document upload & OCR)
│   │       └── meta.py               # GET /meta/* (disclaimer, version)
│   ├── core/
│   │   ├── config.py                 # Settings & validation (Pydantic)
│   │   ├── pipeline.py               # 7-stage orchestrator
│   │   └── router.py                 # LLM router + fallback chain
│   ├── db/
│   │   ├── models.py                 # SQLAlchemy ORM models (11 tables)
│   │   └── session.py                # Async DB session factory
│   ├── middleware/
│   │   ├── disclaimer.py             # Consent enforcement middleware
│   │   └── rate_limit.py             # Token-bucket rate limiter
│   ├── services/
│   │   ├── audit.py                  # Audit trail persistence (case runs, claims, evidence)
│   │   ├── cache.py                  # Key-value cache for embeddings and triage results
│   │   ├── chat_reasoning.py         # Conversational reasoning (pipeline + RAG chat)
│   │   ├── conversation.py           # Conversation CRUD service
│   │   ├── corpus.py                 # Legal corpus scraper, chunker & embedder
│   │   ├── ocr.py                    # 3-tier OCR fallback pipeline
│   │   ├── reasoning.py              # LLM-based reasoning service
│   │   ├── retrieval.py              # pgvector similarity search
│   │   └── verification.py           # Deterministic quote/evidence verification
│   ├── utils/
│   │   ├── image.py                  # Image normalization (300 dpi JPG)
│   │   ├── pdf.py                    # PDF extraction utilities
│   │   └── text.py                   # Text normalization helpers
│   ├── __init__.py
│   └── main.py                       # FastAPI app entry point (lifespan, middleware, routers)
├── devdocs/                          # Architecture documentation
│   ├── design_document.md            # High-level design
│   ├── roadmap.md                    # Work packages & milestones
│   └── technical_specification.md    # Detailed technical spec
├── static/                           # Frontend assets (vanilla HTML/JS/CSS)
│   ├── index.html                    # Main page (Analyze mode + Chat mode)
│   ├── app.js                        # SSE streaming, corpus UI, pipeline UI, chat UI
│   └── style.css                     # Responsive styles (light + chat dark theme)
├── tests/
│   ├── unit/                         # Unit tests (12 files, no DB needed)
│   ├── integration/                  # Integration tests (4 files, DB required)
│   └── conftest.py                   # Shared fixtures
├── alembic.ini                       # Alembic configuration
├── DISCLAIMER.md                     # Liability disclaimer (bilingual EN/DE)
├── docker-compose.yml                # Docker Compose stack (db + citizen-app)
├── Dockerfile                        # Multi-stage application container
├── LICENSE                           # MIT license
├── pyproject.toml                    # Project metadata & dependencies
├── .env.example                      # Environment variable template
└── README.md                         # This file
```

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
