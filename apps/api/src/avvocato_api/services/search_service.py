"""Service di ricerca: vector + FTS + lookup diretto → merge RRF → rerank."""

from __future__ import annotations

import asyncio
from functools import lru_cache
from time import perf_counter

import structlog
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from avvocato_api.deps import get_corpus_map, get_db_session, get_vectorstore
from avvocato_api.services.fts_retriever import FtsRetriever
from avvocato_rag_core.config import get_settings
from avvocato_rag_core.embeddings.base import EmbeddingProvider
from avvocato_rag_core.embeddings.factory import create_embedding_provider
from avvocato_rag_core.hit_merge import ensure_direct_articles_first, reciprocal_rank_fusion
from avvocato_rag_core.query_router import apply_routing, route_query
from avvocato_rag_core.reranker import Reranker
from avvocato_rag_core.reranker_factory import create_reranker
from avvocato_rag_core.retriever import HybridRetriever
from avvocato_rag_core.schemas.retrieval import CorpusFilter, RetrievalQuery, RetrievalResult
from avvocato_rag_core.vectorstore.qdrant_store import QdrantStore

logger = structlog.get_logger(__name__)


@lru_cache(maxsize=1)
def _get_embedder() -> EmbeddingProvider:
    return create_embedding_provider(get_settings())


@lru_cache(maxsize=1)
def _get_reranker() -> Reranker:
    return create_reranker(get_settings())


class SearchService:
    def __init__(
        self,
        retriever: HybridRetriever,
        reranker: Reranker,
        fts: FtsRetriever,
    ) -> None:
        self._retriever = retriever
        self._reranker = reranker
        self._fts = fts

    @classmethod
    def factory(
        cls,
        vectorstore: QdrantStore = Depends(get_vectorstore),
        corpus_map: dict[CorpusFilter, str] = Depends(get_corpus_map),
        session: AsyncSession = Depends(get_db_session),
    ) -> SearchService:
        retriever = HybridRetriever(
            embedder=_get_embedder(),
            vectorstore=vectorstore,
            corpus_collection_map=corpus_map,
        )
        return cls(
            retriever=retriever,
            reranker=_get_reranker(),
            fts=FtsRetriever(session),
        )

    @classmethod
    def build(cls, session: AsyncSession) -> SearchService:
        """Costruzione fuori dal ciclo di vita delle dependency FastAPI.

        Usata dagli endpoint streaming, dove la sessione DB deve vivere dentro
        il generatore (vedi routes/chat.py) e non può essere una dependency.
        """
        return cls(
            retriever=HybridRetriever(
                embedder=_get_embedder(),
                vectorstore=get_vectorstore(),
                corpus_collection_map=get_corpus_map(),
            ),
            reranker=_get_reranker(),
            fts=FtsRetriever(session),
        )

    async def search(self, query: RetrievalQuery) -> RetrievalResult:
        t0 = perf_counter()
        routed = route_query(query.text, base_sources=query.sources)
        effective_query = apply_routing(query, routed)

        logger.info(
            "search.route",
            intent=routed.intent,
            sources=effective_query.sources,
            direct=[(a.source, a.num) for a in routed.direct_articles],
        )

        # Stessa vigenza su tutti e tre i rami (None = oggi, come da contratto
        # di RetrievalQuery).
        vector_task = asyncio.create_task(self._retriever.retrieve(effective_query))
        direct_hits = await self._fts.direct_articles(
            routed.direct_articles, effective_at=effective_query.effective_at
        )
        fts_hits = await self._fts.search(
            routed,
            limit=effective_query.top_k_retrieve,
            effective_at=effective_query.effective_at,
        )
        vector_result = await vector_task

        pin_ids = [h.chunk_id for h in direct_hits]
        merged = reciprocal_rank_fusion(
            [direct_hits, fts_hits, vector_result.hits],
            top_k=effective_query.top_k_retrieve,
            pin_first=pin_ids or None,
        )

        reranked = await self._reranker.rerank(
            routed.original_text,
            merged,
            top_k=effective_query.top_k_rerank,
        )
        direct_keys = [(a.source, a.num) for a in routed.direct_articles]
        reranked = ensure_direct_articles_first(
            reranked, direct=direct_keys, top_k=effective_query.top_k_rerank
        )

        latency_ms = int((perf_counter() - t0) * 1000)
        logger.info(
            "search.done",
            vector=len(vector_result.hits),
            fts=len(fts_hits),
            direct=len(direct_hits),
            merged=len(merged),
            final=len(reranked),
            latency_ms=latency_ms,
        )

        return vector_result.model_copy(
            update={
                "query": effective_query,
                "hits": reranked,
                "total_retrieved": len(merged),
                "latency_ms": latency_ms,
            }
        )
