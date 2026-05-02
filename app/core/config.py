import secrets
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
    CORS_ORIGINS: list[str] = ["http://localhost:8000"]
    DISCLAIMER_VERSION: str = "v1.0.0"

    @property
    def DISCLAIMER_SALT(self) -> str:
        return get_or_create_salt()


def _get_settings() -> "Settings":
    """Lazily create the settings singleton to avoid import-time side effects."""
    global _SETTINGS
    if _SETTINGS is None:
        _SETTINGS = Settings()  # type: ignore[call-arg]
    return _SETTINGS


def __getattr__(name: str) -> "Settings":
    if name == "settings":
        return _get_settings()
    raise AttributeError(name)
