# ==========================================
# Citizen (v1.0) - Multi-stage Dockerfile
# Targets: Ubuntu (primary), also builds on Win/Mac via Docker
# ==========================================

# ---- Stage 1: System dependencies ----
FROM ubuntu:24.04 AS base

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-venv \
    python3-pip \
    build-essential \
    libpq-dev \
    tesseract-ocr \
    libtesseract-dev \
    tesseract-ocr-deu \
    && rm -rf /var/lib/apt/lists/*

# ---- Stage 2: Python venv + pip dependencies ----
FROM base AS deps

RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install wheel / setuptools first to avoid resolution failures
RUN pip install --upgrade pip setuptools wheel

# Copy only pyproject.toml for layer-cached install
COPY pyproject.toml /app/pyproject.toml
RUN pip install --no-cache-dir -e "/app[dev]"

# ---- Stage 3: Application ----
FROM base AS app

COPY --from=deps /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Copy application source
COPY . /app

# Create directories needed at runtime
RUN mkdir -p /app/logs /app/uploads

# Expose the default FastAPI port
EXPOSE 8000

# Health-check
HEALTHCHECK --interval=15s --timeout=5s --retries=3 \
    CMD python3 -c "import httpx; httpx.get('http://localhost:8000/health').raise_for_status()" || exit 1

# Default entrypoint
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
