"""Embedding providers.

Supportiamo due backend:
- `vertex`: Vertex AI text-embedding / publisher models (prod, no GPU locale)
- `local`: SentenceTransformers locali con bge-m3 (dev, eval offline)

L'interfaccia comune è `EmbeddingProvider.embed(texts) -> list[EmbeddingVector]`.
"""

from caucus_rag_core.embeddings.base import (
    EmbeddingProvider,
    EmbeddingVector,
    SparseVector,
)

__all__ = ["EmbeddingProvider", "EmbeddingVector", "SparseVector"]
