# Semantic Version: 0.8.0 | 2026-11-26 — WP-130: DISCLAIMER_VERSION v3.3.0.
# 0.7.0 | 2026-11-17 — WP-111: UPDATE_TRUST_FILE (update-channel trust anchors).
# 0.6.0 | 2026-11-16 — CR-03: STAGE_MAX_TOKENS (per-stage
# output caps, empty by default).
# 0.5.0 | 2026-11-16 — WP-96: DISCLAIMER_VERSION default
# v0.1.0 → v3.0.0 (aligned with DISCLAIMER_DE/EN.md 3.0.0).
# 0.4.1 | 2026-11-16 — WP-93: GOLDSET_PATH default points into
# modules/sozialrecht/goldset/ (goldsets moved with the module).
# 0.4.0 | 2026-11-16 — WP-91: DEFAULT_MODULE and
# ENABLED_MODULES settings added for the module registry.

import secrets
import tomllib
from importlib import metadata as _importlib_metadata
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

SALT_FILE = Path(".secret_salt")

_SETTINGS: "Settings | None" = None


def get_or_create_salt() -> str:
    """Generate and persist a cryptographic salt on first boot.

    Returns a 64-character hex string. Subsequent calls read the existing file
    without modifying it.
    """
    if not SALT_FILE.exists():
        SALT_FILE.write_text(secrets.token_hex(32), encoding="utf-8")
    return SALT_FILE.read_text(encoding="utf-8").strip()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

    # PostgreSQL + pgvector is the only supported backend (D-024).
    DATABASE_URL: str = "postgresql+asyncpg://citizen:citizen@localhost:5432/citizen"
    OPENROUTER_API_KEY: str
    # Separate key for embedding calls (falls back to OPENROUTER_API_KEY).
    EMBEDDING_API_KEY: str = ""
    EMBEDDING_BASE_URL: str = "https://openrouter.ai/api/v1/embeddings"
    PRIMARY_MODEL: str = "deepseek/deepseek-v4-pro"
    FALLBACK_MODEL_1: str = "deepseek/deepseek-v4-flash"
    FALLBACK_MODEL_2: str = "deepseek/deepseek-v4-flash"
    MAX_RETRIES: int = 3
    REQUEST_TIMEOUT: float = 25.0
    MAX_FILE_SIZE_MB: int = 25
    DB_POOL_SIZE: int = 10  # asyncpg connection pool size
    OCR_DPI: int = 300
    OCR_JPG_QUALITY: int = 84
    OCR_CONTRAST_FACTOR: float = 2.0
    OCR_BW_THRESHOLD: int = 128
    OCR_SYNTHESIS_MODEL: str = (
        "deepseek/deepseek-v4-pro"  # LLM for comparing & correcting dual-OCR results
    )
    # OCR performance controls (WP-012)
    ENABLE_OCR_LLM_SYNTHESIS: bool = (
        False  # If False, skip LLM synthesis and combine OCR outputs locally
    )
    MAX_OCR_SYNTHESIS_CHARS: int = 6000  # Max chars of combined OCR text sent to LLM synthesis
    OCR_MAX_PAGES: int = 10  # Max PDF pages processed by image-based OCR; 0 = unlimited
    EMBEDDING_MODEL: str = "openai/text-embedding-3-small"
    VECTOR_DIM: int = 1536
    TOP_K_RETRIEVAL: int = 10
    MAX_COSINE_DISTANCE: float = (
        0.65  # Cosine distance = 1 - cosine similarity. 0.65 means similarity ≥ 0.35.
    )
    MAX_COSINE_DISTANCE_STRICT: float = 0.85
    # "combined" or "per_question" — per_question embeds each question
    # separately, producing better legal-semantic queries.
    RETRIEVAL_MODE: str = "per_question"
    RETRIEVAL_KEYWORD_FALLBACK: bool = True
    TOP_K_KEYWORD: int = 5
    # Unconfigured means no ingestion sources (D-070). Runtime selection and
    # one-shot job overrides can supply explicit sources.
    CORPUS_SOURCES: list[str] | None = None
    # 30 min timeout for full corpus scrape+embed+upsert (WP-014, increased
    # for large corpora).
    CORPUS_INGESTION_TIMEOUT_SEC: int = 1800
    # Number of texts per batch embedding request (OpenRouter batch API;
    # OpenAI limit is 2048).
    EMBEDDING_BATCH_SIZE: int = 64
    EMBEDDING_BATCH_CONCURRENCY: int = 4  # Max simultaneous batch embedding requests
    # --- Timeout budget -------------------------------------------------------
    # The chain must satisfy: sum(per-call) < PIPELINE_TIMEOUT < nginx timeout.
    #
    # Realistic LLM call durations (deepseek-v4-pro on complex legal analysis):
    #   - triage/classification+decomposition: ~20-40s
    #   - grounded_answer (construction+verification+generation): ~60-120s
    #   - adversarial_review: ~60-120s
    #   - calculation_check: ~30-60s
    #
    # Budget: 45 + 150 + 150 + 90 = 435s worst case < 480s pipeline < 540s nginx.
    # The per-call timeouts are HARD limits enforced via asyncio.wait_for in
    # router.py (httpx's read timeout does NOT fire on streaming responses
    # because each chunk resets the timer — see D-017).
    PIPELINE_TIMEOUT_SEC: int = 480  # 8 min overall pipeline budget (was 120 — ludicrous)
    TRIAGE_TIMEOUT_SEC: float = 60.0  # was 20.0 — too short for complex triage
    FINAL_TIMEOUT_SEC: float = 180.0  # was 75 — too short for grounded_answer + adversarial_review
    EMBEDDING_TIMEOUT_SEC: float = 30.0  # was 15.0
    CALCULATION_TIMEOUT_SEC: float = 90.0  # was 45.0
    TRIAGE_MODEL: str | None = None
    FINAL_MODEL: str | None = None
    COMBINE_TRIAGE_STAGES: bool = True
    COMBINE_FINAL_STAGES: bool = True
    # Prompt / token budgeting (WP-010)
    MAX_TRIAGE_INPUT_CHARS: int = 8000
    MAX_FINAL_INPUT_CHARS: int = 5000
    MAX_CHUNK_CONTEXT_CHARS: int = 7000
    MAX_CHUNKS_FOR_FINAL: int = 12
    # Output-token caps per prompt stage (CR-03), e.g.
    # {"grounded_answer": 6000, "adversarial_review": 4000}. Empty = no cap
    # (provider default). Calibrate from the completion_tokens the router logs
    # per call (p99 x 1.5) before setting; a capped response that stays
    # truncated after one doubled retry fails the stage instead of being parsed.
    STAGE_MAX_TOKENS: dict[str, int] = {}
    # Calculation check (WP-014) — specialised model for numeric verification
    ENABLE_CALCULATION_CHECK: bool = True
    CALCULATION_MODEL: str | None = None  # None = use PRIMARY_MODEL
    # Rate limiting — 0 = disabled (RateLimitMiddleware is currently NOT
    # mounted in app.main; values kept for optional enablement)
    RATE_LIMIT_REQUESTS: int = 0
    RATE_LIMIT_WINDOW: int = 60
    # Caching (WP-011)
    ENABLE_CACHE: bool = True
    CACHE_TTL_SEC: int = 86400
    LOG_LEVEL: str = "INFO"
    ENABLE_PROGRESS_STREAM: bool = True  # Whether to stream model output during analysis progress
    # Ack version = "v" + DISCLAIMER_DE/EN.md document version (WP-96, D-059);
    # bump together with the documents, never on its own.
    DISCLAIMER_VERSION: str = "v3.3.0"
    PSEUDONYMIZATION_ENABLED: bool = True  # WP-30 — pseudonymize PII before LLM calls
    # WP-42 — OCR quality gate
    OCR_QUALITY_ENABLED: bool = True
    OCR_QUALITY_MIN_SCORE: float = 0.3  # refuse to proceed below this
    OCR_QUALITY_WARN_SCORE: float = 0.8  # warn below this
    INFERENCE_PROFILE: str = "eu-avv"  # WP-31 — active inference profile name
    AVV_OVERRIDE: bool = False  # WP-31 — allow non-signed profiles without signed AVV
    # --- Deployment posture (WP-62 / WP-66, D-019) ----------------------------
    # dev: author-only testing with synthetic data only (Art. 2(8) AI Act)
    # self: author-only use on the author's own real Bescheide (personal use)
    # provider: any third party can obtain an analysis (author becomes provider)
    DEPLOYMENT_MODE: Literal["dev", "self", "provider"] = "dev"
    # Dev-instance hardening (WP-62): in dev mode the instance refuses to start
    # unless this flag is explicitly true, and document uploads without a
    # synthetic/goldset tag are rejected.
    CITIZEN_SYNTHETIC_DATA_ONLY: bool = False
    # WP-14 — Prüfstand: goldset YAML path and eval results directory.
    # Goldset version change is a config change, not a code change (acceptance criterion).
    # WP-93: goldsets ship inside their module; /api/v1/goldset* stays the
    # Sozialrecht alias until /api/v2 (ARCHITECTURE.md § 5), hence the
    # module path as default. Per-module goldsets: manifest `goldset` (WP-95).
    GOLDSET_PATH: str = "modules/sozialrecht/goldset/goldset-v0.1.0.yaml"
    EVAL_RESULTS_DIR: str = "eval/results"
    # --- Modules (WP-91, D-036/D-037) ----------------------------------------
    # Explicit enablement list. Unset (None) → the tier rule of D-037 applies:
    # dev/self enable every installed module of tier experimental|verified,
    # provider only verified; community is never enabled implicitly.
    ENABLED_MODULES: list[str] | None = None
    # --- Module platform (P11) ----------------------------------------------
    # WP-111: trust anchors (public keys) of the signed module update channel.
    # Relative paths resolve against the repository root. The shipped file is
    # empty: no feed verifies until an operator adds a published key.
    UPDATE_TRUST_FILE: str = "config/update-trust.yaml"

    @property
    def DISCLAIMER_SALT(self) -> str:
        return get_or_create_salt()


def _get_settings() -> "Settings":
    """Lazily create the settings singleton to avoid import-time side effects."""
    global _SETTINGS
    if _SETTINGS is None:
        _SETTINGS = Settings()  # type: ignore[call-arg]
    return _SETTINGS


def get_app_version() -> str:
    """Return the canonical application version from package metadata (e.g. '0.1.0').

    Prefers importlib.metadata (works when the package is installed via pip).
    Falls back to reading pyproject.toml directly (useful during development
    before the package has been installed).
    """
    try:
        return _importlib_metadata.version("citizen")
    except _importlib_metadata.PackageNotFoundError:
        pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        return str(data["project"]["version"])


def get_app_version_tag() -> str:
    """Return the application version with 'v' prefix (e.g. 'v0.1.0')."""
    return f"v{get_app_version()}"


def __getattr__(name: str) -> "Settings":
    if name == "settings":
        return _get_settings()
    raise AttributeError(name)
