"""Interfaccia astratta per embedding providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SparseVector:
    """Rappresentazione sparse (indici + valori) come prodotta da bge-m3."""

    indices: list[int]
    values: list[float]


@dataclass(frozen=True, slots=True)
class EmbeddingVector:
    """Embedding di un testo. Il sparse è opzionale (non tutti i modelli lo producono)."""

    dense: list[float]
    sparse: SparseVector | None = None


class EmbeddingProvider(ABC):
    """Protocol per fornire embeddings. Implementazioni: Vertex, SentenceTransformers."""

    @property
    @abstractmethod
    def model_name(self) -> str: ...

    @property
    @abstractmethod
    def dense_dim(self) -> int: ...

    @abstractmethod
    async def embed(
        self,
        texts: Sequence[str],
        *,
        kind: str = "passage",
    ) -> list[EmbeddingVector]:
        """Calcola embeddings.

        Args:
            texts: testi in input.
            kind: 'passage' per indicizzazione, 'query' per retrieval
                  (bge-m3 non richiede prefix ma altri sì).
        """
