# Semantic Version: 0.2.0 | 2026-07-10 — Desktop app support
# (SQLite + Alembic auto-migration + sqlite-vec)

import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import (
    analyze,
    cases,
    conversations,
    corpus,
    ingest,
    intake,
    meta,
    presets,
)
from app.core.config import get_app_version, get_app_version_tag, settings
from app.middleware.disclaimer import DisclaimerMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # Startup: configure logging, DB init, router warmup, salt generation.
    logging.basicConfig(
        level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    logger = logging.getLogger(__name__)
    logger.info("Citizen %s starting up — LOG_LEVEL=%s", get_app_version_tag(), settings.LOG_LEVEL)

    # SQLite: initialise WAL mode, busy timeout, and foreign keys (no-op for PostgreSQL).
    from app.db.session import IS_SQLITE, _init_sqlite  # type: ignore[attr-defined]

    if IS_SQLITE:
        await _init_sqlite()
        logger.info("SQLite engine initialised — WAL mode enabled")

    # Run Alembic migrations automatically on startup (desktop convenience)
    try:
        from alembic import command as alembic_command
        from alembic.config import Config as AlembicConfig

        alembic_cfg = AlembicConfig("alembic.ini")
        # Override the DB URL with the runtime value (alembic.ini has a dead default)
        alembic_cfg.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

        # On SQLite fresh DB, stamp directly to the SQLite baseline migration
        # to skip PostgreSQL-only migrations 001-006.
        if settings.DATABASE_URL.startswith("sqlite"):
            from sqlalchemy import create_engine, inspect as sa_inspect

            sync_url = settings.DATABASE_URL.replace("+aiosqlite", "")
            sync_engine = create_engine(sync_url)
            inspector = sa_inspect(sync_engine)
            if not inspector.has_table("alembic_version"):
                await asyncio.to_thread(alembic_command.stamp, alembic_cfg, "007_sqlite_baseline")
                logger.info("SQLite fresh DB detected — stamped to 007_sqlite_baseline")
            sync_engine.dispose()

        # Use asyncio.to_thread to escape the running event loop
        # (alembic_command.upgrade calls asyncio.run internally via env.py)
        await asyncio.to_thread(alembic_command.upgrade, alembic_cfg, "head")
        logger.info("Alembic migrations applied successfully.")
    except Exception as exc:
        logger.warning("Alembic migration skipped or failed: %s. Continuing anyway.", exc)

    yield
    # Shutdown
    from app.core.router import close_client

    try:
        await close_client()
    except Exception:
        logging.getLogger(__name__).warning("Failed to close shared router client gracefully")
    logger.info("Citizen %s shutting down", get_app_version_tag())


app = FastAPI(
    title=f"Citizen ({get_app_version_tag()})",
    description="Local-first, evidence-constrained legal reasoning engine for German social law",
    version=get_app_version(),
    lifespan=lifespan,
)

app.add_middleware(DisclaimerMiddleware)

# Serve static frontend (will be populated in WP-014).
app.mount("/static", StaticFiles(directory="static"), name="static")

# Register API routers
app.include_router(ingest.router, prefix="/api/v1", tags=["ingest"])
app.include_router(analyze.router, prefix="/api/v1", tags=["analyze"])
app.include_router(conversations.router, prefix="/api/v1", tags=["conversations"])
app.include_router(cases.router, prefix="/api/v1", tags=["cases"])
app.include_router(corpus.router, prefix="/api/v1", tags=["corpus"])
app.include_router(intake.router, prefix="/api/v1", tags=["intake"])
app.include_router(presets.router, prefix="/api/v1", tags=["presets"])
app.include_router(meta.router, prefix="/api/v1", tags=["meta"])


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe — docker-compose healthcheck and DevOps monitoring."""
    return {"status": "ok", "version": get_app_version_tag()}


@app.get("/")
async def root() -> FileResponse:
    """Serve the main frontend page."""
    return FileResponse(Path("static") / "index.html")


if __name__ == "__main__":
    import argparse
    import os
    import uvicorn

    parser = argparse.ArgumentParser(description="Citizen Desktop Backend")
    parser.add_argument("--port", type=int, default=8000, help="Port to listen on")
    parser.add_argument("--data-dir", type=str, default=".", help="Data directory for DB and files")
    args = parser.parse_args()

    # Override DATABASE_URL if --data-dir is provided
    if args.data_dir != ".":
        data_dir = Path(args.data_dir)
        data_dir.mkdir(parents=True, exist_ok=True)
        os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{data_dir / 'citizen.db'}"

    uvicorn.run(app, host="127.0.0.1", port=args.port, workers=1)
