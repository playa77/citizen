"""Unit tests for app.core.config — WP-002.

Acceptance criteria covered:
- Missing DATABASE_URL raises pydantic.ValidationError.
- get_or_create_salt() creates a 64-char hex string.
- Salt is idempotent across imports.
- .secret_salt is gitignored.
- settings singleton loads with valid env.
"""

import re

import pytest
from pydantic import ValidationError


@pytest.fixture(autouse=True)
def _isolate_salt_file(tmp_path, monkeypatch):
    """Redirect SALT_FILE to a per-test temp path so tests don't pollute each other."""
    # We patch the module-level SALT_FILE *before* any test function runs.
    # Import the raw module — we deliberately avoid importing `settings` here
    # because that would eagerly create the singleton and potentially fail.
    import app.core.config as config_mod

    monkeypatch.setattr(config_mod, "SALT_FILE", tmp_path / ".secret_salt")
    # Reset the cached singleton so each test gets a clean slate.
    config_mod._SETTINGS = None  # type: ignore[attr-defined]
    yield


# ── get_or_create_salt ─────────────────────────────────────────────────


class TestGetOrCreateSalt:
    def test_creates_64_char_hex_string(self, tmp_path, monkeypatch, _isolate_salt_file):
        from app.core.config import get_or_create_salt

        result = get_or_create_salt()

        import app.core.config as config_mod

        assert config_mod.SALT_FILE.exists()
        assert len(result) == 64
        assert re.fullmatch(r"[0-9a-f]+", result)

    def test_idempotent_reads_existing(self, _isolate_salt_file):
        from app.core.config import get_or_create_salt

        first = get_or_create_salt()
        second = get_or_create_salt()

        assert first == second

    def test_does_not_overwrite_existing_salt(self, _isolate_salt_file):
        import app.core.config as config_mod
        from app.core.config import get_or_create_salt

        # Pre-write a known salt
        existing = "a" * 64
        config_mod.SALT_FILE.write_text(existing)

        result = get_or_create_salt()

        assert result == existing

    def test_returns_stripped_content(self, _isolate_salt_file):
        import app.core.config as config_mod
        from app.core.config import get_or_create_salt

        # File with trailing newline
        raw = "b" * 64 + "\n"
        config_mod.SALT_FILE.write_text(raw)

        result = get_or_create_salt()

        assert result == "b" * 64
        assert len(result) == 64


# ── Settings validation ────────────────────────────────────────────────


class TestSettingsValidation:
    def test_missing_database_url_raises_validation_error(self, monkeypatch, _isolate_salt_file):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

        from app.core.config import Settings

        with pytest.raises(ValidationError) as exc_info:
            Settings()

        errors = str(exc_info.value)
        assert "DATABASE_URL" in errors

    def test_valid_env_creates_settings(self, tmp_path, _isolate_salt_file, monkeypatch):
        from app.core.config import Settings

        # Override the host env DATABASE_URL (set by conftest.py)
        # so the _env_file value is the only source.
        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost:5432/test")
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

        env_file = tmp_path / ".env"
        env_file.write_text(
            "DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/test\n"
            "OPENROUTER_API_KEY=sk-test-key\n",
            encoding="utf-8",
        )

        s = Settings(_env_file=env_file)

        assert s.DATABASE_URL == "postgresql+asyncpg://user:pass@localhost:5432/test"
        assert s.OPENROUTER_API_KEY == "sk-test-key"
        assert s.PRIMARY_MODEL == "qwen/qwen3.6-plus"
        assert s.MAX_FILE_SIZE_MB == 25
        assert s.PIPELINE_TIMEOUT_SEC == 120

    def test_default_values_applied(self, tmp_path, _isolate_salt_file, monkeypatch):
        from app.core.config import Settings

        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@h/d")
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

        env_file = tmp_path / ".env"
        env_file.write_text(
            "DATABASE_URL=postgresql+asyncpg://u:p@h/d\n" "OPENROUTER_API_KEY=sk-x\n",
            encoding="utf-8",
        )

        s = Settings(_env_file=env_file)

        assert s.MAX_RETRIES == 3
        assert s.REQUEST_TIMEOUT == 45.0
        assert s.OCR_DPI == 300
        assert s.OCR_JPG_QUALITY == 84
        assert s.TOP_K_RETRIEVAL == 12
        assert s.DIVERSITY_THRESHOLD == 0.75
        assert s.LOG_LEVEL == "INFO"
        assert s.DISCLAIMER_VERSION == "v1.0.0"

    def test_cors_origins_parses_json_list(self, tmp_path, _isolate_salt_file, monkeypatch):
        from app.core.config import Settings

        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@h/d")
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

        env_file = tmp_path / ".env"
        env_file.write_text(
            "DATABASE_URL=postgresql+asyncpg://u:p@h/d\n"
            "OPENROUTER_API_KEY=sk-x\n"
            'CORS_ORIGINS=["http://localhost:3000","http://localhost:8000"]\n',
            encoding="utf-8",
        )

        s = Settings(_env_file=env_file)

        assert s.CORS_ORIGINS == ["http://localhost:3000", "http://localhost:8000"]

    def test_disclaimer_salt_triggers_salt_creation(
        self, tmp_path, _isolate_salt_file, monkeypatch
    ):
        from app.core.config import Settings

        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@h/d")
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

        env_file = tmp_path / ".env"
        env_file.write_text(
            "DATABASE_URL=postgresql+asyncpg://u:p@h/d\n" "OPENROUTER_API_KEY=sk-x\n",
            encoding="utf-8",
        )

        s = Settings(_env_file=env_file)
        salt = s.DISCLAIMER_SALT

        assert len(salt) == 64

    def test_settings_lazy_load_with_env_vars(self, monkeypatch):
        """Import the module-level `settings` singleton when env vars are set."""
        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@h/d")
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-x")

        import app.core.config as config_mod

        config_mod._SETTINGS = None  # type: ignore[attr-defined]

        s = config_mod.settings

        assert s.DATABASE_URL == "postgresql+asyncpg://u:p@h/d"
        assert s.OPENROUTER_API_KEY == "sk-x"


# ── .gitignore verification ────────────────────────────────────────────


class TestGitignore:
    def test_secret_salt_in_gitignore(self):
        """Verify .secret_salt is explicitly listed in .gitignore."""
        from pathlib import Path

        gitignore_path = Path(".gitignore")
        assert gitignore_path.exists(), ".gitignore not found"

        content = gitignore_path.read_text(encoding="utf-8")
        assert ".secret_salt" in content, ".secret_salt must be in .gitignore"
