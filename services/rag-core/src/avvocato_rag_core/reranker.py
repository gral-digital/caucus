"""Reranker cross-encoder (bge-reranker-v2-m3) opzionale.

In dev/eval si usa il modello locale (FlagEmbedding). In prod si sposta su un
endpoint Vertex custom container per evitare GPU sul processo API.

Il reranker *non* è obbligatorio per far girare l'API: se disabilitato, si usano
direttamente gli score hybrid di Qdrant (RRF).
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Any

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
        self._model: Any = None

    def _lazy_load(self) -> Any:
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
            raw = model.compute_score(pairs, normalize=True, batch_size=self._batch_size)
            return [float(x) for x in raw] if isinstance(raw, list) else [float(raw)]

        scores = await asyncio.to_thread(_score)

        reranked = [
            h.model_copy(update={"score_rerank": float(s), "score_final": float(s)})
            for h, s in zip(hits, scores, strict=True)
        ]
        reranked.sort(key=lambda h: h.score_final, reverse=True)
        logger.info("rerank_done", total=len(reranked), kept=top_k)
        return reranked[:top_k]


class KeywordBoostReranker(Reranker):
    """Reranker leggero senza ML: overlap lessicale + disambiguazione rubriche."""

    _NEGATIVE_PAIRS: tuple[tuple[str, str], ...] = (
        ("volontario", "colposo"),
        ("volontaria", "colposo"),
        ("dolo", "colposo"),
        ("extracontrattuale", "contrattuale"),
    )

    async def rerank(
        self, query: str, hits: Sequence[RetrievalHit], top_k: int
    ) -> list[RetrievalHit]:
        if not hits:
            return []

        q_tokens = set(_tokenize(query))
        scored: list[tuple[float, RetrievalHit]] = []

        for hit in hits:
            text = hit.text.lower()
            tokens = set(_tokenize(text))
            overlap = len(q_tokens & tokens) / max(len(q_tokens), 1)

            boost = 0.0
            if hit.metadata.get("lookup") == "direct":
                boost += 3.0
            elif hit.metadata.get("lookup") == "expansion":
                boost += 1.5
            elif hit.metadata.get("lookup") == "fts":
                boost += 1.0

            rubrica = _extract_rubrica(text)
            if rubrica:
                rub_tokens = set(_tokenize(rubrica))
                boost += 0.5 * len(q_tokens & rub_tokens) / max(len(q_tokens), 1)

            penalty = 0.0
            for pos, neg in self._NEGATIVE_PAIRS:
                if pos in query.lower() and neg in text:
                    penalty += 2.0

            # Articoli abrogati: restano nel corpus (per rispondere "è stato
            # abrogato?") ma non devono battere le norme vigenti.
            if hit.metadata.get("abrogato"):
                penalty += 1.5

            final = overlap + boost - penalty + 0.1 * hit.score_final
            scored.append(
                (final, hit.model_copy(update={"score_rerank": final, "score_final": final}))
            )

        scored.sort(key=lambda x: x[0], reverse=True)
        logger.info("keyword_rerank.done", total=len(hits), kept=top_k)
        return [h for _, h in scored[:top_k]]


class CrossEncoderReranker(Reranker):
    """bge-reranker-v2-m3 via sentence-transformers CrossEncoder.

    Preferito a FlagEmbedding (API tokenizer incompatibile con transformers
    recenti). Su Apple Silicon usare device="mps": ~1.5-3s per 30 coppie.
    """

    def __init__(
        self,
        model_name: str = "BAAI/bge-reranker-v2-m3",
        *,
        device: str = "cpu",
        batch_size: int = 16,
        max_length: int = 512,
    ) -> None:
        self._model_name = model_name
        self._device = device
        self._batch_size = batch_size
        self._max_length = max_length
        self._model: Any = None

    def warm_up(self) -> None:
        """Carica il modello e fa una predict di riscaldamento (bloccante)."""
        model = self._lazy_load()
        model.predict([("warm", "up")], batch_size=1)

    def _lazy_load(self) -> Any:
        if self._model is None:
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(
                self._model_name,
                device=self._device,
                max_length=self._max_length,
            )
        return self._model

    async def rerank(
        self, query: str, hits: Sequence[RetrievalHit], top_k: int
    ) -> list[RetrievalHit]:
        if not hits:
            return []
        import asyncio

        model = self._lazy_load()
        pairs = [(query, h.text) for h in hits]

        def _score() -> list[float]:
            raw = model.predict(pairs, batch_size=self._batch_size)
            return [float(x) for x in raw]

        scores = await asyncio.to_thread(_score)
        reranked = []
        for h, score in zip(hits, scores, strict=True):
            # Il cross-encoder giudica solo il testo: i segnali deterministici
            # (lookup diretto per numero, abrogazione) restano dei correttivi.
            adj = score
            if h.metadata.get("lookup") == "direct":
                adj += 1.0
            if h.metadata.get("abrogato"):
                adj -= 0.5
            reranked.append(h.model_copy(update={"score_rerank": score, "score_final": adj}))
        reranked.sort(key=lambda h: h.score_final, reverse=True)
        logger.info("cross_encoder_rerank.done", total=len(reranked), kept=top_k)
        return reranked[:top_k]


class CohereReranker(Reranker):
    """Cross-encoder Cohere rerank-multilingual-v3.0 (SaaS, no GPU locale)."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "rerank-multilingual-v3.0",
    ) -> None:
        self._api_key = api_key
        self._model = model

    async def rerank(
        self, query: str, hits: Sequence[RetrievalHit], top_k: int
    ) -> list[RetrievalHit]:
        if not hits:
            return []

        import httpx

        docs = [h.text or " " for h in hits]
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                "https://api.cohere.com/v1/rerank",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self._model,
                    "query": query,
                    "documents": docs,
                    "top_n": min(top_k, len(hits)),
                },
            )
            resp.raise_for_status()
            data = resp.json()

        by_idx = {r["index"]: float(r["relevance_score"]) for r in data["results"]}
        reranked = [
            h.model_copy(
                update={
                    "score_rerank": by_idx[i],
                    "score_final": by_idx[i],
                }
            )
            for i, h in enumerate(hits)
            if i in by_idx
        ]
        reranked.sort(key=lambda h: h.score_final, reverse=True)
        logger.info("cohere_rerank.done", total=len(hits), kept=len(reranked))
        return reranked[:top_k]


def _tokenize(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-zà-ù0-9]+", text.lower()) if len(t) > 2]


def _extract_rubrica(text: str) -> str | None:
    # Il chunker scrive "[Rubrica] <testo>" negli articolo-full e
    # "[Fonte] Titolo — art. N (<rubrica>), comma M" nei chunk comma.
    m = re.search(r"\[Rubrica\]\s*([^\n]+)", text, re.I)
    if m:
        return m.group(1).strip()
    m = re.search(r"\[Fonte\][^\n(]*\(([^)]+)\)", text, re.I)
    return m.group(1).strip() if m else None
