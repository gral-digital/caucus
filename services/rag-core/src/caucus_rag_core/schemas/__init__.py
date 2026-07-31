"""Pydantic schemas pubblici di rag-core.

Sono le stesse entità descritte in docs/DATA_MODEL.md. Sono la fonte di verità
tipi che viene esposta all'API e rigenerata come TypeScript in packages/shared-types.
"""

from caucus_rag_core.schemas.citation import (
    CaseLawCitation,
    Citation,
    CitationKind,
    NormCitation,
)
from caucus_rag_core.schemas.norm import (
    NormChunk,
    NormChunkKind,
    NormComma,
    NormPartition,
    NormPartitionKind,
    NormSource,
    NormSourceType,
)
from caucus_rag_core.schemas.retrieval import (
    RetrievalHit,
    RetrievalQuery,
    RetrievalResult,
)

__all__ = [
    "CaseLawCitation",
    "Citation",
    "CitationKind",
    "NormChunk",
    "NormChunkKind",
    "NormCitation",
    "NormComma",
    "NormPartition",
    "NormPartitionKind",
    "NormSource",
    "NormSourceType",
    "RetrievalHit",
    "RetrievalQuery",
    "RetrievalResult",
]
