# Citizen (v1.0) - German Social Law Reasoning & Drafting System

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

* **Docker & Docker Compose** (for containerized deployment)
* **Python 3.11+** (for local development)
* **Tesseract OCR** (`tesseract-ocr`, `libtesseract-dev`)
* **PostgreSQL 16** with `pgvector` (if running outside of Docker)

## Quickstart (Docker Compose)

The easiest way to run Citizen is via Docker Compose, which provisions both the FastAPI application and the PostgreSQL database.

1. **Clone the repository:**
   ```bash
   git clone https://github.com/your-org/citizen.git
   cd citizen
   ```

2. **Configure the environment:**
   ```bash
   cp .env.example .env
   ```
   *Edit `.env` and insert your `OPENROUTER_API_KEY`. (Note: Cryptographic salts for GDPR-compliant audit logging are generated automatically by the application on first boot and saved to `.secret_salt`).*

3. **Start the system:**
   ```bash
   docker compose up -d --build
   ```

4. **Access the application:**
   Open `http://localhost:8000` in your browser.

## Local Development Setup

For active development, run the application locally against a containerized or local database.

```bash
# 1. Create and activate a virtual environment
python3.11 -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
pip install -e ".[dev]"

# 3. Run database migrations
alembic upgrade head

# 4. Start the development server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## Security & Privacy Posture

* **Data Locality:** All document processing, OCR, and database operations run locally. Only normalized text (stripped of EXIF/metadata) is transmitted to OpenRouter for LLM inference.
* **Consent Enforcement:** The API and UI mandate explicit acknowledgment of a liability disclaimer before execution.
* **Data Minimization:** To comply with DSGVO/GDPR, IP addresses are never stored in plain text. The system automatically generates a local `.secret_salt` file on first boot to securely hash session data in the audit logs.

## API Documentation

Once the server is running, interactive API documentation is available at:
* **Swagger UI:** `http://localhost:8000/docs`
* **ReDoc:** `http://localhost:8000/redoc`

## License

This project is licensed under the MIT License - see the[LICENSE](LICENSE) file for details.

**Disclaimer:** This software provides automated legal reasoning based on provided texts. It does not constitute binding legal advice. Users must acknowledge the liability disclaimer before utilizing the API or UI.
