"""Global pytest fixtures for Citizen test suite."""

# Semantic Version: 0.6.0 | 2026-11-25 — no configured module preference.
# 0.5.0 | 2026-11-16 — WP-96: DISCLAIMER_VERSION default
# v3.0.0 (follows the config default).
# 0.4.0 | 2026-11-16 — WP-91: DEFAULT_MODULE conftest
# default added; ENABLED_MODULES intentionally left unset (D-037 default).

import contextlib
import os

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_TEST_CONTAINER = None  # module-global so pytest_sessionfinish can stop it


def _ensure_pg_database_url() -> None:
    """Resolve DATABASE_URL before any app import evaluates settings.

    Resolution order (D-026):
    1. A pre-set, non-SQLite DATABASE_URL — used verbatim (CI points this at
       its pgvector service container; developers may point it at any PG 16).
    2. Otherwise start a session-scoped ``pgvector/pgvector:pg16`` container
       via testcontainers and migrate it once, so both unit and integration
       suites run against production-identical SQL with zero manual setup.

    Docker must be available for path 2 (accepted consequence of D-024).
    """
    global _TEST_CONTAINER

    url = os.environ.get("DATABASE_URL", "")
    if url and not url.startswith("sqlite"):
        return

    try:
        from testcontainers.postgres import PostgresContainer
    except ImportError as exc:
        raise RuntimeError(
            "DATABASE_URL is not set (or is a no-longer-supported sqlite URL) "
            "and testcontainers is not installed. Install the [dev] extras or "
            "export DATABASE_URL pointing at a PostgreSQL 16 + pgvector server."
        ) from exc

    container = PostgresContainer(
        "pgvector/pgvector:pg16",
        username="citizen",
        password="citizen",
        dbname="citizen_test",
    )
    container.start()
    _TEST_CONTAINER = container
    # get_connection_url() misplaces the driver argument in testcontainers
    # 4.15 (it lands in the hostname); build the asyncpg URL explicitly.
    os.environ["DATABASE_URL"] = (
        f"postgresql+asyncpg://{container.username}:{container.password}"
        f"@{container.get_container_host_ip()}:{container.get_exposed_port(container.port)}"
        f"/{container.dbname}"
    )

    # Bring the fresh container up to head so integration tests can run
    # without an extra manual step.
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=_PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "Automatic migration of the testcontainer failed:\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )


_ensure_pg_database_url()

# Provide a dummy OpenRouter API key so settings doesn't fail at import.
os.environ.setdefault("OPENROUTER_API_KEY", "sk-or-test-key-000000")

# Set the disclaimer version so integration tests can send the right header.
os.environ.setdefault("DISCLAIMER_VERSION", "v3.5.0")

# WP-62: Dev-instance posture. Tests run with the synthetic-data-only flag
# enabled so the startup assertion in app.main's lifespan passes whenever the
# lifespan is exercised (TestClient context managers, integration tests).
os.environ.setdefault("DEPLOYMENT_MODE", "dev")
os.environ.setdefault("CITIZEN_SYNTHETIC_DATA_ONLY", "true")

# ENABLED_MODULES is deliberately left unset: None activates the D-037 tier
# rule. Deployment enablement does not select a module for a request.


def _preload_module_code() -> None:
    """WP-93: module code lives in ``modules/<id>/*.py`` and is imported by
    the core as ``citizen_modules.<id>.<file>`` (app.modules.content). Preload
    it so module tests can use plain ``from citizen_modules.sozialrecht.<file>
    import ...`` statements."""
    from app.modules.content import import_module_file
    from app.modules.registry import default_modules_root, discover_modules

    for manifest in discover_modules(default_modules_root()).values():
        for py_file in sorted(manifest.path.glob("*.py")):
            import_module_file(manifest, py_file.stem)


_preload_module_code()


def pytest_sessionfinish(session: object, exitstatus: object) -> None:
    """Stop the auto-started container after the session ends."""
    if _TEST_CONTAINER is not None:
        # teardown best-effort; never mask the real test result
        with contextlib.suppress(Exception):
            _TEST_CONTAINER.stop()
