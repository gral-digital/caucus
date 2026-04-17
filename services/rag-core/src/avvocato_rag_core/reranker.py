"""Reranker cross-encoder (bge-reranker-v2-m3) opzionale.

In dev/eval si usa il modello locale (FlagEmbedding). In prod si sposta su un
endpoint Vertex custom container per evitare GPU sul processo API.

Il reranker *non* è obbligatorio per far girare l'API: se disabilitato, si usano
direttamente gli score hybrid di Qdrant (RRF).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

import structlog

from avvocato_rag_core.schemas.retrieval import RetrievalHit

logger = structlog.get_logger(__name__)


class Reranker(ABC):
    @abstractmethod
    async def rerank(
        self, query: str, hits: Sequence[RetrievalHit], top_k: int
    ) -> list[RetrievalHit]: ...


class NoopReranker(Reranker):
    """Passa i primi `top_k` così come sono. Utile in dev prima di montare il modello."""

    async def rerank(
        self, query: str, hits: Sequence[RetrievalHit], top_k: int
    ) -> list[RetrievalHit]:
        del query
        return list(hits[:top_k])


class LocalBGEReranker(Reranker):
    """bge-reranker-v2-m3 locale via FlagEmbedding.

    Richiede `pip install avvocato-rag-core[reranker-local]`.
    """

    def __init__(
        self,
        model_name: str = "BAAI/bge-reranker-v2-m3",
        *,
        device: str = "cpu",
        use_fp16: bool = False,
        batch_size: int = 16,
    ) -> None:
        self._model_name = model_name
        self._device = device
        self._use_fp16 = use_fp16
        self._batch_size = batch_size
        self._model = None

    def _lazy_load(self):
        if self._model is None:
            from FlagEmbedding import FlagReranker

            self._model = FlagReranker(
                self._model_name, use_fp16=self._use_fp16, device=self._device
            )
        return self._model

    async def rerank(
        self, query: str, hits: Sequence[RetrievalHit], top_k: int
    ) -> list[RetrievalHit]:
        if not hits:
            return []

        import asyncio

        model = self._lazy_load()
        pairs = [[query, h.text] for h in hits]

        def _score() -> list[float]:
            return model.compute_score(pairs, normalize=True, batch_size=self._batch_size)

        scores = await asyncio.to_thread(_score)
        if not isinstance(scores, list):
            scores = [scores]

        reranked = [
            h.model_copy(update={"score_rerank": float(s), "score_final": float(s)})
            for h, s in zip(hits, scores, strict=True)
        ]
        reranked.sort(key=lambda h: h.score_final, reverse=True)
        logger.info("rerank_done", total=len(reranked), kept=top_k)
        return reranked[:top_k]
