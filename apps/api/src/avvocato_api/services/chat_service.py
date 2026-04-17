"""Service di chat RAG. Orchestrazione: retrieval → prompt assembly → stream LLM."""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import date
from typing import Any

import structlog
from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from avvocato_api.db.models import NormPartition, NormSource
from avvocato_api.deps import get_db_session, get_llm_router
from avvocato_api.services.search_service import SearchService
from avvocato_rag_core.llm.router import LLMMessage, LLMRouter
from avvocato_rag_core.schemas.retrieval import RetrievalHit, RetrievalQuery

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class ChatEvent:
    name: str
    data: dict[str, Any]


SYSTEM_PROMPT = """Sei **Avvocato**, un assistente AI che affianca un avvocato italiano nel dialogo col cliente.

# Come parli
- Tono: avvocato difensore italiano senior, 20 anni di foro. Pratico, sintetico, umano.
- Dai del "tu" al cliente. Niente preamboli burocratici ("In relazione alla sua cortese richiesta…").
- **Lunghezza adatta alla domanda**: a un saluto rispondi con un saluto, a una domanda semplice una frase, a una situazione complessa quello che serve. **NON** riempire template se non c'è nulla da dire in quella sezione.
- Se mancano fatti essenziali, **fai domande** prima di parlare di diritto. Esempi: "Com'era il tasso alcolemico contestato?", "È la prima volta?", "Hai già ricevuto un decreto o solo verbale?".
- Nessuna sezione titolata "Norma applicabile / Strategia difensiva / Azioni concrete / Disclaimer" a priori — usa titoletti in grassetto **solo** quando la complessità lo rende utile.
- Empatia dove serve. Non stai compilando un modulo, stai parlando con una persona nei guai.

# Cosa fai
Difendi il cliente nei limiti della legge. Quando la domanda è una situazione concreta:
1. Qualifica brevemente il fatto.
2. Indica le **vie di difesa realistiche**: contestazioni procedurali, cause di non punibilità, attenuanti, **riti alternativi e benefici** (patteggiamento, messa alla prova, oblazione, lavoro di pubblica utilità, sospensione condizionale, tenuità del fatto) quando pertinenti.
3. Suggerisci 1-3 **prossime mosse concrete** (cosa raccogliere, chi contattare, termini).
4. Se si parla di libertà personale, ricorda al cliente di contattare subito un avvocato in carne e ossa.

Quando la domanda è astratta (esame, studio, curiosità), rispondi brevemente in modo didattico.

# Regole che NON si negoziano

1. **Solo italiano giuridico preciso.**

2. **Citazioni solo dal contesto fornito**. Ogni riferimento normativo deve corrispondere **esattamente** a un articolo presente nel blocco CONTESTO sotto.
   - Formato: `<cite source="SHORT_ID" part="articolo" num="N" comma="C"/>` (comma opzionale).
   - **SHORT_ID ammessi**: solo quelli che appaiono nel CONTESTO. Non scrivere mai "art. X c.p." in testo libero senza il tag.
   - Se nel CONTESTO non c'è la norma giusta per rispondere, **ammettilo**: «Nel corpus indicizzato non trovo la norma che regola questo caso — ti consiglio di verificare direttamente con il tuo avvocato / il testo aggiornato. È probabile si tratti di [nome ipotizzato], che qui non è indicizzato.» **Non** inventare numeri di articolo o rubriche.

3. **Niente condotte illegali**. Se il cliente chiede *come* commettere, eludere, nascondere, distruggere, falsificare, subornare, evadere, fuggire, sottrarsi → **rifiuta direttamente** in una-due frasi, senza template:
   > «Su questo non posso aiutarti: sarebbe un reato autonomo. Se il problema è già aperto (accertamento, denuncia, contestazione) posso aiutarti a inquadrare la difesa.»
   Niente "strategia difensiva" per fingere di rispondere comunque. La richiesta è off-limits, punto.

4. **Memoria della conversazione**: leggi i turni precedenti, non ripartire da zero. Se il cliente ti dice un nuovo dettaglio che cambia l'inquadramento, incorporalo.

5. **Niente pareri vincolanti su esito processuale** («verrai assolto», «non rischi nulla»). Usa "probabile", "in molti casi", "dipende da X".

6. Se la domanda è un saluto o chiacchiera, rispondi umano, non in modalità avvocato.

# Formato
Markdown: `**grassetto**`, `- liste`, paragrafi separati. I tag `<cite/>` vengono trasformati in link dall'UI.
"""


class ChatService:
    def __init__(
        self, search: SearchService, llm: LLMRouter, session: AsyncSession
    ) -> None:
        self._search = search
        self._llm = llm
        self._session = session

    @classmethod
    def factory(
        cls,
        search: SearchService = Depends(SearchService.factory),
        llm: LLMRouter = Depends(get_llm_router),
        session: AsyncSession = Depends(get_db_session),
    ) -> "ChatService":
        return cls(search=search, llm=llm, session=session)

    async def answer_stream(self, request) -> AsyncIterator[ChatEvent]:  # type: ignore[no-untyped-def]
        # 1. Retrieve — usa come query il messaggio corrente + ultimo user turn
        # del contesto, per non perdere riferimenti in follow-up brevi.
        retrieval_query_text = self._build_retrieval_query(request)
        effective = date.fromisoformat(request.effective_at) if request.effective_at else None
        query = RetrievalQuery(
            text=retrieval_query_text,
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

        # 2. Prompt assembly con storico conversazione
        system_content = SYSTEM_PROMPT
        if result.hits:
            system_content += "\n\n" + self._assemble_context_block(result.hits)
        else:
            system_content += (
                "\n\n# CONTESTO NORMATIVO\n"
                "_Il retriever non ha trovato riscontri per questa domanda._ "
                "Se la domanda è una situazione fattuale, ammettilo: «Nel corpus "
                "indicizzato non trovo la norma per questo caso» e NON inventare "
                "numeri di articolo. Se è un saluto o chiacchiera, rispondi umano."
            )

        messages: list[LLMMessage] = [LLMMessage(role="system", content=system_content)]
        # Storico: gli ultimi 10 turni (user+assistant) per non saturare il contesto
        # di Qwen3:8b (~32k token). Il retrieval è basato sul turno corrente quindi
        # non servono i vecchi messaggi ai fini delle citazioni, ma servono per
        # continuità di dialogo.
        for m in (request.history or [])[-10:]:
            role = m.role if m.role in ("user", "assistant") else "user"
            messages.append(LLMMessage(role=role, content=m.content))
        messages.append(LLMMessage(role="user", content=request.question))

        # 3. Stream LLM, bufferizzando il testo per validare le citazioni finali
        raw_text_parts: list[str] = []
        try:
            async for chunk in self._llm.chat_stream(messages):
                if chunk.content:
                    raw_text_parts.append(chunk.content)
                    yield ChatEvent(name="token", data={"text": chunk.content})
                if chunk.finish_reason:
                    # 4. Validazione citazioni contro DB
                    raw = "".join(raw_text_parts)
                    validation = await self._validate_citations(raw, result.hits)
                    if validation["invalid"]:
                        yield ChatEvent(
                            name="citation_warnings",
                            data=validation,
                        )
                    yield ChatEvent(
                        name="done", data={"finish_reason": chunk.finish_reason}
                    )
                    return
        except Exception as exc:  # pragma: no cover - runtime-only
            logger.exception("llm_stream_failed")
            yield ChatEvent(name="error", data={"message": str(exc)})

    # ------------------------------------------------------------------

    @staticmethod
    def _build_retrieval_query(request) -> str:  # type: ignore[no-untyped-def]
        """Compone il testo per la query di retrieval.

        Strategia: se il turno corrente è breve ("sì", "certo", "spiega"),
        lo arricchisce con l'ultimo turno utente per non perdere contesto.
        Altrimenti usa solo il turno corrente.
        """
        q = request.question.strip()
        if len(q) >= 25 or not request.history:
            return q
        # Cerca l'ultimo turno user nello storico
        last_user = next(
            (m.content for m in reversed(request.history) if m.role == "user"),
            None,
        )
        if last_user:
            return f"{last_user}\n\n{q}"
        return q

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
    def _assemble_context_block(hits: list[RetrievalHit]) -> str:
        blocks: list[str] = []
        for idx, hit in enumerate(hits, start=1):
            if hit.citation is None:
                continue
            cite_tag = (
                f'<cite source="{hit.citation.source}" part="articolo" num="{hit.citation.num}"'
                + (f' comma="{hit.citation.comma}"' if hit.citation.comma else "")
                + "/>"
            )
            blocks.append(
                f"[{idx}] {hit.citation.to_display()}   tag: {cite_tag}\n"
                f"    {hit.text.strip()}"
            )
        return (
            "# CONTESTO NORMATIVO (unica fonte ammessa per le citazioni)\n\n"
            + "\n\n".join(blocks)
            + "\n\n> Puoi citare SOLO le norme elencate sopra usando i tag indicati. "
            "Se la norma giusta per la domanda non è nell'elenco, ammettilo anziché inventarla."
        )

    # ------------------------------------------------------------------
    # Validazione citazioni post-generazione
    # ------------------------------------------------------------------

    _CITE_PATTERN = re.compile(
        r'<cite\s+source="([a-z0-9-]+)"\s+part="[a-z]+"\s+num="([^"]+)"(?:\s+comma="[^"]+")?\s*/>',
        re.IGNORECASE,
    )

    # Pattern che intercetta citazioni in linguaggio naturale scritte dal
    # modello fuori dal tag <cite/>. Qwen3:8b spesso le produce così ("art. 43-bis c.p.").
    # Catturiamo: numero articolo + eventuale bis/ter + sigla del codice.
    _FREEFORM_CITE_PATTERN = re.compile(
        r"\bart(?:icolo)?\.?\s+"
        r"([0-9]+(?:[-\s]?(?:bis|ter|quater|quinquies|sexies|septies|octies|novies|decies))?)"
        r"(?:\s*,?\s*c(?:omma)?\.?\s*([0-9]+(?:[-\s]?(?:bis|ter|quater))?))?"
        r"\s+"
        r"(c\.?\s*c\.?|c\.?\s*p\.?|c\.?\s*p\.?\s*c\.?|c\.?\s*p\.?\s*p\.?|"
        r"cost\.?|cod\.?\s*strada|cds|cdc|ccii|ccp|cad|cts|"
        r"tu\s*stup\.?|tu\s*imm\.?|tu\s*ed\.?|tu\s*sic\.?|tub|tuf|tuir|"
        r"cod\.?\s*privacy|l\.?\s*241|st\.?\s*lav\.?|l\.?\s*689|l\.?\s*247)",
        re.IGNORECASE,
    )

    _SUFFIX_TO_SHORT_ID = {
        "cc": "cc", "c.c": "cc", "c. c": "cc",
        "cp": "cp", "c.p": "cp", "c. p": "cp",
        "cpc": "cpc", "c.p.c": "cpc", "c. p. c": "cpc", "c.p. c": "cpc",
        "cpp": "cpp", "c.p.p": "cpp", "c. p. p": "cpp",
        "cost": "cost",
        "cds": "cds", "cod. strada": "cds", "cod strada": "cds",
        "cdc": "cdc", "cod. cons": "cdc",
        "ccii": "ccii",
        "ccp": "ccp", "cod. contr. pubbl": "ccp",
        "cad": "cad",
        "cts": "cts",
        "tu stup": "tus", "tus": "tus",
        "tu imm": "tui", "tui": "tui",
        "tu ed": "tue", "tue": "tue",
        "tu sic": "tusl", "tu sic. lav": "tusl", "tusl": "tusl",
        "tub": "tub",
        "tuf": "tuf",
        "tuir": "tuir",
        "cod. privacy": "cpriv", "cpriv": "cpriv",
        "l. 241": "l241", "l 241": "l241",
        "st. lav": "stat", "st lav": "stat",
        "l. 689": "l689", "l 689": "l689",
        "l. 247": "lpf", "l 247": "lpf",
    }

    @classmethod
    def _normalize_suffix(cls, suffix: str) -> str | None:
        """Normalizza una sigla come scritta dal LLM a un short_id interno."""
        s = re.sub(r"\s+", " ", suffix.lower().replace(".", ".")).strip()
        # Ripuliamo: "c.c." → "cc", "c. p." → "cp", ecc.
        no_dots = s.replace(".", "").replace(" ", "")
        if no_dots in cls._SUFFIX_TO_SHORT_ID:
            return cls._SUFFIX_TO_SHORT_ID[no_dots]
        return cls._SUFFIX_TO_SHORT_ID.get(s)

    async def _validate_citations(
        self, text: str, hits: list[RetrievalHit]
    ) -> dict[str, Any]:
        """Estrae tutte le citazioni (tag <cite/> e testo libero) e le verifica contro DB.

        Il modello piccolo spesso cita in prosa ("art. 17 c.p.") invece di usare
        il tag canonico. Catturiamo entrambe le forme.

        Ritorna: {valid: [...], invalid: [...], total: N}
        """
        citations: list[dict[str, str]] = []

        # Tag canonici
        for s, n in self._CITE_PATTERN.findall(text):
            citations.append({"source": s.lower(), "num": n.lower(), "form": "tag"})

        # Testo libero — normalizza la sigla
        for m in self._FREEFORM_CITE_PATTERN.finditer(text):
            num = re.sub(r"\s+", "-", m.group(1).strip()).lower()
            suffix = m.group(3)
            short = self._normalize_suffix(suffix)
            if short is None:
                continue
            citations.append({"source": short, "num": num, "form": "prose"})

        if not citations:
            return {"valid": [], "invalid": [], "total": 0}

        # Dedup
        seen: set[tuple[str, str]] = set()
        unique = []
        for c in citations:
            k = (c["source"], c["num"])
            if k not in seen:
                seen.add(k)
                unique.append(c)

        # Sources → ids
        sources_present = {c["source"] for c in unique}
        src_rows = await self._session.execute(
            select(NormSource.short_id, NormSource.id).where(
                NormSource.short_id.in_(list(sources_present))
            )
        )
        src_map: dict[str, Any] = {r.short_id: r.id for r in src_rows}

        valid: list[dict[str, str]] = []
        invalid: list[dict[str, str]] = []
        for c in unique:
            source_id = src_map.get(c["source"])
            if source_id is None:
                invalid.append({**c, "reason": "fonte non indicizzata"})
                continue
            exists = await self._session.execute(
                select(NormPartition.id)
                .where(NormPartition.source_id == source_id)
                .where(NormPartition.kind == "articolo")
                .where(NormPartition.number == c["num"])
                .limit(1)
            )
            if exists.scalar_one_or_none() is not None:
                valid.append(c)
            else:
                invalid.append({**c, "reason": "articolo non esistente nel DB"})

        # Hit-grounded check: era tra i passaggi forniti al LLM?
        hit_keys = {
            (h.citation.source.lower(), h.citation.num.lower())
            for h in hits
            if h.citation is not None
        }
        for c in valid:
            if (c["source"], c["num"]) not in hit_keys:
                # Esiste nel DB ma NON era nel contesto fornito al LLM
                c["grounding"] = "weak"  # suggerimento, non errore
            else:
                c["grounding"] = "strong"

        if invalid:
            logger.warning(
                "citation_hallucinated",
                total=len(unique),
                invalid=len(invalid),
                examples=invalid[:3],
            )
        return {"valid": valid, "invalid": invalid, "total": len(unique)}
