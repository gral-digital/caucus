"""FastAPI entry point.

Monta le route versionate sotto /api/v1 e applica middleware di base.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from avvocato_api.logging_config import configure_logging
from avvocato_api.routes import chat, health, search
from avvocato_rag_core.config import get_settings

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ARG001
    configure_logging()
    settings = get_settings()
    logger.info(
        "avvocato_api.start",
        env=settings.app_env,
        primary_llm=settings.llm_primary_model,
        fallback_llm=settings.llm_fallback_model,
    )
    yield
    logger.info("avvocato_api.stop")


app = FastAPI(
    title="Avvocato API",
    version="0.0.1",
    description=(
        "Backend per Avvocato — piattaforma AI per il settore legale italiano. "
        "Espone endpoint per chat RAG sui codici, ricerca diretta e ingestion control."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    # Dev locale: accettiamo entrambi 3000 (default Next) e 3100 (fallback se 3000 è
    # occupato da un altro progetto). In prod: env-driven sul dominio pubblico.
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3100",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3100",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api/v1", tags=["health"])
app.include_router(search.router, prefix="/api/v1", tags=["search"])
app.include_router(chat.router, prefix="/api/v1", tags=["chat"])
