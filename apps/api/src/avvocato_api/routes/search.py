"""Endpoint di ricerca diretta: restituisce hit rankati senza generazione LLM.

Utile per:
- Debug del retriever
- Integrazioni che vogliono i chunk raw (es. citation browser della UI)
- Valutazione offline (recall@k, mrr, ndcg)
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from avvocato_api.deps import get_corpus_map, get_llm_router, get_vectorstore  # noqa: F401
from avvocato_api.services.search_service import SearchService
from avvocato_rag_core.schemas.retrieval import RetrievalQuery, RetrievalResult

router = APIRouter()


class SearchRequest(BaseModel):
    query: RetrievalQuery


class SearchResponse(BaseModel):
    result: RetrievalResult = Field(..., description="Hit ordinati e score diagnostici.")


@router.post("/search", response_model=SearchResponse)
async def search(
    body: SearchRequest,
    service: SearchService = Depends(SearchService.factory),
) -> SearchResponse:
    """Retrieval hybrid + (opzionale) rerank. Nessuna generazione LLM."""
    result = await service.search(body.query)
    return SearchResponse(result=result)
