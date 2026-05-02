"""Unit tests for app.db.session — WP-003."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_async_session


async def test_session_yields() -> None:
    """Verify that get_async_session yields a valid AsyncSession."""
    async for session in get_async_session():
        assert isinstance(session, AsyncSession)
        assert session.get_bind() is not None
