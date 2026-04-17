"""Dependency injection FastAPI.

Istanzia singleton di session maker, vector store, retriever, LLM router.
Usato dalle route via `Depends(...)`.
"""

from __future__ import annotations

from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from avvocato_rag_core.config import Settings, get_settings
from avvocato_rag_core.llm.router import LLMRouter
from avvocato_rag_core.schemas.retrieval import CorpusFilter
from avvocato_rag_core.vectorstore.qdrant_store import QdrantStore


@lru_cache(maxsize=1)
def get_engine():
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


async def get_db_session() -> AsyncSession:
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
def get_corpus_map(_: Settings | None = None) -> dict[CorpusFilter, str]:
    settings = get_settings()
    return {
        CorpusFilter.CODICI: settings.qdrant_collection_codici,
        CorpusFilter.LEGGI: settings.qdrant_collection_leggi,
        CorpusFilter.CASSAZIONE: settings.qdrant_collection_cassazione,
    }


@lru_cache(maxsize=1)
def get_llm_router() -> LLMRouter:
    settings = get_settings()
    return LLMRouter(
        primary_model=settings.llm_primary_model,
        fallback_model=settings.llm_fallback_model,
    )
