# Citizen — German Social Law Reasoning & Drafting System

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115.0-009688.svg)](https://fastapi.tiangolo.com)

Citizen is a local-first, evidence-constrained legal reasoning engine designed to help individuals navigate German social bureaucracy (e.g., Jobcenter, Sozialamt). It processes scanned administrative correspondence, cross-references demands against current statutes (SGB II/X) and case law, and generates a structured, evidence-backed legal assessment.

## Core Features

* **Local-First OCR Pipeline:** Fully local document ingestion (PDF/JPG/PNG) up to 25MB, utilizing a deterministic fallback chain (`pdfplumber` → `PyMuPDF` → `Tesseract`).
* **Hierarchical Legal Corpus:** Automated chunking of German legal texts (Statute → § → Absatz → Satz) to preserve exact legal boundaries for precise citation.
* **7-Stage Reasoning Pipeline:** A deterministic orchestrator that enforces a strict sequence: Normalization → Classification → Decomposition → Retrieval → Construction → Verification → Generation.
* **Evidence-Bound Output:** Every factual assertion and legal interpretation is explicitly bound to retrieved legal sources via `pgvector` similarity search.
* **Deterministic LLM Routing:** Fault-tolerant OpenRouter client with an automated fallback chain (`qwen3.6-plus` → `gpt-5.4-nano` → `free`).
* **Zero-Friction Compliance:** GDPR-compliant audit logging with automatically generated, persistent cryptographic salts. No manual security configuration required.

## Architecture

The system is built on a modern, asynchronous Python stack:

* **Backend:** FastAPI, Uvicorn
* **Database:** PostgreSQL 16 with `pgvector` extension
* **ORM & Migrations:** SQLAlchemy 2.0 (asyncio), Alembic
* **Frontend:** Vanilla HTML/JS/CSS (Server-Sent Events for streaming)

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

# 4. Start the stack (builds the image + starts PostgreSQL)
docker compose up -d --build

# 5. Wait ~10 seconds for the database to be ready, then run migrations
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
# Should list 7 tables: case_run, claim, evidence_binding,
#   legal_chunk, legal_source, pipeline_stage_log, user_session
```

### Step 5 — Start the development server

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Open [http://localhost:8000](http://localhost:8000) in your browser.

---

## Running Tests

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

### All tests at once

```bash
# Database must be running and migrated
alembic upgrade head
pytest -v
```

---

## Directory Structure

```
citizen/
├── alembic/                          # Database migrations
│   ├── versions/
│   │   └── 001_init_schema.py        # Initial schema (7 tables)
│   ├── env.py
│   └── script.py.mako
├── app/                              # Application source
│   ├── api/
│   │   └── routes/                   # API route handlers
│   ├── core/
│   │   ├── config.py                 # Settings & validation (Pydantic)
│   │   ├── pipeline.py               # 7-stage orchestrator
│   │   └── router.py                 # LLM router + fallback chain
│   ├── db/
│   │   ├── models.py                 # SQLAlchemy ORM models
│   │   └── session.py                # Async DB session factory
│   ├── middleware/
│   │   ├── disclaimer.py             # Consent enforcement middleware
│   │   └── rate_limit.py             # Token-bucket rate limiter
│   ├── services/
│   │   ├── corpus.py                 # Legal corpus scraper & chunker
│   │   ├── ocr.py                    # 3-tier OCR fallback pipeline
│   │   ├── reasoning.py              # LLM-based reasoning service
│   │   └── retrieval.py              # pgvector similarity search
│   ├── utils/
│   │   ├── image.py                  # Image normalization (300dpi JPG)
│   │   ├── pdf.py                    # PDF extraction utilities
│   │   └── text.py                   # Text normalization helpers
│   ├── __init__.py
│   └── main.py                       # FastAPI app entry point
├── devdocs/                          # Architecture documentation
├── static/                           # Frontend assets (HTML/JS/CSS)
├── tests/
│   ├── unit/                         # Unit tests (no DB needed)
│   ├── integration/                  # Integration tests (DB required)
│   └── conftest.py                   # Shared fixtures
├── alembic.ini                       # Alembic configuration
├── deploy_db.sh                      # Database reconciliation helper
├── DISCLAIMER.md                     # Liability disclaimer (bilingual)
├── docker-compose.yml                # Docker Compose stack
├── Dockerfile                        # Application container
├── pyproject.toml                    # Project metadata & dependencies
└── README.md                         # This file
```

## Security & Privacy Posture

* **Data Locality:** All document processing, OCR, and database operations run locally. Only normalized text (stripped of EXIF/metadata) is transmitted to OpenRouter for LLM inference.
* **Consent Enforcement:** The API and UI mandate explicit acknowledgment of a liability disclaimer before execution.
* **Data Minimization:** To comply with DSGVO/GDPR, IP addresses are never stored in plain text. The system automatically generates a local `.secret_salt` file on first boot to securely hash session data in the audit logs.

## API Documentation

Once the server is running, interactive API documentation is available at:

* **Swagger UI:** [http://localhost:8000/docs](http://localhost:8000/docs)
* **ReDoc:** [http://localhost:8000/redoc](http://localhost:8000/redoc)

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

**Disclaimer:** This software provides automated legal reasoning based on provided texts. It does not constitute binding legal advice. Users must acknowledge the liability disclaimer before utilizing the API or UI.
