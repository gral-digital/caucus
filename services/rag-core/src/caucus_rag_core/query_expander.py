"""Query expansion LLM: dalla domanda del cliente alla terminologia giuridica.

Il gap lessicale tra come parla un utente («mi hanno fermato ubriaco»,
«responsabilità extracontrattuale») e come è scritto il testo normativo
(«guida sotto l'influenza dell'alcool», «risarcimento per fatto illecito»)
è la prima causa di retrieval miss con embedding dense. Una riscrittura LLM
economica (1 chiamata, ~200 token) chiude gran parte del gap.

Output strutturato su due righe: la query arricchita (per embedding + FTS) e
una lista di articoli candidati in formato deterministico «sigla numero»,
validata contro il catalogo delle fonti indicizzate (SOURCE_CATALOG). I
candidati NON vengono pinnati: entrano nel merge come lookup a peso
intermedio, e se il modello ha sbagliato articolo il reranker li affossa.
Prima i riferimenti si estraevano con regex dalla sola riga arricchita: le
fonti senza forma canonica riconoscibile (cts, cnav, cpriv, wb, …) non
emergevano mai — è la causa principale dei retrieval miss su query
concettuali misurati in eval.

Robustezza: qualunque errore/timeout → si usa la query originale.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass

import structlog

from caucus_rag_core.act_registry import SOURCE_CATALOG
from caucus_rag_core.llm.router import LLMMessage, LLMRouter
from caucus_rag_core.query_router import ArticleRef

logger = structlog.get_logger(__name__)

_CATALOG_LINE = "; ".join(f"{sid}={title}" for sid, title in sorted(SOURCE_CATALOG.items()))

_SYSTEM = (
    "Sei un giurista italiano esperto di ricerca normativa. Dato il quesito "
    "dell'utente produci ESATTAMENTE due righe:\n"
    "QUERY: il quesito riscritto come query di ricerca su testi normativi "
    "italiani ed europei — aggiungi gli istituti giuridici tecnici e i sinonimi "
    "normativi, max 30 parole; se conosci l'articolo chiave mettine il "
    "riferimento (es. 'art. 2043 codice civile') subito dopo i primi termini. "
    "NON rispondere alla domanda.\n"
    "RIF: gli articoli che rispondono al quesito, da 1 a 6, formato "
    "'sigla numero' separati da '; ', usando SOLO le sigle del catalogo sotto "
    "(es. 'RIF: cc 2947; cpc 633'). La sigla deve essere quella della fonte "
    "giusta nel catalogo (il Testo Unico Bancario è 'tub', non 'cc'). Ogni "
    "articolo va elencato singolarmente: MAI intervalli come 'wb 1-21'. "
    "Includi sia la norma sostanziale sia quella processuale se pertinenti, e "
    "sia la regola generale sia quella speciale (es. prescrizione ordinaria E "
    "prescrizione breve). Se il quesito riguarda un istituto abrogato o "
    "depenalizzato, indica comunque l'articolo storico. Ometti la riga RIF "
    "solo se davvero non conosci nessun articolo pertinente (scrivi 'RIF: -').\n"
    f"CATALOGO SIGLE: {_CATALOG_LINE}"
)

# «cc 2947», «cp 62-bis», «cpc 473-bis.36», «cpriv 2-undecies»
_REF_TOKEN_RE = re.compile(r"^([a-z0-9]+)\s+(\d+(?:[-.\s][a-z0-9.]+)*)$")


@dataclass(frozen=True, slots=True)
class ExpandedQuery:
    """Risultato dell'espansione: testo arricchito + articoli candidati."""

    text: str
    refs: tuple[ArticleRef, ...] = ()


def _parse_refs(line: str) -> tuple[ArticleRef, ...]:
    """Parsa la riga RIF in ArticleRef validati contro il catalogo fonti."""
    refs: list[ArticleRef] = []
    for token in re.split(r"[;,]", line):
        m = _REF_TOKEN_RE.match(token.strip().lower())
        if not m or m.group(1) not in SOURCE_CATALOG:
            continue
        # Punteggiatura di coda («cpp 369-bis.»): senza strip il lookup esatto
        # per numero non risolve mai.
        num = re.sub(r"[\s]+", "-", m.group(2).strip()).rstrip(".-")
        # «wb 1-21» è un intervallo, non un articolo: i suffissi reali dopo il
        # trattino sono parole latine (bis, ter, …), mai un secondo numero.
        if re.fullmatch(r"\d+-\d+", num):
            continue
        ref = ArticleRef(source=m.group(1), num=num)
        if ref not in refs:
            refs.append(ref)
    return tuple(refs[:6])


def parse_expansion(raw: str) -> ExpandedQuery | None:
    """Parsa l'output a due righe del modello. Tollerante su prefissi mancanti."""
    text_line = ""
    refs: tuple[ArticleRef, ...] = ()
    for line in raw.strip().splitlines():
        line = line.strip().strip('"')
        if not line:
            continue
        upper = line.upper()
        if upper.startswith("RIF:"):
            refs = _parse_refs(line[4:])
        elif upper.startswith("QUERY:"):
            text_line = line[6:].strip()
        elif not text_line:
            # Modello senza prefisso: la prima riga utile è la query arricchita.
            text_line = line
    if not text_line or len(text_line) > 600:
        return None
    return ExpandedQuery(text=text_line, refs=refs)


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

    async def expand(self, question: str) -> ExpandedQuery | None:
        """Espansione strutturata, o None se fallisce/va in timeout."""
        try:
            resp = await asyncio.wait_for(
                self._llm.chat(
                    [
                        LLMMessage(role="system", content=_SYSTEM),
                        LLMMessage(role="user", content=question),
                    ],
                    model=self._model,
                    # Budget contenuto: la generazione dell'espansione è sul
                    # percorso critico del TTFT (~50 tok/s → ~3s a budget
                    # pieno) e output lunghi causavano timeout intermittenti,
                    # cioè retrieval senza espansione e recall a zero.
                    max_tokens=150,
                    temperature=0.0,
                ),
                timeout=self._timeout,
            )
        except Exception as exc:  # timeout, provider down, quota: mai bloccare la ricerca
            logger.warning("query_expansion_failed", error=type(exc).__name__)
            return None
        expanded = parse_expansion(resp or "")
        if expanded is None:
            return None
        logger.info(
            "query_expanded",
            original=question[:60],
            expansion=expanded.text[:100],
            refs=[(r.source, r.num) for r in expanded.refs],
        )
        return expanded
