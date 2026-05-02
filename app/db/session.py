from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=0,
    pool_timeout=30,
    pool_recycle=3600,
)

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
