# Semantic Version: 0.2.0
#
# Asynchronous database session factory supporting both PostgreSQL (web deployment)
# and SQLite (desktop app). Dialect is detected automatically from the DATABASE_URL.
#
# PostgreSQL: connection pooling with configurable pool size, no overflow.
# SQLite:    single connection, no pooling, WAL mode enabled on startup,
#            busy timeout, and foreign keys enforcement.

from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

DATABASE_URL = settings.DATABASE_URL
IS_SQLITE = DATABASE_URL.startswith("sqlite")

if IS_SQLITE:
    # SQLite: single connection, no pooling, WAL mode.
    engine = create_async_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
    )

    async def _init_sqlite() -> None:
        """Enable WAL mode for the SQLite engine.

        Per-connection settings (foreign_keys, busy_timeout) are applied by a
        connect event listener so they work on every pooled connection.
        """
        async with engine.begin() as conn:
            await conn.execute(text("PRAGMA journal_mode=WAL"))

    # ── Per-connection event listeners ──────────────────────────────────
    # Every new connection from the pool must load the sqlite-vec extension
    # (C4 fix) and apply per-connection PRAGMAs (C5 fix).
    from sqlalchemy import event
    import sqlite_vec

    @event.listens_for(engine.sync_engine, "connect")
    def _init_sqlite_connection(dbapi_conn: Any, connection_record: Any) -> None:  # noqa: ARG001
        """Load sqlite-vec extension and set per-connection PRAGMAs."""
        # C4: load sqlite-vec on every connection so vec_distance_cosine()
        # is available regardless of which pool connection is used.
        dbapi_conn.enable_load_extension(True)
        try:
            sqlite_vec.load(dbapi_conn)
        except Exception:
            pass  # already loaded or unavailable — will surface at query time
        finally:
            dbapi_conn.enable_load_extension(False)

        # C5: per-connection PRAGMAs — foreign_keys and busy_timeout do not
        # persist across connections; journal_mode=WAL is database-level and
        # stays in _init_sqlite().
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

else:
    # PostgreSQL: connection pooling.
    engine = create_async_engine(
        DATABASE_URL,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=0,
        pool_timeout=30,
        pool_recycle=3600,
    )

    async def _init_sqlite() -> None:
        """No-op: PostgreSQL does not need SQLite-specific initialisation."""


async_session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async session scoped to a single request."""
    async with async_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()


# Expose the session factory directly for use in tests and services.
def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the configured async session factory."""
    return async_session_factory
