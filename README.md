# Citizen — Multi-Area German Legal Reasoning Engine

## PROTOTYPE STATUS — NOT FOR PRODUCTIVE USE

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115.0-009688.svg)](https://fastapi.tiangolo.com)

Citizen is a local-first, evidence-constrained legal reasoning engine for German law. It supports multiple legal areas — from social law (SGB II/X) to inheritance law (BGB, ErbStG, HöfeO), family law, tenancy law, labor law, and more. It processes scanned administrative correspondence, cross-references claims against current statutes and case law, performs deterministic calculations, and generates structured, evidence-backed legal assessments.

## Legal Areas

| Area | Statutes |
|---|---|
| **Sozialrecht** (Bürgergeld / Jobcenter) | SGB I, II, III, IX, X, XII |
| **Erbrecht** | BGB (Erbrecht), ErbStG, HöfeO |
| **Schenkungsrecht** | BGB (Schenkung), ErbStG |
| **Familienrecht** | BGB (Familienrecht) |
| **Mietrecht** | BGB (Mietrecht) |
| **Arbeitsrecht** | BGB, KSchG, BUrlG, TVG |
| **Vertragsrecht** | BGB (Schuldrecht) |
| **Verwaltungsrecht** | VwVfG, SGG |
| **Strafrecht** | StGB |
| **Andere** | Catch-all for unclassified inquiries |

## Core Features

* **Multi-Area Intake:** Interactive multi-turn interview (2–8 turns) to identify the relevant legal area(s) and narrow the scope before analysis. Suggests pipeline presets (e.g. "Sozialrecht Allgemein", "Erbe mit Testament", "Höfeübergabe") based on user scenario.
* **Pipeline Presets:** Curated configuration profiles per use case — pre-tuned prompts, retrieval settings, and stage flags for each legal area combination. Auto-suggested during intake. 5 built-in presets included.
* **Evidence-Bound Output:** Every factual assertion and legal interpretation is explicitly bound to retrieved legal sources through `pgvector` similarity search, with confidence scoring and direct quote excerpts stored in the database.
* **9-Stage Reasoning Pipeline:** Normalization → Classification+Decomposition (combined) → Retrieval (pgvector + keyword fallback) → Construction+Verification+Generation (combined) → Adversarial Review → Calculation Check. Real-time SSE streaming with optional token-by-token output.
* **Adversarial Legal Review:** Multi-perspective review by a "Rechtsprüfungsrat" — evaluates claims from defense, authority, and judicial perspectives to surface hidden weaknesses or counterarguments.
* **Case Chat:** Interactive, persistent chat grounded in pipeline output. Supports targeted re-evaluation of specific claims, claim editing, user adjudication (confirm/flag/correct), and export (JSON/Markdown).
* **Deterministic SGB II Calculation Engine:** Three-phase numerical verification — LLM extracts structured monetary values → deterministic rules engine applies § 11b SGB II tiers → LLM explains findings.
* **Local-First OCR Pipeline:** Fully local document ingestion (PDF/JPG/PNG/TXT/HTML/EML) up to 25 MB. Deterministic fallback chain (`pdfplumber` → `PyMuPDF` → `Tesseract`) with dual-pass image preprocessing.
* **Hierarchical Legal Corpus:** Automated scraping of 16 source types from gesetze-im-internet.de and arbeitsagentur.de (Fachliche Weisungen as PDFs). Chunked at four granularity levels (Statute → § → Absatz → Satz). Runtime-selectable via settings page.
* **Fault-Tolerant LLM Routing:** OpenRouter client with automated fallback chain. Separate API keys for inference and embeddings. Configurable per-stage model overrides.
* **Multi-Turn Conversational Reasoning:** Chat interface with RAG + conversation history. First message triggers the full pipeline; subsequent messages use focused retrieval.
* **Audit Trail:** Full pipeline auditing — every case run, stage log, claim, and evidence binding persisted to PostgreSQL.
* **Browser-Based UI:** Vanilla HTML/JS/CSS frontend with three modes — Analyze (pipeline + case chat), Chat (conversations), Settings (corpus source selection). Real-time SSE progress, dark theme, disclaimer acceptance.

## Architecture

| Layer | Technology |
|---|---|
| **Backend** | FastAPI, Uvicorn (SSE streaming) |
| **Database** | PostgreSQL 16 + `pgvector` + `tsvector` |
| **ORM / Migrations** | SQLAlchemy 2.0 (async), Alembic (6 migrations) |
| **Frontend** | Vanilla HTML/JS/CSS (v0.4.0) |
| **LLMs** | OpenRouter (deepseek/deepseek-v4-pro for inference, openai/text-embedding-3-small for embeddings) |
| **OCR** | pdfplumber → PyMuPDF → Tesseract (German) |
| **Tooling** | ruff (formatting & linting), mypy (strict), pytest (unit + integration) |

## Database Schema (13 Tables)

| # | Table | Purpose |
|---|---|---|
| 1 | `legal_source` | Root record for a legal document |
| 2 | `legal_chunk` | Hierarchical unit of law (statute→§→absatz→satz), tagged with `legal_area` |
| 3 | `chunk_embedding` | Dense vector (1536d, cosine) |
| 4 | `case_run` | Single analysis session with chat history and user edits |
| 5 | `pipeline_stage_log` | Immutable audit per pipeline stage |
| 6 | `claim` | Atomic legal assertion with user adjudication |
| 7 | `evidence_binding` | Claim ↔ LegalChunk link with strength & quote |
| 8 | `cache_entry` | Key-value cache (embeddings, triage) |
| 9 | `legal_parameter` | Versioned legal params (Regelbedarf, Freibetrag...) |
| 10 | `conversation` | Multi-turn chat session |
| 11 | `conversation_message` | Single message (user/assistant/system) |
| 12 | `conversation_document` | Document attached to conversation |
| 13 | `intake_session` | Multi-turn intake interview |
| 13b | `case_run_area` | Many-to-many case_run ↔ legal_area |

## 16 Supported Statute Source Types

sgb1, sgb2, sgb3, sgb9, sgb12, sgbx, bgb, vwvfg, sgg, weisung, bsg, erbstg, hoefev, kschg, burlg, tvg

## Prerequisites

### Docker Deployment (Recommended)

* [Docker](https://docs.docker.com/engine/install/) & [Docker Compose](https://docs.docker.com/compose/install/)
* OpenRouter API key (for LLM inference)
* OpenRouter API key with embedding provider access (for corpus embeddings)

### Local Development

| Dependency | Install (Ubuntu/Debian) |
|---|---|
| Python 3.11+ | `sudo apt install python3.11 python3.11-venv` |
| Tesseract OCR 5.x | `sudo apt install tesseract-ocr libtesseract-dev tesseract-ocr-deu` |
| PostgreSQL 16 + pgvector | `sudo apt install postgresql-16 postgresql-16-pgvector` |
| OpenRouter API keys | Sign up at [openrouter.ai](https://openrouter.ai) |

---

## Quickstart: Docker Compose

```bash
# 1. Clone the repository
git clone https://github.com/your-org/citizen.git
cd citizen

# 2. Create your environment file
cp .env.example .env

# 3. Edit .env — set at minimum:
#    OPENROUTER_API_KEY=sk-or-v1-...        (LLM inference key)
#    EMBEDDING_API_KEY=sk-or-v1-...          (embedding key, if separate)
#    OPENROUTER_API_KEY works for embeddings too if not set

# 4. Build and start the stack
docker compose up -d --build

# 5. Wait for health check, then run migrations
docker compose exec citizen-app alembic upgrade head

# 6. Load the legal corpus (scraping + embedding)
curl -X POST http://localhost:8000/api/v1/corpus/update \
  -H "X-Disclaimer-Ack: v0.1.0" \
  -H "Content-Type: application/json" -d '{}'

# 7. Open the app
#    http://localhost:8000
```

To stop:
```bash
docker compose down
```

---

## API Endpoints (30+)

| Group | Method | Path | Description |
|---|---|---|---|
| **ingest** | `POST` | `/api/v1/ingest` | Upload and OCR a document |
| **analyze** | `POST` | `/api/v1/analyze` | Execute full 9-stage pipeline (SSE) |
| **cases** | `GET` | `/api/v1/cases` | List all case runs |
| **cases** | `GET` | `/api/v1/cases/{id}` | Get case run with claims and evidence |
| **cases** | `DELETE` | `/api/v1/cases/{id}` | Delete case run |
| **cases** | `POST` | `/api/v1/cases/{id}/chat` | Case-grounded chat (SSE) |
| **cases** | `POST` | `/api/v1/cases/{id}/reevaluate` | Targeted claim re-evaluation (SSE) |
| **cases** | `POST` | `/api/v1/cases/{id}/claims` | Add a claim to a case |
| **cases** | `PATCH` | `/api/v1/cases/{id}/claims/{cid}` | Edit a claim |
| **cases** | `POST` | `/api/v1/cases/{id}/adjudicate` | User adjudication (confirm/flag/correct) |
| **cases** | `GET` | `/api/v1/cases/{id}/export` | Export case (JSON/Markdown) |
| **conversations** | `GET`,`POST` | `/api/v1/conversations` | List or create conversations |
| **conversations** | `GET`,`DELETE` | `/api/v1/conversations/{id}` | Get or delete conversation |
| **conversations** | `POST` | `/api/v1/conversations/{id}/messages` | Send chat message (SSE) |
| **conversations** | `POST`,`GET` | `/api/v1/conversations/{id}/documents` | Attach or list documents |
| **conversations** | `DELETE` | `/api/v1/conversations/{id}/documents/{did}` | Remove document |
| **corpus** | `POST` | `/api/v1/corpus/update` | Scrape + embed legal texts |
| **corpus** | `GET` | `/api/v1/corpus/status/{job_id}` | Check update progress |
| **corpus** | `GET` | `/api/v1/corpus/health` | Corpus health (chunks, warnings) |
| **corpus** | `GET` | `/api/v1/corpus/available-sources` | List all source types |
| **corpus** | `GET`,`PUT` | `/api/v1/corpus/sources` | Get/set runtime source selection |
| **intake** | `POST` | `/api/v1/intake/start` | Start multi-turn intake interview |
| **intake** | `GET` | `/api/v1/intake/{id}` | Get intake session state |
| **intake** | `POST` | `/api/v1/intake/{id}/message` | Send intake response (SSE) |
| **intake** | `POST` | `/api/v1/intake/{id}/confirm` | Confirm intake results |
| **intake** | `POST` | `/api/v1/intake/{id}/restart` | Restart intake |
| **presets** | `GET` | `/api/v1/presets` | List all pipeline presets |
| **presets** | `GET` | `/api/v1/presets/{id}` | Get preset details |
| **presets** | `POST` | `/api/v1/presets/suggest` | Suggest preset from scenario |
| **presets** | `POST` | `/api/v1/presets/apply` | Apply preset configuration |
| **meta** | `GET` | `/api/v1/meta/disclaimer/version` | Disclaimer version |
| **meta** | `GET` | `/api/v1/meta/disclaimer/text` | Full disclaimer text (German) |
| **meta** | `GET` | `/api/v1/meta/version` | API and disclaimer versions |
| **health** | `GET` | `/health` | Liveness probe |

---

## Directory Structure

```
citizen/
├── alembic/                              # 6 migrations
│   └── versions/
│       ├── 001_init_schema.py
│       ├── 002_add_cache_entry.py
│       ├── 003_add_conversations.py
│       ├── 004_add_legal_parameter.py
│       ├── 005_add_case_chat_fields.py
│       └── 006_add_intake_and_legal_areas.py
├── app/
│   ├── api/routes/                       # 9 route modules
│   │   ├── analyze.py                    # Pipeline analysis (SSE)
│   │   ├── cases.py                      # Case CRUD, chat, re-eval, adjudication
│   │   ├── conversations.py              # Multi-turn chat
│   │   ├── corpus.py                     # Corpus management
│   │   ├── ingest.py                     # Document ingestion & OCR
│   │   ├── intake.py                     # Multi-turn intake interviews
│   │   ├── meta.py                       # Metadata endpoints
│   │   └── presets.py                    # Pipeline presets
│   ├── core/
│   │   ├── config.py                     # Pydantic settings
│   │   ├── pipeline.py                   # 9-stage SSE orchestrator
│   │   └── router.py                     # LLM router with fallback chain
│   ├── db/
│   │   ├── models.py                     # 13 ORM models
│   │   └── session.py                    # Async session factory
│   ├── middleware/
│   │   ├── disclaimer.py                 # Consent enforcement
│   │   └── rate_limit.py                 # Sliding-window rate limiter
│   ├── services/                         # 18 service modules
│   │   ├── audit.py, cache.py, calculation.py
│   │   ├── case_chat.py, chat_reasoning.py, conversation.py
│   │   ├── corpus.py, corpus_readiness.py
│   │   ├── intake.py, ocr.py, parameter_store.py
│   │   ├── presets.py, prompts.py, reasoning.py
│   │   ├── retrieval.py, rules_engine.py, verification.py
│   ├── utils/                            # image, pdf, text, tokens
│   └── main.py                           # App entry point
├── static/                               # Frontend v0.4.0
│   ├── index.html                        # 3 modes: Analyze, Chat, Settings
│   ├── app.js                            # Vanilla JS logic
│   └── style.css                         # Dark theme
├── tests/                                # 26 test files (~6,800 lines)
├── scripts/
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml
└── .env.example
```

## Key Configuration

| Category | Setting | Default | Description |
|---|---|---|---|
| **LLM Keys** | `OPENROUTER_API_KEY` | — | Key for LLM inference |
| | `EMBEDDING_API_KEY` | `""` | Separate key for embeddings (falls back to `OPENROUTER_API_KEY`) |
| **Models** | `PRIMARY_MODEL` | `deepseek/deepseek-v4-pro` | Primary reasoning model |
| | `EMBEDDING_MODEL` | `openai/text-embedding-3-small` | Embedding model |
| | `TRIAGE_MODEL` / `FINAL_MODEL` | — | Per-stage model overrides |
| **Pipeline** | `COMBINE_TRIAGE_STAGES` | `True` | Merge classification + decomposition |
| | `COMBINE_FINAL_STAGES` | `True` | Merge construction + verification + generation |
| | `ENABLE_CALCULATION_CHECK` | `True` | Run SGB II calculation verification |
| | `PIPELINE_TIMEOUT_SEC` | `120` | Hard pipeline timeout |
| **Retrieval** | `RETRIEVAL_MODE` | `combined` | Embedding strategy |
| | `TOP_K_RETRIEVAL` | `10` | Max chunks per query |
| | `MAX_COSINE_DISTANCE` | `0.95` | Cosine threshold |
| **Corpus** | `CORPUS_SOURCES` | `["sgb2", "sgbx"]` | Default sources (overridable at runtime) |
| **Rate Limit** | `RATE_LIMIT_REQUESTS` | `60` | Requests per window |
| | `RATE_LIMIT_WINDOW` | `60` | Window in seconds |
| **OCR** | `ENABLE_OCR_LLM_SYNTHESIS` | `False` | LLM synthesis of dual-OCR results |

See `.env.example` for the complete list.

## Running Tests

```bash
# Unit tests (no DB needed)
pytest tests/unit/ -v

# Integration tests (requires running database)
alembic upgrade head
pytest tests/integration/ -v

# All tests
pytest -v

# Code quality
ruff check app/ tests/
ruff format --check app/ tests/
mypy app/
```

## Security & Privacy

* **Data Locality:** All document processing runs locally. Only normalized text is sent to OpenRouter.
* **Consent Enforcement:** Mandatory disclaimer acknowledgment via `X-Disclaimer-Ack` header.
* **Data Minimization:** IP addresses never stored in plain text. Auto-generated `.secret_salt` on first boot.
* **Rate Limiting:** In-memory sliding-window rate limiter enabled by default.

## API Documentation

Once running:
* **Swagger UI:** [http://localhost:8000/docs](http://localhost:8000/docs)
* **ReDoc:** [http://localhost:8000/redoc](http://localhost:8000/redoc)

## License

MIT License — see [LICENSE](LICENSE).

**Disclaimer:** This software provides automated legal reasoning. It does not constitute binding legal advice.
