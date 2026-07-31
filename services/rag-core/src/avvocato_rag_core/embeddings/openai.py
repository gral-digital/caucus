"""OpenAI embedding provider via LiteLLM.

Usato in dev/prod SaaS quando non si vuole dipendere da Ollama/torch locali.
Default: ``text-embedding-3-small`` (1536-dim, ottimo rapporto qualità/costo).
"""

from __future__ import annotations

from collections.abc import Sequence

import structlog

from avvocato_rag_core.embeddings.base import EmbeddingProvider, EmbeddingVector

logger = structlog.get_logger(__name__)


class OpenAIEmbeddingProvider(EmbeddingProvider):
    """Embeddings dense via OpenAI API (``litellm.aembedding``)."""

    def __init__(
        self,
        *,
        model: str = "text-embedding-3-small",
        dense_dim: int = 1536,
        api_key: str | None = None,
        batch_size: int = 64,
    ) -> None:
        import litellm

        self._litellm = litellm
        self._model = model
        self._dense_dim = dense_dim
        self._api_key = api_key
        self._batch_size = batch_size

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
        del kind
        if not texts:
            return []

        vectors: list[EmbeddingVector] = []
        for start in range(0, len(texts), self._batch_size):
            chunk = list(texts[start : start + self._batch_size])
            kwargs: dict[str, object] = {
                "model": self._model,
                "input": chunk,
                "dimensions": self._dense_dim,
            }
            if self._api_key:
                kwargs["api_key"] = self._api_key

            resp = await self._litellm.aembedding(**kwargs)
            data = sorted(resp.data, key=lambda row: row["index"])
            for row in data:
                emb = row["embedding"]
                if len(emb) != self._dense_dim:
                    raise RuntimeError(
                        f"OpenAI embedding dim mismatch: expected {self._dense_dim}, got {len(emb)}"
                    )
                vectors.append(EmbeddingVector(dense=list(emb)))

        logger.debug(
            "openai_embed.done",
            model=self._model,
            n=len(vectors),
            dim=self._dense_dim,
        )
        return vectors
