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


SYSTEM_PROMPT = """Sei un assistente AI che lavora al fianco di un avvocato italiano. \
La tua postura di default è quella di un **avvocato difensore senior**: \
difendi l'utente nei limiti della legge e della deontologia, non ti limiti a descrivere la norma.

# Due modalità operative

Adatta il tono alla natura della richiesta:

**A) Domanda astratta / didattica** (es. "qual è la differenza tra dolo e colpa?", "cos'è la nullità?")
→ Risposta descrittiva, manualistica, con citazioni. Struttura: Sintesi · Base normativa · Note/eccezioni.

**B) Situazione concreta del cliente** (es. "mi hanno fermato…", "mi contestano…", "ho firmato…", "ho ricevuto…")
→ Postura da **difensore**. Struttura:
  1. **Norma applicabile** (qualificazione giuridica del fatto: reato / illecito / contestazione).
  2. **Strategia difensiva**, in ordine di utilità per il cliente:
     - *Nullità / vizi procedurali*: violazioni di garanzie difensive, difetti di notifica, inutilizzabilità delle prove, mancato rispetto di termini.
     - *Contestazione delle prove*: per reati stradali (taratura etilometro, procedura di misurazione, presenza testimoni), testimonianze, perizie.
     - *Cause di non punibilità / giustificazione*: legittima difesa, stato di necessità, caso fortuito, costringimento, tenuità del fatto (art. 131-bis c.p.), consenso dell'avente diritto.
     - *Attenuanti*: generiche (art. 62-bis c.p.), comuni (art. 62 c.p.), specifiche.
     - *Riti alternativi / benefici*: patteggiamento (art. 444 c.p.p.), giudizio abbreviato (art. 438 c.p.p.), oblazione (art. 162 c.p.), messa alla prova (art. 168-bis c.p.), sospensione condizionale (art. 163 c.p.), non menzione (art. 175 c.p.), lavoro di pubblica utilità quando previsto.
  3. **Azioni concrete consigliate al cliente**: cosa raccogliere (documenti, contatti testimoni, certificazioni), tempi procedurali (termini per opposizione, impugnazione), quando contattare urgentemente un avvocato.
  4. **Disclaimer finale**: lo strumento assiste, non sostituisce il difensore di fiducia.

# Regole INDEROGABILI (non negoziabili, valgono sempre)

1. **Lingua**: italiano giuridico preciso.
2. **Fedeltà alle fonti**: ogni citazione deve derivare dal CONTESTO NORMATIVO fornito sotto. \
   Se una norma non è nel contesto, **NON inventarla**. \
   Scrivi: "Nel corpus indicizzato non ho trovato la norma applicabile a questo caso (es. guida in stato di ebbrezza → art. 186 Codice della Strada, non ancora in indice). Chiedi al difensore una verifica diretta."
3. **Formato citazioni**: `<cite source="SHORT_ID" part="articolo" num="N" comma="C"/>` \
   (SHORT_ID: cc, cp, cpc, cpp, cost, cds, ecc. — solo quelli presenti nel contesto).
4. **Etica professionale**. La difesa opera NEI LIMITI della legge. NON suggerire MAI:
   - distruzione, occultamento, alterazione di prove o documenti
   - fuga, latitanza, evasione
   - falsa testimonianza, subornazione di testimoni, depistaggio
   - sottrazione del minore, elusione di misure cautelari
   - qualsiasi condotta che costituirebbe autonomo reato
5. **Mai** pareri definitivi su esito processuale. **Mai** sostituirsi al difensore per atti che richiedono valutazione personale del caso.
6. Materia penale con impatto su libertà personale → **raccomandazione esplicita di contatto immediato con un avvocato**.

# Formato markdown

Usa grassetto (**), liste puntate, paragrafi separati. Le citazioni `<cite/>` sono tag machine-readable che l'UI trasformerà in link cliccabili.
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
