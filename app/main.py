# Semantic Version: 0.1.0

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import analyze, cases, conversations, corpus, ingest, meta
from app.core.config import get_app_version, get_app_version_tag, settings
from app.middleware.disclaimer import DisclaimerMiddleware
from app.middleware.rate_limit import RateLimitMiddleware


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
    yield
    # Shutdown
    from app.services.reasoning import close_client as close_reasoning_client
    from app.services.chat_reasoning import close_client as close_chat_client
    try:
        await close_reasoning_client()
    except Exception:
        logging.getLogger(__name__).warning("Failed to close reasoning client gracefully")
    try:
        await close_chat_client()
    except Exception:
        logging.getLogger(__name__).warning("Failed to close chat reasoning client gracefully")
    logger.info("Citizen %s shutting down", get_app_version_tag())


app = FastAPI(
    title=f"Citizen ({get_app_version_tag()})",
    description="Local-first, evidence-constrained legal reasoning engine for German social law",
    version=get_app_version(),
    lifespan=lifespan,
)

# CORS — restricted to localhost:8000 by default; overridden via settings.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate limiting — in-memory sliding window, guards against runaway requests.
app.add_middleware(RateLimitMiddleware)

# Disclaimer acceptance middleware — must be added AFTER CORS
app.add_middleware(DisclaimerMiddleware)

# Serve static frontend (will be populated in WP-014).
app.mount("/static", StaticFiles(directory="static"), name="static")

# Register API routers
app.include_router(ingest.router, prefix="/api/v1", tags=["ingest"])
app.include_router(analyze.router, prefix="/api/v1", tags=["analyze"])
app.include_router(conversations.router, prefix="/api/v1", tags=["conversations"])
app.include_router(cases.router, prefix="/api/v1", tags=["cases"])
app.include_router(corpus.router, prefix="/api/v1", tags=["corpus"])
app.include_router(meta.router, prefix="/api/v1", tags=["meta"])


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe — docker-compose healthcheck and DevOps monitoring."""
    return {"status": "ok", "version": get_app_version_tag()}


@app.get("/")
async def root() -> FileResponse:
    """Serve the main frontend page."""
    return FileResponse(Path("static") / "index.html")
