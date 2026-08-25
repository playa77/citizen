"""Integration-suite fixtures.

Version: 1.0.0 | 2026-08-25
"""

# Semantic Version: 1.0.0

import pytest

# ---------------------------------------------------------------------------
# DB isolation
# ---------------------------------------------------------------------------
# app.db.session creates its asyncpg engine at import time; asyncpg binds
# connections to the event loop they were created on, while pytest-asyncio
# runs each test on a fresh loop. Disposing pooled connections around every
# test forces a fresh connection (and loop binding) for the next one.
# Without this, any second DB-touching test fails with
# "another operation is in progress" / "Future attached to a different loop".
#
# NOTE: deliberately scoped to the integration suite — an async autouse
# fixture in the shared conftest changes pytest-asyncio's handling of the
# unit suite's patch().start() patterns and breaks otherwise-green tests.


@pytest.fixture(autouse=True)
async def _dispose_pooled_connections():
    from app.db.session import engine

    await engine.dispose()
    yield
    await engine.dispose()
