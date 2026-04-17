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

# Copy workspace files (dal root del monorepo)
COPY pyproject.toml ./
COPY services/rag-core ./services/rag-core
COPY apps/api ./apps/api

WORKDIR /app/apps/api

RUN uv sync --frozen --no-dev

EXPOSE 8000
CMD ["uv", "run", "uvicorn", "avvocato_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
