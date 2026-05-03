"""Alembic async environment configuration for Citizen (v1.0).

Uses asyncpg and runs migrations via asyncio.
"""

from __future__ import annotations

import asyncio
import os
from logging.config import fileConfig
from typing import Any

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context

# Import all models so that Base.metadata is fully populated.
from app.db.models import Base

config = context.config

# Override sqlalchemy.url with the runtime DATABASE_URL if present.
DB_URL = os.getenv("DATABASE_URL")
if not DB_URL:
    default_url = "postgresql+asyncpg://user:pass@localhost:5432/legal_engine_db"
    if config.get_main_option("sqlalchemy.url") == default_url:
        DB_URL = default_url
    else:
        DB_URL = str(config.get_main_option("sqlalchemy.url", ""))

if config.config_file_name:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    Cannot be used with async drivers — we require a real connection.
    """
    raise NotImplementedError(
        "Offline migrations are not supported with async SQLAlchemy. "
        "Use 'alembic upgrade head' with a running database."
    )


def _do_run_migrations(connection: Any) -> None:
    """Run migrations within a single DB connection."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
    )

    with context.begin_transaction():
        context.run_migrations()


async def _run_async_migrations(url: str) -> None:
    """Create an async engine and run migrations."""
    engine = create_async_engine(url, poolclass=pool.NullPool)
    async with engine.connect() as connection:
        await connection.run_sync(_do_run_migrations)
    await engine.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode using async engine."""
    asyncio.run(_run_async_migrations(DB_URL))


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
