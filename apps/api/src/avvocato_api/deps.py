"""Dependency injection FastAPI.

Istanzia singleton di session maker, vector store, retriever, LLM router.
Usato dalle route via `Depends(...)`.
"""

from __future__ import annotations

import secrets
import time
from collections import deque
from collections.abc import AsyncGenerator
from functools import lru_cache

import structlog
from fastapi import HTTPException, Request, status
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from avvocato_rag_core.config import get_settings
from avvocato_rag_core.llm.router import LLMRouter
from avvocato_rag_core.schemas.retrieval import CorpusFilter
from avvocato_rag_core.vectorstore.qdrant_store import QdrantStore

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Sicurezza: auth a token condiviso + rate limiting per IP
# ---------------------------------------------------------------------------


def _extract_token(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.headers.get("x-api-key")


async def require_api_auth(request: Request) -> None:
    """Auth minima: token condiviso via ``Authorization: Bearer`` o ``X-API-Key``.

    - Token configurato (API_AUTH_TOKEN): confronto constant-time.
    - Token assente: consentito solo con app_env=local; in dev/prod fail-closed
      (meglio un 503 esplicito che un endpoint LLM a pagamento aperto al mondo).
    """
    settings = get_settings()
    expected = settings.api_auth_token
    if not expected:
        if settings.app_env == "local":
            return
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="API_AUTH_TOKEN non configurato: endpoint disabilitato fuori da app_env=local.",
        )
    provided = _extract_token(request)
    if not provided or not secrets.compare_digest(provided, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token mancante o non valido.",
            headers={"WWW-Authenticate": "Bearer"},
        )


# Sliding window in-memory per processo. Con più istanze (Cloud Run) il limite
# è per-istanza: per un limite globale passare a Redis (già nello stack).
_RATE_BUCKETS: dict[str, deque[float]] = {}


async def rate_limit(request: Request) -> None:
    limit = get_settings().rate_limit_per_minute
    if limit <= 0:
        return
    ip = request.client.host if request.client else "unknown"
    now = time.monotonic()
    bucket = _RATE_BUCKETS.setdefault(ip, deque())
    cutoff = now - 60.0
    while bucket and bucket[0] < cutoff:
        bucket.popleft()
    if len(bucket) >= limit:
        logger.warning("rate_limited", ip=ip, limit=limit)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Troppe richieste: riprova tra qualche istante.",
            headers={"Retry-After": "60"},
        )
    bucket.append(now)


@lru_cache(maxsize=1)
def get_engine() -> AsyncEngine:
    settings = get_settings()
    return create_async_engine(
        settings.database_url,
        echo=settings.app_env == "local",
        pool_size=10,
        max_overflow=5,
        pool_pre_ping=True,
    )


@lru_cache(maxsize=1)
def get_session_maker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=False)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with get_session_maker()() as session:
        yield session


@lru_cache(maxsize=1)
def get_vectorstore() -> QdrantStore:
    settings = get_settings()
    return QdrantStore(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key,
        dense_dim=settings.embedding_dim,
    )


@lru_cache(maxsize=1)
def get_corpus_map() -> dict[CorpusFilter, str]:
    settings = get_settings()
    return {
        CorpusFilter.CODICI: settings.qdrant_collection_codici,
        CorpusFilter.LEGGI: settings.qdrant_collection_leggi,
        CorpusFilter.CASSAZIONE: settings.qdrant_collection_cassazione,
    }


@lru_cache(maxsize=1)
def get_llm_router() -> LLMRouter:
    """Router LLM.

    - ``ollama``: dev locale, nessun costo, qwen3:8b.
    - ``openai``: GPT-5-mini / GPT-5 (reasoning models; serve ``reasoning_effort``
      basso altrimenti consuma i token di uscita per pensare e tronca la risposta).
    - ``vertex``: prod GCP, Llama 3.3 o Claude.
    """
    settings = get_settings()
    backend = settings.llm_backend.lower()

    if backend == "ollama":
        return LLMRouter(
            primary_model=f"ollama/{settings.ollama_llm_model}",
            fallback_model=None,
            default_max_tokens=2048,
            extra_params={"api_base": settings.ollama_base_url},
        )

    if backend == "openai":
        primary = settings.llm_primary_model
        is_reasoning = any(k in primary for k in ("gpt-5", "o1", "o3"))
        extra: dict[str, object] = {}
        if is_reasoning:
            # Minimal reasoning: vogliamo risposte rapide per chat legal.
            # 'low'/'minimal' lasciano più budget output. 'medium' è default.
            extra["reasoning_effort"] = "low"
        return LLMRouter(
            primary_model=primary,
            fallback_model=settings.llm_fallback_model,
            default_max_tokens=8192,  # reasoning models mangiano budget con il thinking
            extra_params=extra,
        )

    return LLMRouter(
        primary_model=settings.llm_primary_model,
        fallback_model=settings.llm_fallback_model,
        default_max_tokens=4096,
    )
