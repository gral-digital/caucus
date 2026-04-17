"""Schema per query di retrieval e risultati."""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from avvocato_rag_core.schemas.citation import NormCitation


class CorpusFilter(StrEnum):
    """Corpora (collection Qdrant) tra cui scegliere per una query."""

    CODICI = "codici"
    LEGGI = "leggi"
    CASSAZIONE = "cassazione"
    TENANT = "tenant"  # placeholder, diventa `tenant_<uuid>_docs` a runtime


class RetrievalQuery(BaseModel):
    """Query di retrieval hybrid."""

    model_config = ConfigDict(frozen=True)

    text: str = Field(..., min_length=1, max_length=4000)
    corpora: list[CorpusFilter] = Field(
        default_factory=lambda: [CorpusFilter.CODICI],
        description="Corpora su cui cercare. Ordine = priorità di fallback.",
    )
    sources: list[str] | None = Field(
        None,
        description="Filtro opzionale su short_id delle fonti (es. ['cc', 'cp']).",
    )
    effective_at: date | None = Field(
        None,
        description="Stato vigente al giorno indicato. None = oggi.",
    )
    top_k_retrieve: int = Field(50, ge=1, le=200)
    top_k_rerank: int = Field(8, ge=1, le=50)
    tenant_id: UUID | None = None


class RetrievalHit(BaseModel):
    """Un risultato di retrieval dopo reranking."""

    model_config = ConfigDict(frozen=True)

    chunk_id: UUID
    partition_id: UUID
    comma_id: UUID | None = None
    citation: NormCitation | None = Field(
        None,
        description="Citazione canonica derivata dal payload del chunk.",
    )
    text: str
    score_dense: float | None = None
    score_sparse: float | None = None
    score_rerank: float | None = None
    score_final: float
    metadata: dict[str, Any] = Field(default_factory=dict)


class RetrievalResult(BaseModel):
    """Risultato completo di una query."""

    model_config = ConfigDict(frozen=True)

    query: RetrievalQuery
    hits: list[RetrievalHit]
    total_retrieved: int
    latency_ms: int
    used_corpora: list[CorpusFilter]
