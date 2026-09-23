# API Dockerfile — Multi-stage para API y worker
# Usage:
#   API:    docker compose build api     (stage: api)  — FastAPI server
#   Worker: docker compose build worker  (stage: worker) — arq workers
# Patrón multi-stage igual que web/Dockerfile: un solo archivo, targets por runtime.

FROM python:3.12-slim AS base

# Variables de entorno
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Dependencias del sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Usuario no-root
RUN groupadd -r appuser && useradd -r -g appuser appuser

WORKDIR /app

# Copiar requirements primero para cache
COPY pyproject.toml .
RUN pip install --no-cache-dir -e ".[dev]"

# Copiar código
COPY . .

RUN chown -R appuser:appuser /app

# ──────────────────────────────────────────────
# Stage: api — FastAPI server (default del compose para service api)
# ──────────────────────────────────────────────
FROM base AS api

USER appuser

# Puerto
EXPOSE 8000

# Comando por defecto (sobrescrito en docker-compose para dev)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

# ──────────────────────────────────────────────
# Stage: worker — arq workers (service worker)
# ──────────────────────────────────────────────
FROM base AS worker

USER appuser

# Worker no expone puerto
CMD ["python", "-m", "app.workers.main"]