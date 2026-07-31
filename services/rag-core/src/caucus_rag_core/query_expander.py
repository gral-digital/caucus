"""Query expansion LLM: dalla domanda del cliente alla terminologia giuridica.

Il gap lessicale tra come parla un utente («mi hanno fermato ubriaco»,
«responsabilità extracontrattuale») e come è scritto il testto normativo
(«guida sotto l'influenza dell'alcool», «risarcimento per fatto illecito»)
è la prima causa di retrieval miss con embedding dense. Una riscrittura LLM
economica (1 chiamata, ~150 token) chiude gran parte del gap.

Robustezza: qualunque errore/timeout → si usa la query originale. I numeri di
articolo eventualmente suggeriti dall'espansione NON alimentano il lookup
diretto (potrebbero essere allucinati): arricchiscono solo il testo per
embedding e FTS, dove un numero sbagliato è innocuo.
"""

from __future__ import annotations

import asyncio

import structlog

from caucus_rag_core.llm.router import LLMMessage, LLMRouter

logger = structlog.get_logger(__name__)

_SYSTEM = (
    "Sei un giurista italiano esperto di ricerca normativa. Riscrivi la domanda "
    "dell'utente come query di ricerca per un motore su testi normativi italiani "
    "ed europei: aggiungi gli istituti giuridici tecnici pertinenti, i sinonimi "
    "normativi e, se li conosci con certezza, i riferimenti (es. 'art. 2043 "
    "codice civile'). NON rispondere alla domanda. Output: SOLO la query "
    "arricchita, una riga, max 40 parole, senza premesse. Metti i riferimenti normativi (es. 'art. 2043 codice civile') SUBITO DOPO i primi termini, mai in fondo."
)


class LLMQueryExpander:
    def __init__(
        self,
        llm: LLMRouter,
        *,
        model: str | None = None,
        timeout_seconds: float = 6.0,
    ) -> None:
        self._llm = llm
        self._model = model
        self._timeout = timeout_seconds

    async def expand(self, question: str) -> str | None:
        """Termini di espansione, o None se l'espansione fallisce/va in timeout."""
        try:
            resp = await asyncio.wait_for(
                self._llm.chat(
                    [
                        LLMMessage(role="system", content=_SYSTEM),
                        LLMMessage(role="user", content=question),
                    ],
                    model=self._model,
                    max_tokens=160,
                    temperature=0.0,
                ),
                timeout=self._timeout,
            )
        except Exception as exc:  # timeout, provider down, quota: mai bloccare la ricerca
            logger.warning("query_expansion_failed", error=type(exc).__name__)
            return None
        text = (resp or "").strip().strip('"').strip()
        if not text or len(text) > 600:
            return None
        logger.info("query_expanded", original=question[:60], expansion=text[:100])
        return text
