# Semantic Version: 0.2.0 | 2026-07-10 — Desktop app support

import secrets
import tomllib
from importlib import metadata as _importlib_metadata
from pathlib import Path

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

    DATABASE_URL: str = "sqlite+aiosqlite:///citizen.db"
    DATA_DIR: str = ""  # Desktop data directory — set by Electron at runtime
    OPENROUTER_API_KEY: str
    EMBEDDING_API_KEY: str = ""  # separate key for embedding calls (falls back to OPENROUTER_API_KEY)
    EMBEDDING_BASE_URL: str = "https://openrouter.ai/api/v1/embeddings"
    PRIMARY_MODEL: str = "deepseek/deepseek-v4-pro"
    FALLBACK_MODEL_1: str = "deepseek/deepseek-v4-pro"
    FALLBACK_MODEL_2: str = "/openrouter/free"
    MAX_RETRIES: int = 1
    REQUEST_TIMEOUT: float = 25.0
    MAX_FILE_SIZE_MB: int = 25
    DB_POOL_SIZE: int = 10  # PostgreSQL only — ignored for SQLite
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
        0.55  # Cosine distance = 1 - cosine similarity. 0.55 means similarity ≥ 0.45.
    )
    MAX_COSINE_DISTANCE_STRICT: float = 0.85
    RETRIEVAL_MODE: str = "per_question"  # "combined" or "per_question" — per_question embeds each question separately, producing better legal-semantic queries
    RETRIEVAL_KEYWORD_FALLBACK: bool = True
    TOP_K_KEYWORD: int = 5
    CORPUS_SOURCES: list[str] = ["sgb2", "sgbx"]
    CORPUS_INGESTION_TIMEOUT_SEC: int = (
        900  # 15 min timeout for full corpus scrape+embed+upsert (WP-014)
    )
    PIPELINE_TIMEOUT_SEC: int = 120
    TRIAGE_TIMEOUT_SEC: float = 20.0
    FINAL_TIMEOUT_SEC: float = 75.0
    EMBEDDING_TIMEOUT_SEC: float = 15.0
    TRIAGE_MODEL: str | None = None
    FINAL_MODEL: str | None = None
    COMBINE_TRIAGE_STAGES: bool = True
    COMBINE_FINAL_STAGES: bool = True
    # Prompt / token budgeting (WP-010)
    MAX_TRIAGE_INPUT_CHARS: int = 8000
    MAX_FINAL_INPUT_CHARS: int = 5000
    MAX_CHUNK_CONTEXT_CHARS: int = 7000
    MAX_CHUNKS_FOR_FINAL: int = 6
    # Calculation check (WP-014) — specialised model for numeric verification
    ENABLE_CALCULATION_CHECK: bool = True
    CALCULATION_MODEL: str | None = None  # None = use PRIMARY_MODEL
    CALCULATION_TIMEOUT_SEC: float = 45.0
    # Rate limiting — 0 = disabled (desktop app, no rate limiting needed)
    RATE_LIMIT_REQUESTS: int = 0
    RATE_LIMIT_WINDOW: int = 60
    # Caching (WP-011)
    ENABLE_CACHE: bool = True
    CACHE_TTL_SEC: int = 86400
    LOG_LEVEL: str = "INFO"
    ENABLE_PROGRESS_STREAM: bool = True  # Whether to stream model output during analysis progress
    DISCLAIMER_VERSION: str = "v0.1.0"
    PSEUDONYMIZATION_ENABLED: bool = True  # WP-30 — pseudonymize PII before LLM calls
    # WP-42 — OCR quality gate
    OCR_QUALITY_ENABLED: bool = True
    OCR_QUALITY_MIN_SCORE: float = 0.3  # refuse to proceed below this
    OCR_QUALITY_WARN_SCORE: float = 0.8  # warn below this
    INFERENCE_PROFILE: str = "eu-avv"  # WP-31 — active inference profile name
    AVV_OVERRIDE: bool = False  # WP-31 — allow non-signed profiles without signed AVV
    # WP-14 — Prüfstand: goldset YAML path and eval results directory.
    # Goldset version change is a config change, not a code change (acceptance criterion).
    GOLDSET_PATH: str = "eval/goldsets/goldset-v0.1.0.yaml"
    EVAL_RESULTS_DIR: str = "eval/results"

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
