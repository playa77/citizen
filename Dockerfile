# ==========================================
# Citizen — Multi-stage Dockerfile
# Targets: Ubuntu (primary), also builds on Win/Mac via Docker
# ==========================================
# Semantic Version: 0.1.0

# ---- Stage 1: Install system-level dependencies ----
FROM python:3.11-slim-bookworm AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    tesseract-ocr \
    libtesseract-dev \
    tesseract-ocr-deu \
    && rm -rf /var/lib/apt/lists/*

# ---- Stage 2: Python dependencies (venv) ----
FROM base AS deps

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install wheel / setuptools first
RUN pip install --upgrade pip setuptools wheel

# Copy only build-time files for layer caching
COPY pyproject.toml README.md /app/

# Create a minimal package to satisfy pip install -e ".[dev]"
WORKDIR /app
RUN mkdir -p app && touch app/__init__.py && \
    pip install --no-cache-dir -e ".[dev]"

# ---- Stage 3: Production application image ----
FROM base AS app

# Copy venv from deps stage (no dev tooling in final image — saving ~120 MB)
COPY --from=deps /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Copy application source
COPY . /app

# Create runtime directories
RUN mkdir -p /app/logs /app/uploads

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/health').raise_for_status()" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
