# DOCUMENT 2: TECHNICAL SPECIFICATION
**System:** Citizen (v1.0)
**Target Execution Agent:** Zero-Context Coding Agent
**Compliance:** Strictly aligned with Document 1. All details traceable or explicitly marked.

---

## 1. PROJECT STRUCTURE

```
citizen/
├── .env.example                  # Exhaustive environment variable template
├── docker-compose.yml            # Local orchestration (FastAPI + PostgreSQL 16)
├── Dockerfile                    # Multi-stage build for Ubuntu/Win/Mac compatibility
├── pyproject.toml                # Dependency management, build system, metadata
├── .secret_salt                  # Auto-generated cryptographic salt
├── alembic.ini                   # Database migration configuration
├── alembic/
│   ├── env.py                    # Async Alembic environment setup
│   ├── script.py.mako            # Migration template
│   └── versions/                 # Auto-generated migration scripts
├── app/
│   ├── __init__.py               # Package initialization
│   ├── main.py                   # FastAPI application factory, lifespan, middleware
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py             # Pydantic Settings, env validation
│   │   ├── router.py             # OpenRouter deterministic fallback client
│   │   └── pipeline.py           # 7-stage orchestrator, state machine, SSE streaming
│   ├── api/
│   │   ├── __init__.py
│   │   └── routes/
│   │       ├── __init__.py
│   │       ├── ingest.py         # /api/v1/ingest endpoint
│   │       ├── analyze.py        # /api/v1/analyze endpoint
│   │       └── corpus.py         # /api/v1/corpus/update endpoint
│   ├── services/
│   │   ├── __init__.py
│   │   ├── ocr.py                # Local OCR pipeline, PDF fallbacks, JPG standardization
│   │   ├── corpus.py             # Scraper, parser, hierarchical chunker, embedder
│   │   ├── retrieval.py          # pgvector query engine, diversity constraints, reranking
│   │   └── reasoning.py          # Claim construction, verification, output formatting
│   ├── db/
│   │   ├── __init__.py
│   │   ├── session.py            # Async SQLAlchemy engine/session factory
│   │   └── models.py             # Declarative ORM models, exact schema mapping
│   └── utils/
│       ├── __init__.py
│       ├── text.py               # Normalization, regex cleaning, chunking helpers
│       ├── pdf.py                # pdfplumber/PyMuPDF extraction wrappers
│       └── image.py              # Pillow-based 300dpi JPG conversion, EXIF stripping
├── static/
│   ├── index.html                # Single-page UI, disclaimer modal, upload form
│   ├── app.js                    # Fetch/SSE client, progress rendering, output display
│   └── style.css                 # Minimal responsive styling
├── tests/
│   ├── __init__.py
│   ├── conftest.py               # Pytest fixtures, async DB setup, mock LLM router
│   ├── unit/
│   │   ├── test_ocr.py
│   │   ├── test_chunker.py
│   │   ├── test_router.py
│   │   └── test_reasoning.py
│   └── integration/
│       ├── test_pipeline.py
│       └── test_api_routes.py
└── logs/                         # Runtime logs (gitignored)
```

**File Descriptions:**
- `main.py`: Application entrypoint. Configures lifespan events (DB init, router warmup), mounts static files, registers routers, applies CORS/middleware.
- `core/config.py`: Loads `.env` via `pydantic-settings`. Validates types, enforces required keys, provides typed access.
- `core/router.py`: Implements `OpenRouterClient`. Handles HTTP POST to `https://openrouter.ai/api/v1/chat/completions`, manages retry/fallback chain, logs latency/errors.
- `core/pipeline.py`: Stateful orchestrator. Accepts `PipelineInput`, executes stages 1-7 sequentially, yields `SSEvent` for progress, returns `PipelineOutput`.
- `api/routes/*.py`: FastAPI route handlers. Validate payloads, call services, handle HTTP errors, return JSON/SSE.
- `services/ocr.py`: Synchronous pipeline. Accepts `UploadFile`, enforces 25MB limit, runs `pdfplumber` → `PyMuPDF` → `Tesseract` fallback, returns normalized text.
- `services/corpus.py`: Async scraper. Fetches `gesetze-im-internet.de` XML/HTML, parses structure, chunks hierarchically, generates embeddings, upserts to DB.
- `services/retrieval.py`: Async vector search. Accepts decomposed questions, queries `pgvector` with `IVFFlat`/`HNSW`, enforces top-k diversity, returns ranked chunks.
- `services/reasoning.py`: LLM-driven logic. Constructs prompts for stages 3, 5, 6, 7. Parses JSON responses, validates claim-evidence bindings, formats 6-part output.
- `db/models.py`: SQLAlchemy 2.0 declarative models. Maps exactly to DDL. Includes indexes, constraints, relationships.
- `db/session.py`: `asyncpg` engine factory, scoped session provider, connection pool config.
- `utils/*.py`: Pure functions for text cleaning, PDF extraction, image conversion. No side effects.
- `static/*`: Vanilla JS/HTML/CSS. No build step. Served directly by FastAPI.
- `tests/*`: Pytest suite. Unit tests mock DB/LLM. Integration tests use `TestClient` with ephemeral SQLite/Postgres.

---

## 2. DEPENDENCIES

**Constraint:** Python 3.11+ required. All versions pinned to exact minor/patch for reproducibility.

| Package | Version Constraint | Justification |
|---------|-------------------|---------------|
| `fastapi` | `==0.115.0` | Async web framework, native SSE support, OpenAPI generation |
| `uvicorn[standard]` | `==0.30.6` | ASGI server, high concurrency, cross-platform |
| `sqlalchemy[asyncio]` | `==2.0.35` | Async ORM, strict typing, Alembic compatibility |
| `asyncpg` | `==0.29.0` | High-performance async PostgreSQL driver |
| `alembic` | `==1.13.3` | DB migration management |
| `pgvector` | `==0.3.0` | Python bindings for PostgreSQL vector extension |
| `pydantic` | `==2.9.2` | Data validation, settings management |
| `pydantic-settings` | `==2.5.2` | `.env` loading, type coercion |
| `httpx` | `==0.27.2` | Async HTTP client for OpenRouter API |
| `pdfplumber` | `==0.11.4` | Primary PDF text extraction |
| `PyMuPDF` | `==1.24.10` | Secondary PDF text extraction fallback |
| `pytesseract` | `==0.3.13` | Python wrapper for Tesseract OCR |
| `Pillow` | `==10.4.0` | Image processing, JPG standardization, EXIF stripping |
| `beautifulsoup4` | `==4.12.3` | HTML/XML parsing for corpus scraper |
| `lxml` | `==5.3.0` | Fast XML parser for official legal sources |
| `tiktoken` | `==0.7.0` | Token counting for context window management |
| `python-multipart` | `==0.0.9` | File upload parsing |
| `jinja2` | `==3.1.4` | Template rendering (if needed for prompt assembly) |
| `pytest` | `==8.3.3` | Testing framework |
| `pytest-asyncio` | `==0.24.0` | Async test support |
| `pytest-mock` | `==3.14.0` | Mocking utilities |
| `httpx` | `==0.27.2` | TestClient backend |

**System Dependencies (Ubuntu/Debian):**
- `tesseract-ocr` (>=5.3.0)
- `libtesseract-dev`
- `postgresql-16`
- `postgresql-16-pgvector`
- `build-essential`
- `libpq-dev`

**[ASSUMPTION: SYSTEM_DEPS]** Tesseract and PostgreSQL 16 are installed via OS package manager. The Dockerfile handles this automatically. Local installs require manual `apt`/`brew`/`choco` execution.

---

## 3. CONFIGURATION

### 3.1 Environment Variables
| Variable | Type | Required | Default | Description |
|----------|------|----------|---------|-------------|
| `DATABASE_URL` | `str` | Yes | `postgresql+asyncpg://user:pass@localhost:5432/legal_engine` | Async SQLAlchemy connection string |
| `OPENROUTER_API_KEY` | `str` | Yes | `""` | OpenRouter authentication token |
| `PRIMARY_MODEL` | `str` | No | `qwen/qwen3.6-plus` | First-attempt LLM identifier |
| `FALLBACK_MODEL_1` | `str` | No | `openai/gpt-5.4-nano` | Secondary fallback |
| `FALLBACK_MODEL_2` | `str` | No | `/openrouter/free` | Ultimate fallback |
| `MAX_RETRIES` | `int` | No | `3` | Max retry attempts per model before fallback |
| `REQUEST_TIMEOUT` | `float` | No | `45.0` | Seconds before HTTP timeout |
| `MAX_FILE_SIZE_MB` | `int` | No | `25` | Hard upload limit |
| `OCR_DPI` | `int` | No | `300` | Standardized image resolution |
| `OCR_JPG_QUALITY` | `int` | No | `84` | JPEG compression quality |
| `EMBEDDING_MODEL` | `str` | No | `text-embedding-3-small` | OpenRouter-compatible embedding model |
| `VECTOR_DIM` | `int` | No | `1536` | Embedding vector dimension |
| `TOP_K_RETRIEVAL` | `int` | No | `12` | Max chunks retrieved per question |
| `DIVERSITY_THRESHOLD` | `float` | No | `0.75` | Cosine similarity threshold for diversity filtering |
| `PIPELINE_TIMEOUT_SEC` | `int` | No | `120` | Hard timeout for full 7-stage execution |
| `LOG_LEVEL` | `str` | No | `INFO` | Python logging level |
| `CORS_ORIGINS` | `str` | No | `["http://localhost:8000"]` | Allowed frontend origins |
| `DISCLAIMER_VERSION` | `str` | No | `v1.0.0` | Current disclaimer version for client validation |

### 3.2 Complete `.env` Example
```env
DATABASE_URL=postgresql+asyncpg://legal_user:secure_password_123@localhost:5432/citizen_db
OPENROUTER_API_KEY=sk-or-v1-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
PRIMARY_MODEL=qwen/qwen3.6-plus
FALLBACK_MODEL_1=openai/gpt-5.4-nano
FALLBACK_MODEL_2=/openrouter/free
MAX_RETRIES=3
REQUEST_TIMEOUT=45.0
MAX_FILE_SIZE_MB=25
OCR_DPI=300
OCR_JPG_QUALITY=84
EMBEDDING_MODEL=text-embedding-3-small
VECTOR_DIM=1536
TOP_K_RETRIEVAL=12
DIVERSITY_THRESHOLD=0.75
PIPELINE_TIMEOUT_SEC=120
LOG_LEVEL=INFO
CORS_ORIGINS=["http://localhost:8000"]
```

---

## 4. DATA LAYER

### 4.1 Exhaustive Schema Definitions (SQLAlchemy 2.0 + DDL Equivalents)

```sql
-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- 1. legal_source
CREATE TABLE legal_source (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_type VARCHAR(50) NOT NULL CHECK (source_type IN ('sgb2', 'sgbx', 'weisung', 'bsg')),
    title VARCHAR(500) NOT NULL,
    jurisdiction VARCHAR(100) NOT NULL DEFAULT 'DE',
    effective_date DATE NOT NULL,
    source_url TEXT NOT NULL,
    version_hash VARCHAR(64) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_source_type_active ON legal_source(source_type, is_active);

-- 2. legal_chunk
CREATE TABLE legal_chunk (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id UUID NOT NULL REFERENCES legal_source(id) ON DELETE CASCADE,
    unit_type VARCHAR(20) NOT NULL CHECK (unit_type IN ('statute', 'paragraph', 'absatz', 'satz')),
    hierarchy_path TEXT NOT NULL, -- e.g., "SGB II > § 31 > Abs. 1 > Satz 2"
    text_content TEXT NOT NULL,
    effective_date DATE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_chunk_source ON legal_chunk(source_id);
CREATE INDEX idx_chunk_hierarchy ON legal_chunk(hierarchy_path);

-- 3. chunk_embedding
CREATE TABLE chunk_embedding (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chunk_id UUID NOT NULL REFERENCES legal_chunk(id) ON DELETE CASCADE,
    embedding vector(1536) NOT NULL,
    model_name VARCHAR(100) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_embedding_vector ON chunk_embedding USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- 4. case_run
CREATE TABLE case_run (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id VARCHAR(100) NOT NULL,
    input_text TEXT NOT NULL,
    status VARCHAR(20) NOT NULL CHECK (status IN ('queued', 'running', 'completed', 'failed')),
    latency_ms INTEGER,
    llm_fallback_chain TEXT[], -- Array of model names used
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_case_session ON case_run(session_id);

-- 5. pipeline_stage_log
CREATE TABLE pipeline_stage_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_run_id UUID NOT NULL REFERENCES case_run(id) ON DELETE CASCADE,
    stage_name VARCHAR(50) NOT NULL CHECK (stage_name IN ('normalization', 'classification', 'decomposition', 'retrieval', 'construction', 'verification', 'generation')),
    input_snapshot JSONB,
    output_snapshot JSONB,
    duration_ms INTEGER NOT NULL,
    error_trace TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_stage_case ON pipeline_stage_log(case_run_id);

-- 6. claim
CREATE TABLE claim (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_run_id UUID NOT NULL REFERENCES case_run(id) ON DELETE CASCADE,
    claim_text TEXT NOT NULL,
    confidence_score FLOAT NOT NULL CHECK (confidence_score BETWEEN 0.0 AND 1.0),
    claim_type VARCHAR(30) NOT NULL CHECK (claim_type IN ('fact', 'interpretation', 'recommendation')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 7. evidence_binding
CREATE TABLE evidence_binding (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    claim_id UUID NOT NULL REFERENCES claim(id) ON DELETE CASCADE,
    chunk_id UUID NOT NULL REFERENCES legal_chunk(id) ON DELETE RESTRICT,
    binding_strength FLOAT NOT NULL CHECK (binding_strength BETWEEN 0.0 AND 1.0),
    quote_excerpt TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX idx_binding_unique ON evidence_binding(claim_id, chunk_id);
```

### 4.2 Migration Strategy
- **Tool:** Alembic with `asyncio` mode.
- **Workflow:** `alembic revision --autogenerate -m "init_schema"` → `alembic upgrade head`.
- **Idempotency:** All `CREATE EXTENSION` and `CREATE INDEX` statements wrapped in `IF NOT EXISTS` or guarded by Alembic ops.
- **Seed Data:** Initial corpus ingestion triggered via `/api/v1/corpus/update` endpoint. No hardcoded SQL seeds to ensure versioned, auditable ingestion.

---

## 5. MODULE SPECIFICATIONS (EXHAUSTIVE)

### 5.1 `app/core/config.py`
**File Path:** `app/core/config.py`
**Public Interface:**
```python
import secrets
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List

SALT_FILE = Path(".secret_salt")

def get_or_create_salt() -> str:
    """Automatically generates and persists a cryptographic salt on first boot."""
    if not SALT_FILE.exists():
        SALT_FILE.write_text(secrets.token_hex(32), encoding="utf-8")
    return SALT_FILE.read_text(encoding="utf-8").strip()

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")
    
    DATABASE_URL: str
    OPENROUTER_API_KEY: str
    PRIMARY_MODEL: str = "qwen/qwen3.6-plus"
    FALLBACK_MODEL_1: str = "openai/gpt-5.4-nano"
    FALLBACK_MODEL_2: str = "/openrouter/free"
    MAX_RETRIES: int = 3
    REQUEST_TIMEOUT: float = 45.0
    MAX_FILE_SIZE_MB: int = 25
    OCR_DPI: int = 300
    OCR_JPG_QUALITY: int = 84
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    VECTOR_DIM: int = 1536
    TOP_K_RETRIEVAL: int = 12
    DIVERSITY_THRESHOLD: float = 0.75
    PIPELINE_TIMEOUT_SEC: int = 120
    LOG_LEVEL: str = "INFO"
    CORS_ORIGINS: List[str] = ["http://localhost:8000"]
    DISCLAIMER_VERSION: str = "v1.0.0"

    @property
    def DISCLAIMER_SALT(self) -> str:
        return get_or_create_salt()

settings = Settings()
```
**Internal Behavior:** Loads `.env` at import time. Validates types. Raises `pydantic.ValidationError` if required keys missing. Provides singleton `settings` instance.
**Error Handling:** `ValidationError` on startup halts app. Caller must catch in `main.py` lifespan.

### 5.2 `app/core/router.py`
**File Path:** `app/core/router.py`
**Public Interface:**
```python
import httpx
from typing import AsyncGenerator, Dict, Any, List
from app.core.config import settings

class OpenRouterClient:
    def __init__(self):
        self.models = [settings.PRIMARY_MODEL, settings.FALLBACK_MODEL_1, settings.FALLBACK_MODEL_2]
        self.client = httpx.AsyncClient(timeout=settings.REQUEST_TIMEOUT)

    async def chat_completion(self, messages: List[Dict[str, str]], temperature: float = 0.1) -> str:
        # Returns final text response or raises RouterExhaustedError
        ...
```
**Internal Behavior:** 
1. Iterates `self.models`.
2. For each model, attempts POST to `https://openrouter.ai/api/v1/chat/completions` with headers `{"Authorization": f"Bearer {settings.OPENROUTER_API_KEY}", "HTTP-Referer": "http://localhost:8000", "X-Title": "LegalEngine"}`.
3. On `429`, `5xx`, or `httpx.TimeoutException`, retries up to `MAX_RETRIES` with exponential backoff (`1s, 2s, 4s`).
4. If all retries fail, logs fallback event, proceeds to next model.
5. Parses `response.json()["choices"][0]["message"]["content"]`.
6. Returns string. If all models exhausted, raises `RouterExhaustedError`.
**Error Handling:** `RouterExhaustedError` (custom). Caller must catch and return HTTP 503 with fallback chain log.

### 5.3 `app/services/ocr.py`
**File Path:** `app/services/ocr.py`
**Public Interface:**
```python
from fastapi import UploadFile
from app.utils.image import standardize_to_jpg
from app.utils.pdf import extract_pdf_text
import pytesseract
from PIL import Image
import io

async def process_document(file: UploadFile) -> str:
    # Returns normalized UTF-8 text
    ...
```
**Internal Behavior:**
1. Validate `file.size < settings.MAX_FILE_SIZE_MB * 1024 * 1024`. Raise `ValueError` if exceeded.
2. Read bytes. If MIME is `application/pdf`:
   - Attempt `extract_pdf_text(bytes)` (Fallback 1: `pdfplumber`).
   - If empty/exception, attempt `PyMuPDF` extraction (Fallback 2).
   - If still empty, convert PDF pages to images via `pdf2image` or `PyMuPDF.get_pixmap()`, pass to `standardize_to_jpg()`, then run `pytesseract.image_to_string()` (Fallback 3).
3. If MIME is `image/*`:
   - Load with `Pillow`.
   - Call `standardize_to_jpg(image)` (resizes to 300dpi, quality 84, strips EXIF).
   - Run `pytesseract.image_to_string()`.
4. Clean text via `app.utils.text.normalize_text()`.
5. Return cleaned string.
**Error Handling:** `ValueError` on size limit. `OCRFailedError` if all fallbacks yield empty text. Caller returns HTTP 400.

### 5.4 `app/core/pipeline.py`
**File Path:** `app/core/pipeline.py`
**Public Interface:**
```python
from dataclasses import dataclass, field
from typing import AsyncGenerator, Dict, Any, List
from app.services.retrieval import retrieve_chunks
from app.services.reasoning import decompose_questions, construct_claims, verify_claims, generate_output

@dataclass
class PipelineState:
    input_text: str
    normalized_text: str = ""
    issues: List[str] = field(default_factory=list)
    questions: List[str] = field(default_factory=list)
    retrieved_chunks: List[Dict[str, Any]] = field(default_factory=list)
    claims: List[Dict[str, Any]] = field(default_factory=list)
    verified_claims: List[Dict[str, Any]] = field(default_factory=list)
    final_output: Dict[str, str] = field(default_factory=dict)

async def run_pipeline(state: PipelineState) -> AsyncGenerator[str, None]:
    # Yields SSE formatted events
    ...
```
**Internal Behavior:**
1. Stage 1: Normalize input (strip whitespace, detect encoding, log).
2. Stage 2: Classify issues via LLM prompt. Parse JSON. Update `state.issues`.
3. Stage 3: Decompose into questions via LLM. Update `state.questions`.
4. Stage 4: Call `retrieve_chunks(state.questions)`. Update `state.retrieved_chunks`.
5. Stage 5: Call `construct_claims(state.retrieved_chunks, state.questions)`. Update `state.claims`.
6. Stage 6: Call `verify_claims(state.claims, state.retrieved_chunks)`. Update `state.verified_claims`.
7. Stage 7: Call `generate_output(state.verified_claims)`. Update `state.final_output`.
8. Yield `data: {"stage": "...", "status": "complete", "payload": ...}` after each stage.
9. Enforce `PIPELINE_TIMEOUT_SEC` via `asyncio.wait_for`.
**Error Handling:** `PipelineTimeoutError` on timeout. `StageExecutionError` on LLM/DB failure. Caller catches, logs to `pipeline_stage_log`, returns HTTP 500 with partial state.

### 5.5 `app/services/reasoning.py`
**File Path:** `app/services/reasoning.py`
**Public Interface:**
```python
from typing import List, Dict, Any
from app.core.router import OpenRouterClient

router = OpenRouterClient()

async def decompose_questions(normalized_text: str) -> List[str]:
    ...
async def construct_claims(chunks: List[Dict], questions: List[str]) -> List[Dict[str, Any]]:
    ...
async def verify_claims(claims: List[Dict], chunks: List[Dict]) -> List[Dict[str, Any]]:
    ...
async def generate_output(verified_claims: List[Dict]) -> Dict[str, str]:
    ...
```
**Internal Behavior:**
- Each function constructs a system prompt enforcing JSON schema output.
- `decompose_questions`: Prompts LLM to extract 3-5 explicit legal questions from text.
- `construct_claims`: For each question, prompts LLM to generate claims with `claim_text`, `confidence_score`, `claim_type`, and `required_chunk_ids`.
- `verify_claims`: Cross-references each claim against provided chunk text. Flags unsupported assertions. Adjusts confidence.
- `generate_output`: Formats verified claims into mandatory 6-part structure. Enforces citation format `§ X Abs. Y Satz Z`.
**Error Handling:** `JSONParseError` if LLM returns malformed JSON. Retries once with stricter prompt. Fails to `StageExecutionError` if second attempt fails.

### 5.6 `app/services/retrieval.py`
**File Path:** `app/services/retrieval.py`
**Public Interface:**
```python
from typing import List, Dict, Any
from app.db.session import get_async_session
from app.db.models import ChunkEmbedding, LegalChunk
from sqlalchemy import select, func
import numpy as np

async def retrieve_chunks(questions: List[str]) -> List[Dict[str, Any]]:
    ...
```
**Internal Behavior:**
1. Generate embeddings for each question via OpenRouter embedding endpoint.
2. For each question embedding, query `chunk_embedding` table using `<->` cosine distance operator.
3. Apply `DIVERSITY_THRESHOLD`: Filter results where `cosine_distance < threshold`.
4. Enforce `TOP_K_RETRIEVAL` per question.
5. Join with `legal_chunk` to fetch `text_content`, `hierarchy_path`, `source_type`.
6. Aggregate, deduplicate by `chunk_id`, sort by relevance.
7. Return list of dicts with metadata.
**Error Handling:** `DBConnectionError` on pool exhaustion. `EmbeddingError` on API failure. Caller logs and returns empty list (graceful degradation).

### 5.7 `app/middleware/disclaimer.py`
**File Path:** `app/middleware/disclaimer.py`
**Public Interface:**
```python
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from app.core.config import settings
import hashlib

class DisclaimerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/api/v1/") and request.method in ("POST", "PUT", "DELETE"):
            ack_header = request.headers.get("X-Disclaimer-Ack")
            if not ack_header or ack_header != settings.DISCLAIMER_VERSION:
                raise HTTPException(
                    status_code=403,
                    detail={"error": "disclaimer_acknowledgment_required", "current_version": settings.DISCLAIMER_VERSION}
                )
        response = await call_next(request)
        return response
```
**Internal Behavior:**
1. Intercepts all mutating API requests.
2. Validates `X-Disclaimer-Ack` against `settings.DISCLAIMER_VERSION`.
3. On mismatch/absence, returns `403` with structured JSON.
4. Logs acknowledgment event to `pipeline_stage_log` via async background task (non-blocking).
5. Passes request to next middleware/route.
**Error Handling:** `HTTPException(403)` on validation failure. Caller (FastAPI) handles JSON response automatically.
```

---

## 6. TESTING STRATEGY

### 6.1 Frameworks & Conventions
- **Framework:** `pytest` + `pytest-asyncio`.
- **Naming:** `test_<module>_<function>_<scenario>.py`
- **Structure:** `tests/unit/` (mocked DB/LLM), `tests/integration/` (ephemeral Postgres, real HTTP client).
- **Coverage Target:** >= 85% line coverage. 100% on `core/router.py`, `services/ocr.py`, `core/pipeline.py`.

### 6.2 Test Categories
1. **Unit Tests:** Isolate pure functions. Mock `httpx`, `pytesseract`, `sqlalchemy`. Verify exact return types, error raising, state mutations.
2. **Integration Tests:** Spin up `TestClient` with `sqlite+aiosqlite` (for schema validation) or `postgresql+asyncpg` (via `testcontainers`). Verify full pipeline execution, SSE streaming, DB writes.
3. **Contract Tests:** Validate LLM prompt/response schemas against `pydantic` models. Ensure JSON parsing never crashes.
4. **Performance Tests:** `pytest-benchmark` for OCR pipeline (<5s for 5MB PDF), retrieval (<50ms for 10k chunks), pipeline timeout enforcement.

### 6.3 Machine-Verifiable Acceptance Criteria
- `pytest tests/unit/test_ocr.py -v` passes 8/8 tests.
- `pytest tests/unit/test_router.py -v` passes 6/6 tests (fallback chain verified).
- `pytest tests/integration/test_pipeline.py -v` passes 4/4 tests (full 7-stage execution, SSE format validated).
- `alembic check` returns zero pending migrations.
- `mypy app/` returns zero type errors.

---

## 7. BUILD, RUN, DEPLOY

### 7.1 Local Development (Ubuntu/WSL/macOS)
```bash
# 1. Clone & Setup
git clone <repo_url> && cd citizen
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# 2. System Dependencies (Ubuntu)
sudo apt update && sudo apt install -y tesseract-ocr libtesseract-dev postgresql-16 postgresql-16-pgvector

# 3. Database Setup
sudo -u postgres psql -c "CREATE USER citizen_user WITH PASSWORD 'secure_password_123';"
sudo -u postgres psql -c "CREATE DATABASE citizen_db OWNER legal_user;"
sudo -u postgres psql -d legal_engine_db -c "CREATE EXTENSION vector;"

# 4. Environment
cp .env.example .env
# Edit .env with actual OPENROUTER_API_KEY

# 5. Migrations
alembic upgrade head

# 6. Run
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 7.2 Docker Compose (Production-Ready Local)
```bash
docker compose up -d --build
# Services: postgres-16, fastapi-app
# Access: http://localhost:8000
# Logs: docker compose logs -f fastapi-app
```

### 7.3 Deployment Checklist
1. Verify `DATABASE_URL` points to persistent volume.
2. Set `LOG_LEVEL=WARNING` in production.
3. Run `alembic upgrade head` before container restart.
4. Ensure `OPENROUTER_API_KEY` has sufficient quota.
5. Monitor `/api/v1/corpus/update` logs for successful ingestion.
6. Verify SSE streaming works behind reverse proxy (Nginx/Caddy) by enabling `proxy_buffering off;` and `X-Accel-Buffering no;`.

---
