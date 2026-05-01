# DOCUMENT 3: ROADMAP
**System:** Citizen (v1.0)
**Execution Paradigm:** Atomic Work Packages, Machine-Verifiable Acceptance Criteria
**Alignment:** Strictly consistent with Documents 1 & 2.

---

## 1. ENGINEERING STANDARDS

### 1.1 Toolchain & Formatting
- **Language:** Python 3.11+
- **Formatter:** `ruff format` (line length: 100, target-version: py311)
- **Linter:** `ruff check` (enable: E, F, W, I, UP, B, C4, SIM, RUF)
- **Type Checker:** `mypy --strict --ignore-missing-imports`
- **Test Runner:** `pytest -v --tb=short --cov=app --cov-report=term-missing`
- **Commit Format:** Conventional Commits (`feat:`, `fix:`, `chore:`, `test:`, `docs:`). Max 72 char subject.
- **Definition of Done (DoD):**
  1. Code passes `ruff check`, `ruff format --check`, `mypy`.
  2. Unit/Integration tests pass locally with `pytest`.
  3. Coverage for modified files >= 85%.
  4. No unhandled exceptions in logs.
  5. All environment variables documented in `.env.example`.

### 1.2 Branching & Review
- **Main Branch:** `main` (protected, requires passing CI).
- **Feature Branches:** `feat/<wp-id>-<short-desc>`.
- **Merge Strategy:** Squash & Merge after CI passes.
- **CI Pipeline:** `ruff` → `mypy` → `pytest` → `docker build` (on push to PR).

---

## 2. MILESTONES

| Milestone | Description | Testable System State |
|-----------|-------------|------------------------|
| **M1: Foundation & Infrastructure** | Project scaffolding, dependency management, Docker/DB setup, config validation. | `docker compose up` starts FastAPI + Postgres. `/health` returns 200. `.env` loads correctly. |
| **M2: Data Layer & Corpus Ingestion** | SQLAlchemy models, Alembic migrations, `pgvector` setup, scraper/chunker implementation. | `alembic upgrade head` succeeds. `/api/v1/corpus/update` populates DB with 100+ hierarchical chunks. |
| **M3: OCR & Document Processing** | Local OCR pipeline, PDF fallback chain, JPG standardization, text normalization. | Uploading a 5MB scanned PDF returns clean UTF-8 text in <5s. Fallbacks trigger correctly on malformed files. |
| **M4: LLM Router & Reasoning Engine** | OpenRouter client, fallback chain, 7-stage pipeline orchestrator, prompt engineering. | Pipeline executes 7 stages sequentially. Fallback chain logs correctly. JSON parsing never crashes. |
| **M5: API, UI & Integration** | FastAPI routes, SSE streaming, static frontend, end-to-end pipeline wiring. | `/api/v1/analyze` streams progress. UI renders 6-part output. Full run completes in <120s. |
| **M6: Testing, Validation & Release** | Comprehensive test suite, performance benchmarks, security hardening, v1.0 tag. | `pytest` passes 100%. Coverage >= 85%. `docker compose` runs cleanly. MIT license applied. |

---

## 3. WORK PACKAGES (WP)

### WP-001: Project Scaffolding & Dependency Lock
**Scope:** Initialize repo, `pyproject.toml`, `.env.example`, `Dockerfile`, `docker-compose.yml`.
**Files Created/Modified:** `pyproject.toml`, `.env.example`, `Dockerfile`, `docker-compose.yml`, `README.md`
**Acceptance Criteria:**
- `docker compose up -d` exits with code 0.
- `docker compose ps` shows `postgres-16` and `fastapi-app` running.
- `cat .env.example | wc -l` >= 15.

### WP-002: Configuration, Settings Validation & Auto-Salting
**Scope:** Implement `app/core/config.py` with `pydantic-settings`. Implement zero-friction `.secret_salt` generation.
**Files Created/Modified:** `app/__init__.py`, `app/core/__init__.py`, `app/core/config.py`, `.gitignore`
**Signatures:** `def get_or_create_salt() -> str: ...`, `class Settings(BaseSettings): ...`
**Acceptance Criteria:**
- `python -c "from app.core.config import settings; print(settings.DATABASE_URL)"` prints valid string.
- Missing `DATABASE_URL` raises `pydantic.ValidationError`.
- On first import, a `.secret_salt` file is created containing a 64-character hex string.
- Subsequent imports read the existing `.secret_salt` file without modifying it.
- `.secret_salt` is explicitly added to `.gitignore`.
- `ruff check app/core/config.py` returns 0.

### WP-003: Database Engine & Session Factory
**Scope:** Async SQLAlchemy engine, scoped session provider, connection pooling.
**Files Created/Modified:** `app/db/__init__.py`, `app/db/session.py`
**Signatures:** `async def get_async_session() -> AsyncGenerator[AsyncSession, None]: ...`
**Acceptance Criteria:**
- `pytest tests/unit/test_session.py::test_session_yields` passes.
- `mypy app/db/session.py` returns 0 errors.
- Connection pool size matches `settings.DB_POOL_SIZE` (default 10).

### WP-004: ORM Models & Alembic Initialization
**Scope:** Declarative models matching Doc 2 schema. Alembic `env.py` configured for async.
**Files Created/Modified:** `app/db/models.py`, `alembic.ini`, `alembic/env.py`, `alembic/versions/001_init_schema.py`
**Signatures:** `class LegalSource(Base): ...`, `class LegalChunk(Base): ...`, `class ChunkEmbedding(Base): ...`
**Acceptance Criteria:**
- `alembic upgrade head` executes without error.
- `psql -d legal_engine_db -c "\dt"` lists 7 tables.
- `pgvector` extension verified via `SELECT extname FROM pg_extension WHERE extname='vector';`.

### WP-005: Corpus Scraper & Hierarchical Chunker
**Scope:** Fetch `gesetze-im-internet.de` XML, parse structure, chunk by `§/Abs/Satz`, generate metadata.
**Files Created/Modified:** `app/services/corpus.py`, `app/utils/text.py`
**Signatures:** `async def scrape_and_chunk(source_type: str) -> List[Dict[str, Any]]: ...`
**Acceptance Criteria:**
- `pytest tests/unit/test_chunker.py::test_hierarchical_split` passes (verifies `SGB II > § 31 > Abs. 1 > Satz 2` path).
- Output contains `unit_type`, `hierarchy_path`, `text_content`.
- `ruff check app/services/corpus.py` returns 0.

### WP-006: Embedding Generation & Vector Upsert
**Scope:** Generate embeddings via OpenRouter, upsert to `chunk_embedding` table with `ON CONFLICT`.
**Files Created/Modified:** `app/services/corpus.py` (extend), `app/core/router.py` (add embedding method)
**Signatures:** `async def generate_embeddings(chunks: List[Dict]) -> List[Dict]: ...`, `async def upsert_chunks(session: AsyncSession, chunks: List[Dict]) -> None: ...`
**Acceptance Criteria:**
- `pytest tests/integration/test_corpus.py::test_vector_upsert` passes.
- `SELECT count(*) FROM chunk_embedding;` > 0 after manual trigger.
- `IVFFlat` index verified via `\di+ idx_embedding_vector`.

### WP-007: PDF Text Extraction Fallbacks
**Scope:** Implement `pdfplumber` → `PyMuPDF` fallback chain.
**Files Created/Modified:** `app/utils/pdf.py`
**Signatures:** `def extract_pdf_text(file_bytes: bytes) -> str: ...`
**Acceptance Criteria:**
- `pytest tests/unit/test_pdf.py::test_fallback_chain` passes (mocks empty `pdfplumber`, verifies `PyMuPDF` triggers).
- Returns clean UTF-8 string for digitally generated PDFs.
- `mypy app/utils/pdf.py` returns 0 errors.

### WP-008: Image Standardization & Tesseract OCR
**Scope:** Convert images/PDF pages to 300dpi JPG (quality 84, strip EXIF), run `pytesseract`.
**Files Created/Modified:** `app/utils/image.py`, `app/services/ocr.py`
**Signatures:** `def standardize_to_jpg(image: Image.Image) -> Image.Image: ...`, `async def process_document(file: UploadFile) -> str: ...`
**Acceptance Criteria:**
- `pytest tests/unit/test_ocr.py::test_jpg_standardization` passes (verifies DPI=300, quality=84, no EXIF).
- `pytest tests/unit/test_ocr.py::test_tesseract_fallback` passes.
- Processing a 5MB scanned PDF completes in <5s.

### WP-009: OpenRouter Client & Deterministic Fallback
**Scope:** Implement `OpenRouterClient` with retry/backoff/fallback chain.
**Files Created/Modified:** `app/core/router.py`
**Signatures:** `class OpenRouterClient: ...`, `async def chat_completion(self, messages: List[Dict], temperature: float = 0.1) -> str: ...`
**Acceptance Criteria:**
- `pytest tests/unit/test_router.py::test_fallback_chain` passes (mocks 429 on primary, verifies fallback 1 triggers).
- `pytest tests/unit/test_router.py::test_exhaustion_error` passes (mocks all failures, verifies `RouterExhaustedError`).
- Logs contain `fallback_event` with model names.

### WP-010: 7-Stage Pipeline Orchestrator
**Scope:** Implement `PipelineState`, stage execution loop, SSE streaming, timeout enforcement.
**Files Created/Modified:** `app/core/pipeline.py`
**Signatures:** `@dataclass class PipelineState: ...`, `async def run_pipeline(state: PipelineState) -> AsyncGenerator[str, None]: ...`
**Acceptance Criteria:**
- `pytest tests/unit/test_pipeline.py::test_stage_sequence` passes (verifies order: normalization → classification → ... → generation).
- `asyncio.wait_for(run_pipeline(state), timeout=120)` raises `TimeoutError` correctly.
- SSE format matches `data: {"stage": "...", "status": "complete", "payload": ...}\n\n`.

### WP-011: Reasoning Engine Prompts & JSON Parsing
**Scope:** Implement `decompose_questions`, `construct_claims`, `verify_claims`, `generate_output`.
**Files Created/Modified:** `app/services/reasoning.py`
**Signatures:** `async def decompose_questions(normalized_text: str) -> List[str]: ...`, `async def construct_claims(...) -> List[Dict]: ...`, `async def verify_claims(...) -> List[Dict]: ...`, `async def generate_output(...) -> Dict[str, str]: ...`
**Acceptance Criteria:**
- `pytest tests/unit/test_reasoning.py::test_json_parsing` passes (mocks malformed LLM output, verifies retry).
- Output contains mandatory keys: `sachverhalt`, `rechtliche_wuerdigung`, `ergebnis`, `handlungsempfehlung`, `entwurf`, `unsicherheiten`.
- `mypy app/services/reasoning.py` returns 0 errors.

### WP-012: Retrieval Engine & Diversity Constraints
**Scope:** Query `pgvector`, apply cosine distance threshold, enforce top-k diversity, join metadata.
**Files Created/Modified:** `app/services/retrieval.py`
**Signatures:** `async def retrieve_chunks(questions: List[str]) -> List[Dict[str, Any]]: ...`
**Acceptance Criteria:**
- `pytest tests/integration/test_retrieval.py::test_diversity_filter` passes (verifies `cosine_distance < 0.75` filter).
- Returns exactly `TOP_K_RETRIEVAL` chunks per question.
- `SELECT count(*) FROM chunk_embedding WHERE embedding <-> query < 0.75;` matches returned count.

### WP-013: FastAPI Routes & Payload Validation
**Scope:** Implement `/api/v1/ingest`, `/api/v1/analyze`, `/api/v1/corpus/update`.
**Files Created/Modified:** `app/api/routes/ingest.py`, `app/api/routes/analyze.py`, `app/api/routes/corpus.py`, `app/main.py`
**Signatures:** `@router.post("/ingest") async def ingest(file: UploadFile): ...`, `@router.post("/analyze") async def analyze(payload: AnalyzeRequest): ...`
**Acceptance Criteria:**
- `pytest tests/integration/test_api_routes.py::test_ingest_endpoint` passes (returns 200 with text).
- `pytest tests/integration/test_api_routes.py::test_analyze_endpoint` passes (returns 200 with 6-part JSON).
- `curl -X POST http://localhost:8000/api/v1/ingest -F "file=@test.pdf"` returns valid JSON.

### WP-014: Static Frontend & SSE Client
**Scope:** Build `index.html`, `app.js`, `style.css`. Handle upload, progress streaming, output rendering.
**Files Created/Modified:** `static/index.html`, `static/app.js`, `static/style.css`
**Signatures:** `function handleUpload(file) { ... }`, `function streamAnalysis(sessionId) { ... }`
**Acceptance Criteria:**
**Acceptance Criteria:**
- `http://localhost:8000` loads without console errors.
- Modal blocks all interaction until checkbox is checked and "Acknowledge" clicked.
- `localStorage.getItem("legal_disclaimer_accepted_v1")` returns valid JSON with `version`, `timestamp`, `ip_hash`.
- `fetch("/api/v1/ingest")` without `X-Disclaimer-Ack` header returns `403` with exact error payload.
- `fetch("/api/v1/ingest")` with correct header returns `200` and proceeds.
- Version mismatch triggers modal re-render.
- Final output renders exactly 6 sections with correct headings.

### WP-015: End-to-End Integration & Performance Validation
**Scope:** Wire all components, run full pipeline, verify latency, log audit trails.
**Files Created/Modified:** `tests/integration/test_pipeline.py`, `app/main.py` (middleware)
**Signatures:** `async def test_full_pipeline_execution(): ...`
**Acceptance Criteria:**
- `pytest tests/integration/test_pipeline.py::test_full_pipeline_execution` passes.
- Total latency < 120s for 3-page scanned PDF.
- `pipeline_stage_log` table contains 7 rows per run.
- `claim` and `evidence_binding` tables populated correctly.
- `pytest tests/integration/test_pipeline.py::test_disclaimer_enforcement` passes (verifies full pipeline only executes post-acknowledgment).
- `pipeline_stage_log` contains exactly 8 rows per run (7 stages + 1 disclaimer_ack).

### WP-016: Security Hardening & v1.0 Release
**Scope:** Apply CORS, rate limiting (local), logging, MIT license, Docker optimization, release tag.
**Files Created/Modified:** `app/main.py`, `Dockerfile`, `LICENSE`, `README.md`
**Signatures:** `app.add_middleware(CORSMiddleware, ...)`
**Acceptance Criteria:**
- `curl -I http://localhost:8000` returns `Access-Control-Allow-Origin: http://localhost:8000`.
- `docker build -t citizen:v1.0 .` succeeds.
- `git tag v1.0 && git push origin v1.0` succeeds.
- `pytest --cov=app` reports >= 85% coverage.

### WP-017: Disclaimer Middleware & Consent Enforcement
**Scope:** Implement `DisclaimerMiddleware`, integrate into FastAPI app, add `/api/v1/meta/disclaimer/*` endpoints, wire logging.
**Files Created/Modified:** `app/middleware/disclaimer.py`, `app/api/routes/meta.py`, `app/main.py`
**Signatures:** `class DisclaimerMiddleware(BaseHTTPMiddleware): ...`, `@router.get("/meta/disclaimer/version")`, `@router.get("/meta/disclaimer/text")`
**Acceptance Criteria:**
- `pytest tests/unit/test_middleware.py::test_disclaimer_block` passes (verifies 403 on missing header).
- `pytest tests/unit/test_middleware.py::test_disclaimer_pass` passes (verifies 200 on valid header).
- `curl -H "X-Disclaimer-Ack: v1.0.0" http://localhost:8000/api/v1/ingest` returns 200.
- `pipeline_stage_log` contains `disclaimer_ack` entry with correct version/timestamp.
- `ruff check app/middleware/disclaimer.py` returns 0.

---

## 4. FUTURE WORK (POST-v1.0)

| Feature | Trigger Condition | Architectural Impact |
|---------|-------------------|----------------------|
| **Automated Corpus Updates** | User base > 100, legal amendment frequency > 2/month | Add `APScheduler` cron job, implement diff-based chunk invalidation, add `source_version` tracking. |
| **Multi-Tenant RBAC & Auth** | Monetization phase, SaaS deployment | Add `user`, `role`, `tenant` tables. Implement JWT middleware. Scope `case_run` by `tenant_id`. |
| **Persistent Case History UI** | User feedback requests > 50% | Enable `case_run` persistence in UI. Add search/filter endpoints. Implement data retention policies. |
| **Procedural Timeline Engine** | Expansion to SGB III/XII | Add `deadline`, `event_type`, `trigger_date` models. Integrate calendar sync. Add escalation alerts. |
| **Local LLM Support (Ollama/vLLM)** | Privacy compliance requirements | Add `LocalLLMClient` abstraction. Implement model routing based on `provider` config. Optimize VRAM usage. |
| **Semi-Automated Case Tracking** | Lawyer/Professional tier launch | Add `case_status`, `agency_response`, `follow_up_date` fields. Implement webhook/email polling. |

---
