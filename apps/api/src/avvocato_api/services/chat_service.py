"""Service di chat RAG. Orchestrazione: retrieval → prompt assembly → stream LLM."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import date
from typing import Any

import structlog
from fastapi import Depends

from avvocato_api.deps import get_llm_router
from avvocato_api.services.search_service import SearchService
from avvocato_rag_core.llm.router import LLMMessage, LLMRouter
from avvocato_rag_core.schemas.retrieval import RetrievalHit, RetrievalQuery

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class ChatEvent:
    name: str
    data: dict[str, Any]


SYSTEM_PROMPT = """Sei un assistente legale per avvocati italiani.

REGOLE INDEROGABILI:
1. Rispondi SEMPRE in italiano giuridico preciso e conciso.
2. Ogni affermazione normativa DEVE essere supportata da una citazione a una fonte nel contesto fornito.
3. Le citazioni vanno rese nel formato: <cite source="SHORT_ID" part="articolo" num="N" comma="C"/>
   dove SHORT_ID è uno di: cc (codice civile), cp (codice penale), cpc, cpp, cost, e le altre fonti presenti nel contesto.
4. Se il contesto non contiene basi sufficienti, rispondi: "Non ho trovato una base normativa sufficiente nel corpus indicizzato per rispondere con certezza."
   NON inventare citazioni. NON attingere a conoscenza pregressa.
5. Mai dare pareri vincolanti: sei uno strumento di supporto, non un sostituto dell'avvocato.
6. Se la domanda tocca materia penale/processuale con impatto su libertà personale, aggiungi un disclaimer invitando a verifica diretta dei testi e della giurisprudenza aggiornata.

Struttura della risposta quando possibile:
- Sintesi (1-3 frasi)
- Base normativa (con citazioni)
- Note / eccezioni / giurisprudenza rilevante (se presente nel contesto)
"""


class ChatService:
    def __init__(self, search: SearchService, llm: LLMRouter) -> None:
        self._search = search
        self._llm = llm

    @classmethod
    def factory(
        cls,
        search: SearchService = Depends(SearchService.factory),
        llm: LLMRouter = Depends(get_llm_router),
    ) -> "ChatService":
        return cls(search=search, llm=llm)

    async def answer_stream(self, request) -> AsyncIterator[ChatEvent]:  # type: ignore[no-untyped-def]
        # 1. Retrieve
        effective = date.fromisoformat(request.effective_at) if request.effective_at else None
        query = RetrievalQuery(
            text=request.question,
            corpora=request.corpora,
            sources=request.sources,
            effective_at=effective,
            top_k_retrieve=50,
            top_k_rerank=8,
        )
        result = await self._search.search(query)

        yield ChatEvent(
            name="retrieval",
            data={
                "hits": [self._hit_summary(h) for h in result.hits],
                "latency_ms": result.latency_ms,
            },
        )

        if not result.hits:
            yield ChatEvent(
                name="token",
                data={
                    "text": "Non ho trovato una base normativa sufficiente nel corpus indicizzato per rispondere con certezza."
                },
            )
            yield ChatEvent(name="done", data={"finish_reason": "no_context"})
            return

        # 2. Prompt assembly
        messages = [
            LLMMessage(role="system", content=SYSTEM_PROMPT),
            LLMMessage(
                role="user",
                content=self._assemble_user_prompt(request.question, result.hits),
            ),
        ]

        # 3. Stream LLM
        try:
            async for chunk in self._llm.chat_stream(messages):
                if chunk.content:
                    yield ChatEvent(name="token", data={"text": chunk.content})
                if chunk.finish_reason:
                    yield ChatEvent(
                        name="done", data={"finish_reason": chunk.finish_reason}
                    )
                    return
        except Exception as exc:  # pragma: no cover - runtime-only
            logger.exception("llm_stream_failed")
            yield ChatEvent(name="error", data={"message": str(exc)})

    @staticmethod
    def _hit_summary(hit: RetrievalHit) -> dict[str, Any]:
        return {
            "chunk_id": str(hit.chunk_id),
            "citation_display": hit.citation.to_display() if hit.citation else None,
            "citation_anchor": hit.citation.to_anchor() if hit.citation else None,
            "score": hit.score_final,
            "excerpt": hit.text[:240],
        }

    @staticmethod
    def _assemble_user_prompt(question: str, hits: list[RetrievalHit]) -> str:
        context_blocks: list[str] = []
        for idx, hit in enumerate(hits, start=1):
            citation = hit.citation.to_display() if hit.citation else "fonte-sconosciuta"
            cite_tag = (
                f'<cite source="{hit.citation.source}" part="articolo" num="{hit.citation.num}"'
                + (f' comma="{hit.citation.comma}"' if hit.citation and hit.citation.comma else "")
                + "/>"
                if hit.citation
                else ""
            )
            context_blocks.append(
                f"[{idx}] {citation}\n"
                f"TAG_CANONICO: {cite_tag}\n"
                f"TESTO:\n{hit.text}\n"
            )

        return (
            f"DOMANDA: {question}\n\n"
            "CONTESTO NORMATIVO (usa esclusivamente questo per le citazioni; "
            "non introdurre riferimenti non presenti):\n\n"
            + "\n---\n".join(context_blocks)
            + "\n\nRispondi seguendo le regole del system prompt."
        )
