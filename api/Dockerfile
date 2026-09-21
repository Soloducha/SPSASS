# API Dockerfile — Multi-stage para desarrollo y producción
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

# Cambiar a usuario no-root
RUN chown -R appuser:appuser /app
USER appuser

# Puerto
EXPOSE 8000

# Comando por defecto (sobrescrito en docker-compose para dev)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]