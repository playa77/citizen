# Semantic Version: 0.3.0 | 2026-08-25 — API-only service (D-024/D-025):
# static frontend, root HTML route and desktop launcher removed.

import asyncio
import logging
import sys
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import Response

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
from app.middleware.dev_headers import DevNoIndexMiddleware
from app.middleware.disclaimer import DisclaimerMiddleware
from app.services.dev_guard import DevGuardError, check_dev_synthetic_data_startup


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

    # WP-62: Dev-instance synthetic-data-only assertion (Art. 2(8) posture).
    # A dev instance must not start without an explicit synthetic-data-only flag.
    try:
        check_dev_synthetic_data_startup()
    except DevGuardError as exc:
        logger.critical(
            "Refusing to start: DEPLOYMENT_MODE=dev without CITIZEN_SYNTHETIC_DATA_ONLY=true — %s",
            exc,
        )
        raise

    # PostgreSQL engine — no dialect-specific initialisation required (D-024).
    from app.db.session import async_session_factory

    # Run Alembic migrations automatically on startup.
    try:
        # env.py reads DATABASE_URL from the environment; the ini-file default
        # is a dead sentinel. Do NOT call set_main_option here — the
        # side-effect inside env.py causes a long-running deadlock with asyncpg
        # when applied through the running event loop. See DECISIONS.md §D-007.

        # Run alembic upgrade in a subprocess, NOT via asyncio.to_thread.
        #
        # asyncio.to_thread(alembic_command.upgrade, …) deadlocks when called
        # from inside uvicorn's lifespan handler because asyncpg + greenlet
        # internals conflict with the running event loop across threads.
        # A subprocess is an independent interpreter that avoids this entirely.
        # See DECISIONS.md §D-007.
        #
        # Single migration DAG since D-024: "head" is unambiguous.
        _proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "alembic",
            "upgrade",
            "head",
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
            logger.info("Alembic migrations applied successfully (target=head).")
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
app.add_middleware(DevNoIndexMiddleware)

# API-only service (D-025): no static frontend, no HTML routes. The sole
# external interface is the versioned REST API under /api/v1, self-described
# via /docs, /redoc and /openapi.json.

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


@app.get("/robots.txt")
async def robots_txt() -> Response:
    """Robots exclusion (WP-62) — dev instances must not be indexed."""
    if getattr(settings, "DEPLOYMENT_MODE", "dev") == "dev":
        return Response(
            content="User-agent: *\nDisallow: /\n",
            media_type="text/plain",
        )
    return Response(
        content="User-agent: *\nAllow: /\n",
        media_type="text/plain",
    )
