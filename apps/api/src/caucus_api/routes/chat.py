"""Endpoint di chat RAG sui codici.

Flusso:
  user query → retrieval + rerank → prompt assembly → LLM stream SSE
             → frontend parsea <cite source="cc" num="..."/> e linka

Lo streaming è SSE (not WebSocket) per semplicità e cacheability via Cloud Run.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Literal

import orjson
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from caucus_api.deps import get_session_maker, rate_limit, require_api_auth
from caucus_api.services.chat_service import ChatService
from caucus_rag_core.schemas.retrieval import CorpusFilter

router = APIRouter(dependencies=[Depends(require_api_auth), Depends(rate_limit)])


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    # Cap esplicito: la history è client-supplied e senza limite consentirebbe
    # payload da megabyte (costo LLM + memoria) prima di qualunque troncamento.
    content: str = Field(..., max_length=8000)


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=4000)
    history: list[ChatMessage] = Field(
        default_factory=list,
        max_length=40,
        description="Turni precedenti della conversazione corrente (user/assistant alternati). Esclude il turno attuale.",
    )
    corpora: list[CorpusFilter] = Field(
        default_factory=lambda: [CorpusFilter.CODICI, CorpusFilter.CASSAZIONE]
    )
    sources: list[str] | None = Field(
        None,
        description="Filtro opzionale short_id fonti, es. ['cc', 'cp']. Default: tutte.",
    )
    effective_at: str | None = Field(
        None, description="ISO date per stato normativo vigente a quella data."
    )
    document_ids: list[uuid.UUID] = Field(
        default_factory=list,
        max_length=3,
        description="Documenti caricati (POST /documents) da usare come contesto del turno.",
    )
    mode: Literal["ricerca", "analisi", "redazione", "giurisprudenza"] = Field(
        "ricerca",
        description="Modulo attivo: orienta comportamento e priorità dei corpora.",
    )


@router.post("/chat")
async def chat_stream(body: ChatRequest) -> EventSourceResponse:
    """Stream SSE. Eventi:

    - `retrieval`: {hits: [...]}  → inviato subito dopo il retrieval.
    - `token`: {text: "..."}       → chunk di testo LLM.
    - `citation_warnings`: {...}   → citazioni invalide/deboli/abrogate.
    - `done`:  {finish_reason, final_text} → fine risposta.
    - `error`: {message}           → errore recuperabile.

    NB: la sessione DB è aperta DENTRO il generatore, non come dependency
    `yield`: da FastAPI 0.106 le dependency vengono chiuse prima che il body
    streamato venga prodotto, quindi una sessione iniettata sarebbe già chiusa
    durante lo streaming (leak di connessioni dal pool sotto carico).
    """

    async def events() -> AsyncIterator[dict[str, str]]:
        async with get_session_maker()() as session:
            service = ChatService.build(session)
            async for evt in service.answer_stream(body):
                yield {
                    "event": evt.name,
                    "data": orjson.dumps(evt.data).decode(),
                }

    # no-transform: vieta a proxy intermedi di comprimere/bufferizzare lo
    # stream (la compressione del dev server Next consegnava tutti i token
    # in un colpo solo); X-Accel-Buffering copre nginx in produzione.
    return EventSourceResponse(
        events(),
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )
