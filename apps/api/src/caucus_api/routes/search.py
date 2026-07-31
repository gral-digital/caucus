"""Endpoint di ricerca diretta: restituisce hit rankati senza generazione LLM.

Utile per:
- Debug del retriever
- Integrazioni che vogliono i chunk raw (es. citation browser della UI)
- Valutazione offline (recall@k, mrr, ndcg)
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from caucus_api.deps import rate_limit, require_api_auth
from caucus_api.services.search_service import SearchService
from caucus_rag_core.schemas.retrieval import RetrievalQuery, RetrievalResult

router = APIRouter(dependencies=[Depends(require_api_auth), Depends(rate_limit)])


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
    # tenant_id è un attributo di sicurezza: NON deve mai arrivare dal client
    # (IDOR pronto all'uso il giorno in cui l'indice contiene dati tenant).
    # Verrà popolato server-side dal contesto auth quando esisterà la tenancy.
    query = body.query.model_copy(update={"tenant_id": None})
    result = await service.search(query)
    return SearchResponse(result=result)
