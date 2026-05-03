from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import analyze, corpus, ingest, meta
from app.middleware.disclaimer import DisclaimerMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # Startup: DB init, router warmup, salt generation will live here.
    yield
    # Shutdown


app = FastAPI(
    title="Citizen (v1.0)",
    description="Local-first, evidence-constrained legal reasoning engine for German social law",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — restricted to localhost:8000 by default; overridden by settings later.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Disclaimer acceptance middleware — must be added AFTER CORS
app.add_middleware(DisclaimerMiddleware)

# Serve static frontend (will be populated in WP-014).
app.mount("/static", StaticFiles(directory="static"), name="static")

# Register API routers
app.include_router(ingest.router, prefix="/api/v1", tags=["ingest"])
app.include_router(analyze.router, prefix="/api/v1", tags=["analyze"])
app.include_router(corpus.router, prefix="/api/v1", tags=["corpus"])
app.include_router(meta.router, prefix="/api/v1", tags=["meta"])


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe — docker-compose healthcheck and DevOps monitoring."""
    return {"status": "ok", "version": "v1.0.0"}


@app.get("/")
async def root() -> FileResponse:
    """Serve the main frontend page."""
    return FileResponse(Path("static") / "index.html")
