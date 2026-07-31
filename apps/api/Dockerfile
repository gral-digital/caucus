# syntax=docker/dockerfile:1.7
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# uv per install veloce e riproducibile
COPY --from=ghcr.io/astral-sh/uv:0.5.10 /uv /usr/local/bin/uv

# Dipendenze di sistema minime
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev curl ca-certificates \
  && rm -rf /var/lib/apt/lists/*

# Copy workspace files (dal root del monorepo).
# uv.lock è OBBLIGATORIO per `uv sync --frozen`: senza, il build fallisce.
COPY pyproject.toml uv.lock ./
COPY services/rag-core ./services/rag-core
COPY apps/api ./apps/api

WORKDIR /app/apps/api

RUN uv sync --frozen --no-dev

# Mai girare come root in un container esposto.
RUN useradd --create-home --uid 1001 appuser \
  && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -sf http://localhost:8000/api/v1/health/live || exit 1
# --proxy-headers: dietro Cloud Run/LB serve per client IP e scheme corretti.
CMD ["uv", "run", "uvicorn", "avvocato_api.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
