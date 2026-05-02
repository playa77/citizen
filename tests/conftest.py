"""Global pytest fixtures for Citizen test suite."""

import os

# Provide a valid DATABASE_URL _before_ any import-time evaluation.
# Unit tests that import session.py or config.py will not fail at collection.
# The URL does not need to point at a live server — engine creation is lazy in
# most unit tests (and the session module doesn't call engine.connect() on import).
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://test:test@localhost:5432/test_citizen",
)
