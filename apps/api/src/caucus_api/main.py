"""FastAPI entry point.

Monta le route versionate sotto /api/v1 e applica middleware di base.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from caucus_api.logging_config import configure_logging
from caucus_api.routes import chat, export, health, norma, search
from caucus_rag_core.config import get_settings

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:  # noqa: ARG001
    configure_logging()
    settings = get_settings()
    logger.info(
        "caucus_api.start",
        env=settings.app_env,
        primary_llm=settings.llm_primary_model,
        fallback_llm=settings.llm_fallback_model,
    )
    # Warm-up del reranker locale: il caricamento del cross-encoder (~5s)
    # non deve pagarlo la prima query utente.
    from caucus_api.services.search_service import _get_reranker
    from caucus_rag_core.reranker import CrossEncoderReranker

    reranker = _get_reranker()
    if isinstance(reranker, CrossEncoderReranker):
        import asyncio as _asyncio

        await _asyncio.to_thread(reranker.warm_up)
        logger.info("reranker.warmed_up")
    yield
    logger.info("caucus_api.stop")


app = FastAPI(
    title="Caucus API",
    version="0.0.1",
    description=(
        "Backend per Caucus — AI open source per il diritto e la compliance italiana. "
        "Espone endpoint per chat RAG sui codici, ricerca diretta e ingestion control."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    # Env-driven (CORS_ALLOW_ORIGINS, comma-separated). Il default in config
    # copre il dev locale (3000/3100); in prod impostare il dominio pubblico.
    allow_origins=[o.strip() for o in get_settings().cors_allow_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
)

app.include_router(health.router, prefix="/api/v1", tags=["health"])
app.include_router(search.router, prefix="/api/v1", tags=["search"])
app.include_router(chat.router, prefix="/api/v1", tags=["chat"])
app.include_router(norma.router, prefix="/api/v1", tags=["norma"])
app.include_router(export.router, prefix="/api/v1", tags=["export"])
