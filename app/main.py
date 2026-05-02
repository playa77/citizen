from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles


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

# Serve static frontend (will be populated in WP-014).
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe — docker-compose healthcheck and DevOps monitoring."""
    return {"status": "ok", "version": "v1.0.0"}
