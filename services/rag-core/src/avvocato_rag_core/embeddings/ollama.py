"""Ollama embedding provider.

Per sviluppo locale (Mac, zero cloud, zero costi). Usa l'API REST nativa di
Ollama, senza dipendenze Python pesanti (niente torch / FlagEmbedding).

In produzione si sostituisce con :class:`VertexEmbeddingProvider` cambiando
solo la factory — l'interfaccia :class:`EmbeddingProvider` è la stessa.
"""

from __future__ import annotations

from collections.abc import Sequence

import httpx
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from avvocato_rag_core.embeddings.base import EmbeddingProvider, EmbeddingVector


class OllamaEmbeddingProvider(EmbeddingProvider):
    """Chiama ``POST /api/embed`` di Ollama per dense embeddings.

    Note:
      - Ollama non restituisce sparse embedding, solo dense. Per hybrid search
        reale serve bge-m3 via FlagEmbedding o un endpoint che esponga sparse.
        Lo scenario dev/MVP su Ollama funziona benissimo con solo dense.
      - Il modello di default è ``bge-m3`` (1024-dim, multilingual).
    """

    def __init__(
        self,
        *,
        base_url: str = "http://localhost:11434",
        model: str = "bge-m3",
        dense_dim: int = 1024,
        timeout: float = 300.0,
        max_retries: int = 5,
        batch_size: int = 8,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._dense_dim = dense_dim
        self._timeout = timeout
        self._max_retries = max_retries
        self._batch_size = batch_size
        # Timeout granulare: connect veloce, read/write lunghi perché Ollama
        # con bge-m3 su Apple Silicon può fare cold-start di ~10 s e batch
        # lunghi possono prendere 30-60 s ciascuno.
        self._http = http_client or httpx.AsyncClient(
            timeout=httpx.Timeout(timeout, connect=10.0),
        )

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def dense_dim(self) -> int:
        return self._dense_dim

    async def embed(
        self,
        texts: Sequence[str],
        *,
        kind: str = "passage",
    ) -> list[EmbeddingVector]:
        del kind  # bge-m3 non richiede prefix
        if not texts:
            return []

        url = f"{self._base_url}/api/embed"
        vectors: list[EmbeddingVector] = []

        # Ollama accetta un array `input`, ma batch grandi possono saturare
        # la RAM del server. Suddividiamo in micro-batch.
        for start in range(0, len(texts), self._batch_size):
            chunk = list(texts[start : start + self._batch_size])

            async for attempt in self._retry():
                with attempt:
                    resp = await self._http.post(
                        url,
                        json={"model": self._model, "input": chunk},
                    )
                    resp.raise_for_status()

            data = resp.json()
            embeddings = data.get("embeddings", [])
            if len(embeddings) != len(chunk):
                raise RuntimeError(
                    f"Ollama /api/embed: expected {len(chunk)} vectors, got {len(embeddings)}"
                )
            for emb in embeddings:
                vectors.append(EmbeddingVector(dense=list(emb)))

        return vectors

    def _retry(self) -> AsyncRetrying:
        return AsyncRetrying(
            stop=stop_after_attempt(self._max_retries),
            wait=wait_exponential(multiplier=1.5, min=1, max=15),
            retry=retry_if_exception_type(httpx.HTTPError),
            reraise=True,
        )

    async def aclose(self) -> None:
        await self._http.aclose()
