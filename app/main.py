# Semantic Version: 0.2.0 | 2026-07-10 — Desktop app support
# (SQLite + Alembic auto-migration + sqlite-vec)

import asyncio
import logging
import sys
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
    documents,
    eval_reports,
    goldset,
    ingest,
    intake,
    meta,
    ocr,
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
    from app.db.session import IS_SQLITE, _init_sqlite, async_session_factory

    if IS_SQLITE:
        await _init_sqlite()
        logger.info("SQLite engine initialised — WAL mode enabled")

    # Run Alembic migrations automatically on startup (desktop convenience)
    try:
        from alembic import command as alembic_command
        from alembic.config import Config as AlembicConfig

        alembic_cfg = AlembicConfig("alembic.ini")
        # env.py already reads DATABASE_URL from the environment; the ini-file
        # default is a dead sentinel. Do NOT call set_main_option here — the
        # side-effect inside env.py causes a long-running deadlock with asyncpg
        # when applied through the running event loop. See DECISIONS.md §D-007.
        # alembic_cfg.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

        # On SQLite fresh DB, stamp directly to the SQLite baseline migration
        # to skip PostgreSQL-only migrations 001-006.
        if settings.DATABASE_URL.startswith("sqlite"):
            from sqlalchemy import create_engine
            from sqlalchemy import inspect as sa_inspect

            sync_url = settings.DATABASE_URL.replace("+aiosqlite", "")
            sync_engine = create_engine(sync_url)
            inspector = sa_inspect(sync_engine)
            if not inspector.has_table("alembic_version"):
                await asyncio.to_thread(alembic_command.stamp, alembic_cfg, "007_sqlite_baseline")
                logger.info("SQLite fresh DB detected — stamped to 007_sqlite_baseline")
            sync_engine.dispose()

        # Run alembic upgrade in a subprocess, NOT via asyncio.to_thread.
        #
        # asyncio.to_thread(alembic_command.upgrade, …) deadlocks when called
        # from inside uvicorn's lifespan handler because asyncpg + greenlet
        # internals conflict with the running event loop across threads.
        # A subprocess is an independent interpreter that avoids this entirely.
        # See DECISIONS.md §D-007.
        #
        # Migration DAG: two branches — PostgreSQL (001→006→011_pg) and SQLite baseline (007→010→011_sqlite).
        # "head" is ambiguous; target the correct tip for the active database dialect.
        _migration_target = (
            "heads"
            if settings.DATABASE_URL.startswith("sqlite")
            else "011_pg_legal_chunk_text_hash"
        )
        _proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "alembic",
            "upgrade",
            _migration_target,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _stdout, _stderr = await asyncio.wait_for(_proc.communicate(), timeout=60.0)
        if _proc.returncode != 0:
            logger.warning(
                "Alembic upgrade returned code %d: stdout=%s stderr=%s",
                _proc.returncode,
                _stdout.decode(errors="replace").strip(),
                _stderr.decode(errors="replace").strip(),
            )
        else:
            logger.info("Alembic migrations applied successfully (target=%s).", _migration_target)
    except Exception as exc:
        logger.warning("Alembic migration skipped or failed: %s. Continuing anyway.", exc)

    # Preload the legal parameter cache for synchronous param() lookups.
    from app.services.parameter_store import reload_parameter_cache

    try:
        async with async_session_factory() as session:
            await reload_parameter_cache(session)
        logger.info("Legal parameter cache populated.")
    except Exception as exc:
        logger.warning("Parameter cache population failed: %s. Continuing anyway.", exc)

    # WP-31: Validate active inference profile at startup
    try:
        from app.services.inference_profiles import (
            get_active_profile,
            validate_profile,
        )

        profile = get_active_profile()
        warnings = validate_profile(profile)
        logger.info(
            "Active inference profile: %s (label=%r, avv_status=%s, pseudonymization=%s)",
            profile.name,
            profile.label,
            profile.avv_status,
            profile.pseudonymization,
        )
        if warnings:
            for w in warnings:
                logger.warning("Inference profile warning: %s", w)
    except ValueError as exc:
        logger.error(
            "Inference profile validation FAILED — starting in limited mode: %s",
            exc,
        )
    except Exception as exc:
        logger.warning(
            "Inference profile loading skipped: %s. Continuing anyway.",
            exc,
        )

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
app.include_router(ocr.router, prefix="/api/v1", tags=["ocr"])
app.include_router(documents.router, prefix="/api/v1", tags=["documents"])
app.include_router(goldset.router, prefix="/api/v1", tags=["goldset"])
app.include_router(eval_reports.router, prefix="/api/v1", tags=["eval_reports"])


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
