"""Integration-suite fixtures.

Version: 1.1.0 | 2026-11-16
"""

# Semantic Version: 1.1.0 | 2026-11-16 — I-08: module-scoped pool reset so
# module-scoped fixtures (TestClient transcripts) never inherit connections
# bound to an earlier event loop (combined unit + integration runs).
# 1.0.0 | 2026-08-25

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


@pytest.fixture(scope="module", autouse=True)
def _fresh_pool_per_module():
    """Drop the pool before any module-scoped fixture runs (I-08).

    The function-scoped dispose below runs *after* module-scoped fixtures are
    set up, so a module fixture that opens a ``TestClient`` (own event loop)
    would otherwise pick up connections the previous test file -- or, in a
    combined ``pytest tests/unit tests/integration`` run, the unit suite --
    left pooled on a different, possibly closed loop. ``close=False`` swaps in
    a fresh pool without awaiting anything on the old connections, which is
    the only safe option from synchronous code and a foreign loop.
    """
    from app.db.session import engine

    engine.sync_engine.dispose(close=False)
    yield
    engine.sync_engine.dispose(close=False)


@pytest.fixture(autouse=True)
async def _dispose_pooled_connections():
    from app.db.session import engine

    await engine.dispose()
    yield
    await engine.dispose()
