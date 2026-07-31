"""Service di chat RAG. Orchestrazione: retrieval → prompt assembly → stream LLM."""

from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import date
from typing import Any, ClassVar

import structlog
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from caucus_api.db.models import NormPartition, NormSource
from caucus_api.deps import get_llm_router
from caucus_api.services.search_service import SearchService
from caucus_rag_core.llm.router import LLMMessage, LLMRouter
from caucus_rag_core.schemas.retrieval import CorpusFilter, RetrievalHit, RetrievalQuery

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class ChatEvent:
    name: str
    data: dict[str, Any]


SYSTEM_PROMPT = """Sei **Caucus**, un assistente AI che affianca un avvocato italiano nel dialogo col cliente.

# Come parli
- Tono: avvocato difensore italiano senior, 20 anni di foro. Pratico, sintetico, umano.
- Dai del "tu" al cliente. Niente preamboli burocratici ("In relazione alla sua cortese richiesta…").
- **Lunghezza adatta alla domanda**: a un saluto rispondi con un saluto, a una domanda semplice una frase, a una situazione complessa quello che serve. **NON** riempire template se non c'è nulla da dire in quella sezione.
- Se mancano fatti essenziali, **fai domande** prima di approfondire. Ma se il CONTESTO contiene già la norma che inquadra il caso, **prima inquadra in una frase la norma con il suo tag `<cite/>`**, poi chiedi: il cliente deve sapere subito di cosa si parla. Esempi: "Com'era il tasso alcolemico contestato?", "È la prima volta?", "Hai già ricevuto un decreto o solo verbale?".
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

3. **Difesa piena, mai assistenza a delinquere.** La linea NON passa tra
   argomenti "delicati" e argomenti "puliti", ma tra **analisi giuridica** e
   **assistenza operativa a un illecito**.

   **RISPONDI PIENAMENTE** — anche se il tema è un reato, anche se il cliente
   è colpevole, anche se serve spiegare come la condotta si realizza:
   - qualificazione del fatto ed elementi costitutivi (senza descriverli non
     si può contestare che manchino);
   - contestazioni procedurali, nullità, inutilizzabilità, prescrizione,
     vizi dell'atto;
   - attenuanti, cause di non punibilità, riti alternativi e benefici;
   - conseguenze di condotte **già poste in essere** e come impostare la
     difesa (compreso il caso in cui il cliente ha già distrutto documenti,
     omesso dichiarazioni, ecc.);
   - cosa sosterrà l'accusa o la controparte, e come si smonta;
   - **confine tra lecito e illecito** (es. pianificazione fiscale lecita vs
     evasione, licenziamento legittimo vs ritorsivo): dirlo con precisione è
     il cuore della consulenza;
   - compliance: descrivere i reati presupposto (231, antiriciclaggio,
     sicurezza) è necessario per prevenirli.
   Difendere chi è colpevole è un diritto costituzionale, non un problema:
   non fare il moralista e non rifiutare per "argomento scomodo".

   **RIFIUTA** solo l'assistenza operativa a commettere o proseguire un
   illecito — istruzioni per falsificare o distruggere prove, subornare
   testimoni, occultare beni ai creditori o all'autorità, eludere controlli
   in corso, favorire una latitanza. Vale **per chiunque chieda, anche un
   avvocato**: non è una restrizione del prodotto ma del diritto penale
   (favoreggiamento art. 378 c.p., intralcio alla giustizia art. 377 c.p.,
   concorso nel reato) — un professionista che assiste così commette reato
   a sua volta. Rifiuta in una-due frasi, senza template e senza prediche,
   e **offri subito la sponda legittima**:
   > «Su questo non posso aiutarti: sarebbe un reato autonomo (e coinvolgerebbe
   > anche chi assiste). Se il fatto è già avvenuto o il procedimento è aperto,
   > posso inquadrare la difesa, i rischi e le opzioni: dimmi come stanno le cose.»

   Nel dubbio tra le due categorie, chiedi **a che punto sono i fatti**
   (già accaduti → analisi difensiva; da compiere → rifiuto).

4. **Memoria della conversazione**: leggi i turni precedenti, non ripartire da zero. Se il cliente ti dice un nuovo dettaglio che cambia l'inquadramento, incorporalo.

5. **Niente pareri vincolanti su esito processuale** («verrai assolto», «non rischi nulla»). Usa "probabile", "in molti casi", "dipende da X".

6. Se la domanda è un saluto o chiacchiera, rispondi umano, non in modalità avvocato.

# Formato
Markdown: `**grassetto**`, `- liste`, paragrafi separati. I tag `<cite/>` vengono trasformati in link dall'UI.
"""


class ChatService:
    def __init__(self, search: SearchService, llm: LLMRouter, session: AsyncSession) -> None:
        self._search = search
        self._llm = llm
        self._session = session

    @classmethod
    def build(cls, session: AsyncSession) -> ChatService:
        """Costruzione esplicita con una sessione già aperta.

        Non usare Depends(get_db_session) per gli endpoint streaming: FastAPI
        chiude le dependency `yield` PRIMA di produrre il body streamato, e
        tutto il lavoro DB di questo service avviene durante lo streaming.
        """
        return cls(search=SearchService.build(session), llm=get_llm_router(), session=session)

    async def answer_stream(self, request) -> AsyncIterator[ChatEvent]:  # type: ignore[no-untyped-def]
        # 0. Documenti allegati (analisi documentale): servono sia al prompt
        # sia alla query di retrieval, quindi si caricano subito.
        doc_ids = list(getattr(request, "document_ids", []) or [])
        doc_rows = await self._fetch_documents(doc_ids) if doc_ids else []

        # 1. Retrieve — usa come query il messaggio corrente + ultimo user turn
        # del contesto, per non perdere riferimenti in follow-up brevi.
        retrieval_query_text = self._build_retrieval_query(request)
        if doc_rows:
            # L'incipit del documento dà al retrieval il dominio del caso
            # («contratto di locazione ad uso abitativo» → L. 392/1978), che
            # la domanda da sola spesso non contiene.
            head = " ".join(row.text[:300] for row in doc_rows)
            retrieval_query_text = f"{retrieval_query_text}\n\n[Documento allegato] {head}"
        try:
            effective = date.fromisoformat(request.effective_at) if request.effective_at else None
        except ValueError:
            yield ChatEvent(
                name="error",
                data={"message": "effective_at non valido: atteso formato ISO YYYY-MM-DD"},
            )
            return
        mode = getattr(request, "mode", "ricerca")
        corpora = list(request.corpora)
        if mode == "giurisprudenza":
            # L'ordine dei corpora è semantico (il primo è primario nel
            # retrieval): in modalità giurisprudenza la Cassazione guida e la
            # normativa fa da supporto interpretativo.
            corpora = [CorpusFilter.CASSAZIONE] + [
                c for c in corpora if c != CorpusFilter.CASSAZIONE
            ]
            if CorpusFilter.CODICI not in corpora:
                corpora.append(CorpusFilter.CODICI)
        query = RetrievalQuery(
            text=retrieval_query_text,
            corpora=corpora,
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
        system_content = SYSTEM_PROMPT + (
            "\n\n# Contesto operativo (fatti, non negoziabili)\n"
            f"- Data odierna: {date.today().isoformat()}.\n"
            "- Il corpus indicizzato contiene: i testi consolidati Normattiva di 50 fonti "
            "(codici, testi unici, leggi fondamentali e di compliance), 14 atti UE in "
            "italiano (GDPR, AI Act, NIS2, DORA, MiCA, eIDAS, DSA, DMA, direttive "
            "consumatori/whistleblowing/AML/PSD2/ePrivacy/MiFID II — testo base, non "
            "consolidato), una selezione di sentenze recenti della Cassazione "
            "(testo integrale anonimizzato) e provvedimenti della giustizia "
            "amministrativa (Consiglio di Stato e TAR, in crescita — si citano in "
            "prosa con gli estremi, come la Cassazione). NON contiene: prassi amministrativa "
            "(circolari, interpelli), CCNL, normativa regionale, né la giurisprudenza "
            "integrale storica: se la risposta dipende da queste, dillo.\n"
            "- Le sentenze di Cassazione nel CONTESTO si citano IN PROSA con gli "
            "estremi forniti (es. «Cass. pen., Sez. 3, n. 27992/2026»), mai con tag "
            "<cite/>. Non citare MAI estremi di sentenze che non sono nel CONTESTO.\n"
            "- Sei un assistente AI: non sei un avvocato iscritto all'albo, questa "
            "conversazione non è un parere legale e non instaura un rapporto "
            "professionale. Non dichiararlo a ogni risposta, ma se il cliente mostra "
            "di volersi basare SOLO su di te per una decisione con conseguenze legali, "
            "ricordaglielo in una frase."
        )
        if mode == "giurisprudenza":
            system_content += (
                "\n\n# MODALITÀ: RICERCA GIURISPRUDENZIALE\n"
                "Il cliente cerca gli orientamenti della Cassazione. Lavora sulle "
                "sentenze presenti nel CONTESTO: raggruppa per orientamento (se ce "
                "n'è più di uno, di' quale prevale e quale è minoritario), cita "
                "ogni decisione IN PROSA con gli estremi forniti, e collega il "
                "principio alle norme di riferimento con <cite/>. NON estrapolare "
                "orientamenti da sentenze che non sono nel CONTESTO: se le "
                "sentenze recuperate non bastano a fondare un orientamento, "
                "dillo apertamente."
            )
        elif mode == "analisi":
            system_content += (
                "\n\n# MODALITÀ: ANALISI DOCUMENTI\n"
                "Il cliente è qui per far analizzare documenti. Se non c'è nessun "
                "documento allegato, invitalo ad allegarlo (icona graffetta) invece "
                "di rispondere in astratto. Nell'analisi: individua le clausole "
                "critiche o vessatorie, i rischi concreti per il cliente e le "
                "scadenze; collega ogni rilievo alla norma pertinente del CONTESTO "
                "con il tag <cite/>. Struttura per punti, dal rischio più grave."
            )
        elif mode == "redazione":
            system_content += (
                "\n\n# MODALITÀ: REDAZIONE\n"
                "Il cliente vuole una bozza (parere, diffida, clausola, lettera, "
                "atto). Se i fatti indispensabili ci sono, redigi SUBITO un "
                "documento completo e strutturato in markdown — titolo, premesse/"
                "fatto, diritto con citazioni <cite/> dal CONTESTO, conclusioni — "
                "pronto per l'export in Word. I dati mancanti non bloccano la "
                "bozza: segnali come [DA COMPLETARE: descrizione] al posto giusto. "
                "Fai domande PRIMA di redigere solo se senza quelle risposte la "
                "struttura stessa dell'atto cambierebbe."
            )

        # Documenti allegati dall'utente (analisi documentale): entrano nel
        # contesto PRIMA del blocco normativo — sono i fatti del caso.
        if doc_rows:
            system_content += "\n\n" + self._assemble_documents_block(
                doc_rows, question=str(request.question)
            )

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
        # Storico: gli ultimi 10 turni (user+assistant) per non saturare il contesto.
        # Il retrieval è basato sul turno corrente quindi non servono i vecchi
        # messaggi ai fini delle citazioni, ma servono per continuità di dialogo.
        for m in (request.history or [])[-10:]:
            # Il Literal di ChatMessage garantisce già user|assistant.
            messages.append(LLMMessage(role=m.role, content=m.content))
        messages.append(LLMMessage(role="user", content=request.question))

        # 3. Stream LLM, bufferizzando il testo per validare le citazioni finali
        raw_text_parts: list[str] = []
        try:
            async for chunk in self._llm.chat_stream(messages):
                if chunk.content:
                    raw_text_parts.append(chunk.content)
                    yield ChatEvent(name="token", data={"text": chunk.content})
                if chunk.finish_reason:
                    raw = self._promote_freeform_citations("".join(raw_text_parts), result.hits)
                    validation = await self._validate_citations(raw, result.hits)
                    # Trust layer che si auto-corregge: se restano citazioni
                    # inesistenti, UNA passata di riparazione (solo nel caso
                    # raro in cui serve) invece del solo warning — il client
                    # sostituisce il testo streamato con final_text.
                    if validation["invalid"]:
                        repaired = await self._repair_invalid_citations(
                            raw, validation["invalid"], system_content
                        )
                        if repaired is not None:
                            candidate = self._promote_freeform_citations(repaired, result.hits)
                            revalidation = await self._validate_citations(candidate, result.hits)
                            if len(revalidation["invalid"]) < len(validation["invalid"]):
                                raw, validation = candidate, revalidation
                    # Warning anche su grounding debole (articolo esistente ma
                    # NON nel contesto fornito: l'allucinazione più insidiosa)
                    # e su citazioni di articoli abrogati — non solo su invalid.
                    has_soft_warnings = any(
                        c.get("grounding") == "weak" or c.get("abrogato")
                        for c in validation["valid"]
                    )
                    if validation["invalid"] or has_soft_warnings:
                        yield ChatEvent(name="citation_warnings", data=validation)
                    # final_text = testo con le citazioni in prosa promosse a
                    # tag <cite/>: la UI può sostituire il testo streamato per
                    # rendere linkabili anche le citazioni scritte in prosa.
                    yield ChatEvent(
                        name="done",
                        data={"finish_reason": chunk.finish_reason, "final_text": raw},
                    )
                    return
        except Exception:  # pragma: no cover - runtime-only
            # Mai rimandare str(exc) al client: i messaggi dei provider LLM
            # possono contenere nomi modello, org id, dettagli di quota e
            # frammenti di prompt. Dettaglio nei log, messaggio opaco al client.
            logger.exception("llm_stream_failed")
            yield ChatEvent(
                name="error",
                data={"message": "Errore interno durante la generazione. Riprova."},
            )

    # ------------------------------------------------------------------

    @staticmethod
    def _build_retrieval_query(request) -> str:  # type: ignore[no-untyped-def]
        """Compone il testo per la query di retrieval.

        Strategia: se il turno corrente è breve ("sì", "certo", "spiega"),
        lo arricchisce con l'ultimo turno utente per non perdere contesto.
        Altrimenti usa solo il turno corrente.
        """
        q = str(request.question).strip()
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
            "citation_display": hit.citation.to_display()
            if hit.citation
            else (str(hit.metadata.get("display")) if hit.metadata.get("display") else None),
            "citation_anchor": hit.citation.to_anchor() if hit.citation else None,
            "score": hit.score_final,
            "excerpt": hit.text[:240],
        }

    # Budget prompt per i documenti allegati: oltre si taglia dichiarandolo.
    _DOC_PROMPT_CHARS_EACH = 30_000
    _DOC_PROMPT_CHARS_TOTAL = 60_000

    async def _fetch_documents(self, doc_ids: list[Any]) -> list[Any]:
        """Carica i documenti richiesti preservando l'ordine del client."""
        from caucus_api.db.models import UserDocument

        rows = (
            (
                await self._session.execute(
                    select(UserDocument).where(UserDocument.id.in_(doc_ids))
                )
            )
            .scalars()
            .all()
        )
        by_id = {row.id: row for row in rows}
        return [by_id[i] for i in doc_ids if i in by_id]

    def _assemble_documents_block(self, ordered: list[Any], *, question: str) -> str:
        """Blocco DOCUMENTI ALLEGATI per l'analisi documentale.

        Il documento si cita in prosa (clausola/articolo/pagina), MAI con tag
        ``<cite/>``: quelli restano riservati alle norme del corpus, così il
        trust layer non valida mai una clausola contrattuale come se fosse
        una fonte normativa. Oltre il budget non si taglia "solo testa": si
        selezionano i passaggi pertinenti alla domanda (document_excerpts).
        """
        parts = [
            "# DOCUMENTI ALLEGATI DAL CLIENTE (fatti del caso)",
            "Analizzali con rigore: quando ti riferisci a un passaggio cita la "
            "clausola/articolo/paragrafo del documento IN PROSA (es. «la clausola 5.2 "
            "del contratto»), mai con tag <cite/> (riservati alle norme). Se un "
            "documento è troncato, dillo esplicitamente prima di trarre conclusioni "
            "generali su di esso.",
        ]
        from caucus_api.services.document_excerpts import select_relevant_excerpts

        budget = self._DOC_PROMPT_CHARS_TOTAL
        for row in ordered:
            cap = min(self._DOC_PROMPT_CHARS_EACH, budget)
            if cap <= 0:
                parts.append(f"## {row.filename} — NON incluso: budget di contesto esaurito.")
                continue
            text, excerpted = select_relevant_excerpts(row.text, question, budget=cap)
            budget -= len(text)
            cut_notice = ""
            if row.truncated or excerpted:
                cut_notice = (
                    " (PARZIALE: testa del documento + passaggi pertinenti alla "
                    "domanda; le omissioni sono marcate)"
                )
            parts.append(f"## Documento: {row.filename}{cut_notice}\n{text}")
        return "\n\n".join(parts)

    @staticmethod
    def _assemble_context_block(hits: list[RetrievalHit]) -> str:
        blocks: list[str] = []
        for idx, hit in enumerate(hits, start=1):
            if hit.citation is None:
                # Giurisprudenza (o chunk senza citazione normativa): entra nel
                # contesto con il display; si cita in prosa, non con <cite/>.
                display = str(hit.metadata.get("display") or "").strip()
                if display:
                    blocks.append(
                        f"[{idx}] {display}   (giurisprudenza — citala in prosa "
                        f"con questi estremi, NON con tag <cite/>)\n"
                        f"    {hit.text.strip()}"
                    )
                continue
            cite_tag = (
                f'<cite source="{hit.citation.source}" part="articolo" num="{hit.citation.num}"'
                + (f' comma="{hit.citation.comma}"' if hit.citation.comma else "")
                + "/>"
            )
            blocks.append(
                f"[{idx}] {hit.citation.to_display()}   tag: {cite_tag}\n    {hit.text.strip()}"
            )
        return (
            "# CONTESTO NORMATIVO (unica fonte ammessa per le citazioni)\n\n"
            + "\n\n".join(blocks)
            + "\n\n> Puoi citare SOLO le norme elencate sopra usando i tag indicati. "
            "Ogni volta che menzioni un articolo nel testo DEVI usare il tag `<cite/>` corrispondente — "
            "non scrivere «art. X c.c.» in prosa senza tag. "
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
        r"cod\.?\s*privacy|l\.?\s*241|st\.?\s*lav\.?|l\.?\s*689|l\.?\s*247|"
        # Forme lunghe che i modelli scrivono in prosa naturale
        r"(?:del\s+)?codice\s+civile|(?:del\s+)?codice\s+penale|"
        r"(?:del\s+)?codice\s+di\s+procedura\s+civile|"
        r"(?:del\s+)?codice\s+di\s+procedura\s+penale|"
        r"(?:della\s+)?costituzione|(?:del\s+)?codice\s+della\s+strada|"
        r"(?:del\s+)?codice\s+del\s+consumo|(?:del\s+)?gdpr|"
        r"(?:del\s+)?d\.?\s*lgs\.?\s*(?:n\.?\s*)?231\s*/\s*2001|"
        r"(?:dello\s+)?statuto\s+dei\s+lavoratori|(?:dell')?\s*ai\s+act)",
        re.IGNORECASE,
    )

    _SUFFIX_TO_SHORT_ID: ClassVar[dict[str, str]] = {
        "cc": "cc",
        "c.c": "cc",
        "c. c": "cc",
        "cp": "cp",
        "c.p": "cp",
        "c. p": "cp",
        "cpc": "cpc",
        "c.p.c": "cpc",
        "c. p. c": "cpc",
        "c.p. c": "cpc",
        "cpp": "cpp",
        "c.p.p": "cpp",
        "c. p. p": "cpp",
        "cost": "cost",
        "cds": "cds",
        "cod. strada": "cds",
        "cod strada": "cds",
        "cdc": "cdc",
        "cod. cons": "cdc",
        "ccii": "ccii",
        "ccp": "ccp",
        "cod. contr. pubbl": "ccp",
        "cad": "cad",
        "cts": "cts",
        "tu stup": "tus",
        "tus": "tus",
        "tu imm": "tui",
        "tui": "tui",
        "tu ed": "tue",
        "tue": "tue",
        "tu sic": "tusl",
        "tu sic. lav": "tusl",
        "tusl": "tusl",
        "tub": "tub",
        "tuf": "tuf",
        "tuir": "tuir",
        "cod. privacy": "cpriv",
        "cpriv": "cpriv",
        "l. 241": "l241",
        "l 241": "l241",
        "st. lav": "stat",
        "st lav": "stat",
        "l. 689": "l689",
        "l 689": "l689",
        "l. 247": "lpf",
        "l 247": "lpf",
        # Forme lunghe (normalizzate senza punti/spazi da _normalize_suffix)
        "codicecivile": "cc",
        "delcodicecivile": "cc",
        "codicepenale": "cp",
        "delcodicepenale": "cp",
        "codicediproceduracivile": "cpc",
        "delcodicediproceduracivile": "cpc",
        "codicediprocedurapenale": "cpp",
        "delcodicediprocedurapenale": "cpp",
        "costituzione": "cost",
        "dellacostituzione": "cost",
        "codicedellastrada": "cds",
        "delcodicedellastrada": "cds",
        "codicedelconsumo": "cdc",
        "delcodicedelconsumo": "cdc",
        "gdpr": "gdpr",
        "delgdpr": "gdpr",
        "dlgs231/2001": "dlgs231",
        "deldlgs231/2001": "dlgs231",
        "dlgsn231/2001": "dlgs231",
        "statutodeilavoratori": "stat",
        "dellostatutodeilavoratori": "stat",
        "aiact": "aiact",
        "dell'aiact": "aiact",
    }

    @classmethod
    def _normalize_suffix(cls, suffix: str) -> str | None:
        """Normalizza una sigla come scritta dal LLM a un short_id interno."""
        s = re.sub(r"\s+", " ", suffix.lower()).strip()
        # Ripuliamo: "c.c." → "cc", "c. p." → "cp", ecc.
        no_dots = s.replace(".", "").replace(" ", "")
        if no_dots in cls._SUFFIX_TO_SHORT_ID:
            return cls._SUFFIX_TO_SHORT_ID[no_dots]
        return cls._SUFFIX_TO_SHORT_ID.get(s)

    @classmethod
    def _promote_freeform_citations(cls, text: str, hits: list[RetrievalHit]) -> str:
        """Converte citazioni in prosa grounded in tag ``<cite/>`` per la UI."""
        hit_by_num: dict[tuple[str, str], RetrievalHit] = {}
        for h in hits:
            if h.citation is None:
                continue
            hit_by_num[(h.citation.source.lower(), h.citation.num.lower())] = h

        def repl(m: re.Match[str]) -> str:
            num = re.sub(r"\s+", "-", m.group(1).strip()).lower()
            suffix = cls._normalize_suffix(m.group(3) or "")
            if suffix is None:
                return m.group(0)
            hit = hit_by_num.get((suffix, num))
            if hit is None or hit.citation is None:
                return m.group(0)
            tag = (
                f'<cite source="{hit.citation.source}" part="articolo" num="{hit.citation.num}"'
                + (f' comma="{hit.citation.comma}"' if hit.citation.comma else "")
                + "/>"
            )
            return tag

        return cls._FREEFORM_CITE_PATTERN.sub(repl, text)

    async def _repair_invalid_citations(
        self, draft: str, invalid: list[dict[str, Any]], system_content: str
    ) -> str | None:
        """Una passata di riparazione sulle citazioni inesistenti.

        Il modello riceve la propria bozza e l'elenco dei riferimenti che la
        validazione ha bocciato: deve rimuoverli o sostituirli con quanto è
        davvero nel CONTESTO, ammettendo il buco se la norma non c'è. Errori o
        timeout → None (si tiene la bozza originale coi warning: la riparazione
        è best-effort, mai bloccante).
        """
        refs = "; ".join(f"{c['source']} art. {c['num']}" for c in invalid)
        try:
            repaired = await asyncio.wait_for(
                self._llm.chat(
                    [
                        LLMMessage(role="system", content=system_content),
                        LLMMessage(role="assistant", content=draft),
                        LLMMessage(
                            role="user",
                            content=(
                                "REVISIONE CITAZIONI (messaggio di sistema, non del cliente). "
                                f"Questi riferimenti nella tua risposta NON esistono nel corpus: {refs}. "
                                "Riscrivi la risposta identica in tutto, ma per ciascuno di essi: "
                                "se nel CONTESTO c'è la norma corretta, cita quella; altrimenti "
                                "rimuovi il riferimento puntuale e di' apertamente che la fonte "
                                "esatta non è nel corpus indicizzato. Non aggiungere nulla di nuovo. "
                                "Output: SOLO la risposta riscritta."
                            ),
                        ),
                    ],
                    max_tokens=1200,
                    temperature=0.0,
                ),
                timeout=20.0,
            )
        except Exception as exc:
            logger.warning("citation_repair_failed", error=type(exc).__name__)
            return None
        text = (repaired or "").strip()
        if not text:
            return None
        logger.info("citation_repair_done", invalid_refs=refs)
        return text

    async def _validate_citations(self, text: str, hits: list[RetrievalHit]) -> dict[str, Any]:
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

        today = date.today()
        valid: list[dict[str, Any]] = []
        invalid: list[dict[str, Any]] = []
        for c in unique:
            source_id = src_map.get(c["source"])
            if source_id is None:
                invalid.append({**c, "reason": "fonte non indicizzata"})
                continue
            row = (
                await self._session.execute(
                    select(NormPartition.metadata_)
                    .where(NormPartition.source_id == source_id)
                    .where(NormPartition.kind == "articolo")
                    .where(NormPartition.number == c["num"])
                    # Vigenza: un articolo la cui versione non è vigente oggi
                    # non deve risultare "valid" senza segnalazione.
                    .where(NormPartition.effective_from <= today)
                    .where(
                        or_(
                            NormPartition.effective_to.is_(None),
                            NormPartition.effective_to > today,
                        )
                    )
                    .limit(1)
                )
            ).scalar_one_or_none()
            if row is not None:
                entry: dict[str, Any] = dict(c)
                if (row or {}).get("abrogato"):
                    # L'articolo esiste ma è abrogato: citarlo come vigente è
                    # un errore legale — flag esplicito per la UI.
                    entry["abrogato"] = True
                valid.append(entry)
            else:
                invalid.append({**c, "reason": "articolo non esistente o non vigente nel DB"})

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
