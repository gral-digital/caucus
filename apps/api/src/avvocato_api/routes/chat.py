"""Endpoint di chat RAG sui codici.

Flusso:
  user query → retrieval + rerank → prompt assembly → LLM stream SSE
             → frontend parsea <cite source="cc" num="..."/> e linka

Lo streaming è SSE (not WebSocket) per semplicità e cacheability via Cloud Run.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import orjson
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from avvocato_api.services.chat_service import ChatService
from avvocato_rag_core.schemas.retrieval import CorpusFilter

router = APIRouter()


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=2, max_length=4000)
    corpora: list[CorpusFilter] = Field(default_factory=lambda: [CorpusFilter.CODICI])
    sources: list[str] | None = Field(
        None,
        description="Filtro opzionale short_id fonti, es. ['cc', 'cp']. Default: tutte.",
    )
    effective_at: str | None = Field(
        None, description="ISO date per stato normativo vigente a quella data."
    )


@router.post("/chat")
async def chat_stream(
    body: ChatRequest,
    service: ChatService = Depends(ChatService.factory),
) -> EventSourceResponse:
    """Stream SSE. Eventi:

    - `retrieval`: {hits: [...]}  → inviato subito dopo il retrieval.
    - `token`: {text: "..."}       → chunk di testo LLM.
    - `done`:  {finish_reason}     → fine risposta.
    - `error`: {message}           → errore recuperabile.
    """

    async def events() -> AsyncIterator[dict[str, str]]:
        async for evt in service.answer_stream(body):
            yield {
                "event": evt.name,
                "data": orjson.dumps(evt.data).decode(),
            }

    return EventSourceResponse(events())
