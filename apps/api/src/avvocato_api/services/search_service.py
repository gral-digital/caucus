"""Service di ricerca: assembla retriever + reranker.

In fase 1 usiamo bge-m3 locale come embedder (via FlagEmbedding). In prod lo
si sostituisce con `VertexEmbeddingProvider` cambiando solo questa factory.
"""

from __future__ import annotations

from functools import lru_cache

from fastapi import Depends

from avvocato_api.deps import get_corpus_map, get_vectorstore
from avvocato_rag_core.config import get_settings
from avvocato_rag_core.embeddings.base import EmbeddingProvider
from avvocato_rag_core.reranker import LocalBGEReranker, NoopReranker, Reranker
from avvocato_rag_core.retriever import HybridRetriever
from avvocato_rag_core.schemas.retrieval import RetrievalQuery, RetrievalResult
from avvocato_rag_core.vectorstore.qdrant_store import QdrantStore


@lru_cache(maxsize=1)
def _get_embedder() -> EmbeddingProvider:
    """Factory per il backend di embedding selezionato via env.

    - ``ollama`` (default dev): chiama http://localhost:11434 — niente torch.
    - ``local``: FlagEmbedding bge-m3 in-process (richiede torch + transformers).
    - ``vertex``: Vertex AI publisher endpoint (per prod).
    """
    settings = get_settings()
    backend = settings.embedding_backend.lower()

    if backend == "ollama":
        from avvocato_rag_core.embeddings.ollama import OllamaEmbeddingProvider

        return OllamaEmbeddingProvider(
            base_url=settings.ollama_base_url,
            model=settings.ollama_embedding_model,
            dense_dim=settings.embedding_dim,
        )
    if backend == "local":
        # Import lazy per non forzare torch quando non serve.
        from avvocato_rag_core.embeddings.local import LocalBGEM3Provider

        return LocalBGEM3Provider(model_name=settings.embedding_model)
    if backend == "vertex":
        raise NotImplementedError(
            "VertexEmbeddingProvider richiede access_token_factory; config TBD in prod."
        )
    raise ValueError(f"Unknown embedding_backend: {backend!r}")


@lru_cache(maxsize=1)
def _get_reranker() -> Reranker:
    settings = get_settings()
    # In local si preferisce noop per velocità; in dev/prod attiviamo bge-reranker.
    if settings.app_env == "local":
        return NoopReranker()
    try:
        return LocalBGEReranker(model_name=settings.reranker_model)
    except ImportError:
        return NoopReranker()


class SearchService:
    def __init__(
        self,
        retriever: HybridRetriever,
        reranker: Reranker,
    ) -> None:
        self._retriever = retriever
        self._reranker = reranker

    @classmethod
    def factory(
        cls,
        vectorstore: QdrantStore = Depends(get_vectorstore),
        corpus_map=Depends(get_corpus_map),
    ) -> "SearchService":
        retriever = HybridRetriever(
            embedder=_get_embedder(),
            vectorstore=vectorstore,
            corpus_collection_map=corpus_map,
        )
        return cls(retriever=retriever, reranker=_get_reranker())

    async def search(self, query: RetrievalQuery) -> RetrievalResult:
        raw = await self._retriever.retrieve(query)
        reranked_hits = await self._reranker.rerank(
            query.text, raw.hits, top_k=query.top_k_rerank
        )
        return raw.model_copy(update={"hits": reranked_hits})
