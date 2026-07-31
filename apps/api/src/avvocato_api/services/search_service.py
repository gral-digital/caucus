"""Service di ricerca: vector + FTS + lookup diretto → merge RRF → rerank."""

from __future__ import annotations

import asyncio
from functools import lru_cache
from time import perf_counter

import structlog
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from avvocato_api.deps import get_corpus_map, get_db_session, get_llm_router, get_vectorstore
from avvocato_api.services.fts_retriever import FtsRetriever
from avvocato_rag_core.config import get_settings
from avvocato_rag_core.embeddings.base import EmbeddingProvider
from avvocato_rag_core.embeddings.factory import create_embedding_provider
from avvocato_rag_core.hit_merge import ensure_direct_articles_first, reciprocal_rank_fusion
from avvocato_rag_core.query_expander import LLMQueryExpander
from avvocato_rag_core.query_router import ArticleRef, apply_routing, route_query
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


@lru_cache(maxsize=1)
def _get_expander() -> LLMQueryExpander | None:
    if not get_settings().query_expansion_enabled:
        return None
    return LLMQueryExpander(
        get_llm_router(), model=get_settings().query_expansion_model
    )


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

        # L'espansione LLM (la parte lenta, ~1-2s) parte SUBITO; in parallelo
        # girano i rami DB sul testo originale. ATTENZIONE: le chiamate che
        # usano la AsyncSession (direct, fts, exp_lookup) devono restare
        # SEQUENZIALI tra loro — la sessione SQLAlchemy non ammette operazioni
        # concorrenti ("This session is provisioning a new connection...").
        expander = _get_expander()
        expansion_task = (
            asyncio.create_task(expander.expand(routed.original_text))
            if expander is not None
            else None
        )
        direct_hits = await self._fts.direct_articles(
            routed.direct_articles, effective_at=effective_query.effective_at
        )
        fts_hits = await self._fts.search(
            routed,
            limit=effective_query.top_k_retrieve,
            effective_at=effective_query.effective_at,
        )

        expansion_refs: tuple[ArticleRef, ...] = ()
        if expansion_task is not None:
            expansion = await expansion_task
            if expansion:
                effective_query = effective_query.model_copy(
                    update={"text": f"{effective_query.text}\n{expansion}"}
                )
                # I riferimenti espliciti nell'espansione ("art. 2043 codice
                # civile") diventano candidati di lookup NON pinnati: se il
                # modello ha suggerito l'articolo giusto è un hit esatto, se ha
                # sbagliato il reranker lo affossa.
                exp_routed = route_query(expansion)
                user_refs = {(a.source, a.num) for a in routed.direct_articles}
                expansion_refs = tuple(
                    a
                    for a in exp_routed.direct_articles
                    if (a.source, a.num) not in user_refs
                )[:4]

        # Il ramo vettoriale (embedder+Qdrant, niente sessione DB) gira in
        # parallelo al lookup DB dei candidati dell'espansione.
        vector_task = asyncio.create_task(self._retriever.retrieve(effective_query))
        expansion_hits = []
        if expansion_refs:
            expansion_hits = [
                h.model_copy(
                    update={
                        "score_final": 1.0,
                        "metadata": {**h.metadata, "lookup": "expansion"},
                    }
                )
                for h in await self._fts.direct_articles(
                    expansion_refs, effective_at=effective_query.effective_at
                )
            ]
        vector_result = await vector_task

        pin_ids = [h.chunk_id for h in direct_hits]
        merged = reciprocal_rank_fusion(
            [direct_hits, expansion_hits, fts_hits, vector_result.hits],
            top_k=effective_query.top_k_retrieve,
            pin_first=pin_ids or None,
            # Il lookup per numero di articolo è deterministico: pesa il triplo
            # dei rami probabilistici. I candidati dell'espansione LLM pesano
            # più del probabilistico ma meno del lookup utente.
            weights=[3.0, 1.5, 1.0, 1.0],
        )

        # Il reranker riceve la query ESPANSA: il cross-encoder è debole sul
        # gap dottrina↔testo normativo ("responsabilità extracontrattuale" vs
        # art. 2043: 0.0002), fortissimo quando la query contiene la
        # terminologia della norma (0.98). Misurato, non teorico.
        reranked = await self._reranker.rerank(
            effective_query.text,
            merged[: get_settings().rerank_candidates],
            top_k=effective_query.top_k_rerank,
        )
        direct_keys = [(a.source, a.num) for a in routed.direct_articles]
        reranked = ensure_direct_articles_first(
            reranked, direct=direct_keys, top_k=effective_query.top_k_rerank
        )
        # Dedup per partizione: lo stesso articolo non deve occupare più slot
        # del top-k con chunk diversi (articolo-full + comma) — spreca contesto
        # e maschera articoli diversi rilevanti.
        seen_partitions: set[object] = set()
        deduped = []
        for h in reranked:
            if h.partition_id in seen_partitions:
                continue
            seen_partitions.add(h.partition_id)
            deduped.append(h)
        reranked = deduped

        # One-hop expansion sul grafo dei rinvii: gli articoli citati dai top
        # hit entrano nel contesto come materiale ausiliario (in coda).
        ref_hits = await self._fts.expand_citations(
            reranked[:3], max_extra=3, effective_at=effective_query.effective_at
        )
        if ref_hits:
            reranked = reranked + ref_hits

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
