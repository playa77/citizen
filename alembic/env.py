"""Alembic async environment configuration for Citizen (v1.0).

Uses asyncpg and runs migrations via asyncio.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Import all models so that Base.metadata is fully populated.
from app.db.models import Base

config = context.config

# Override sqlalchemy.url with the runtime DATABASE_URL if present.
default_url = "postgresql+asyncpg://user:pass@localhost:5432/legal_engine_db"
if config.get_main_option("sqlalchemy.url") == default_url:
    import os

    if os.getenv("DATABASE_URL"):
        config.set_main_option("sqlalchemy.url", os.environ["DATABASE_URL"])

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


def do_run_migration(
    connectable: async_engine_from_config,
) -> None:
    """Run migrations within a single DB connection."""
    context.configure(
        connection=connectable,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Create an async engine and run migrations."""
    connectable = async_engine_from_config(
        config.config_ini_section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migration)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode using async engine."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
