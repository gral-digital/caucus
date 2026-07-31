"""Embedding provider locale basato su sentence-transformers (bge-m3).

Richiede `pip install caucus-rag-core[embeddings-local]`. Usato in dev e per
batch ingestion offline. In prod si usa Vertex (più scalabile, no GPU on-host).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from caucus_rag_core.embeddings.base import (
    EmbeddingProvider,
    EmbeddingVector,
    SparseVector,
)

if TYPE_CHECKING:
    from FlagEmbedding import BGEM3FlagModel


class LocalBGEM3Provider(EmbeddingProvider):
    """bge-m3 via FlagEmbedding (dense + sparse nello stesso forward)."""

    def __init__(
        self,
        model_name: str = "BAAI/bge-m3",
        *,
        device: str = "cpu",
        use_fp16: bool = False,
        batch_size: int = 8,
        max_length: int = 8192,
    ) -> None:
        self._model_name = model_name
        self._device = device
        self._use_fp16 = use_fp16
        self._batch_size = batch_size
        self._max_length = max_length
        self._model: BGEM3FlagModel | None = None

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dense_dim(self) -> int:
        return 1024  # fixed per bge-m3

    def _lazy_load(self) -> BGEM3FlagModel:
        if self._model is None:
            # Import lazy per non forzare torch in runtime che non usa embeddings locali.
            from FlagEmbedding import BGEM3FlagModel

            self._model = BGEM3FlagModel(
                self._model_name,
                use_fp16=self._use_fp16,
                device=self._device,
            )
        return self._model

    async def embed(
        self,
        texts: Sequence[str],
        *,
        kind: str = "passage",
    ) -> list[EmbeddingVector]:
        del kind  # bge-m3 non richiede prefix
        model = self._lazy_load()

        # FlagEmbedding è sync + CPU/GPU-bound → esegui in thread per non bloccare l'event loop.
        import asyncio

        def _encode() -> dict[str, Any]:
            return model.encode(  # type: ignore[no-any-return]
                list(texts),
                batch_size=self._batch_size,
                max_length=self._max_length,
                return_dense=True,
                return_sparse=True,
                return_colbert_vecs=False,
            )

        output = await asyncio.to_thread(_encode)
        dense_vecs = output["dense_vecs"]
        sparse_vecs = output["lexical_weights"]

        vectors: list[EmbeddingVector] = []
        for dense, sparse in zip(dense_vecs, sparse_vecs, strict=True):
            indices = [int(k) for k in sparse]
            values = [float(v) for v in sparse.values()]
            vectors.append(
                EmbeddingVector(
                    dense=dense.tolist() if hasattr(dense, "tolist") else list(dense),
                    sparse=SparseVector(indices=indices, values=values),
                )
            )
        return vectors
