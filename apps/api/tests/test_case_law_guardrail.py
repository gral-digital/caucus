"""Test del guardrail giurisprudenza e del contesto conversazionale nel retrieval.

Il caso reale che ha motivato entrambi (prod, 2026-08-10): follow-up «Per
forza di cose deve essere economicamente apprezzabile?» in una conversazione
sul profitto nel furto → retrieval fuori tema (diritto dei contratti) →
risposta «la Cassazione ha chiarito che…» inventata, contraria alle Sezioni
Unite n. 41570/2023 (assenti dal corpus), senza una citazione.
"""

from __future__ import annotations

from uuid import uuid4

from caucus_api.routes.chat import ChatMessage, ChatRequest
from caucus_api.services.chat_service import ChatService
from caucus_rag_core.schemas.citation import NormCitation
from caucus_rag_core.schemas.retrieval import RetrievalHit


def _norm_hit(source: str, num: str) -> RetrievalHit:
    return RetrievalHit(
        chunk_id=uuid4(),
        partition_id=uuid4(),
        citation=NormCitation(source=source, part="articolo", num=num),
        text="testo",
        score_final=1.0,
        metadata={"source": source, "articolo": num},
    )


def _case_law_hit(numero: str, anno: str) -> RetrievalHit:
    return RetrievalHit(
        chunk_id=uuid4(),
        partition_id=uuid4(),
        citation=None,
        text="testo sentenza",
        score_final=1.0,
        metadata={
            "source": "cass",
            "numero": numero,
            "anno": anno,
            "display": f"Cass. pen., Sez. 5, Sentenza n. {numero}/{anno}",
        },
    )


# ------------------------- guardrail giurisprudenza -------------------------


def test_claim_without_case_law_hits_is_flagged():
    text = (
        "Sì, secondo la giurisprudenza della Cassazione il profitto deve essere "
        "economicamente apprezzabile. La Cassazione ha chiarito che il profitto "
        "deve essere misurabile in termini monetari."
    )
    claims = ChatService._ungrounded_case_law_claims(text, [_norm_hit("cp", "624")])
    assert claims, "attribuzioni senza sentenze nel contesto devono essere flaggate"
    assert any("Cassazione ha chiarito" in c for c in claims)


def test_claim_grounded_on_context_extremes_is_ok():
    text = (
        "Secondo la giurisprudenza più recente il fine di profitto può avere "
        "natura non patrimoniale (Cass. pen., Sez. 5, n. 12345/2025)."
    )
    hits = [_case_law_hit("12345", "2025"), _norm_hit("cp", "624")]
    assert ChatService._ungrounded_case_law_claims(text, hits) == []


def test_claim_citing_extremes_not_in_context_is_flagged():
    # Cita estremi, ma non di sentenze fornite: resta infondata.
    text = "Le Sezioni Unite hanno stabilito il principio (n. 41570/2023)."
    hits = [_case_law_hit("12345", "2025")]
    assert ChatService._ungrounded_case_law_claims(text, hits)


def test_honest_gap_admission_is_not_flagged():
    text = (
        "Nel corpus indicizzato non trovo sentenze della Cassazione su questo "
        "punto: la giurisprudenza che ho copre solo le pronunce dal 2025. "
        "Sull'orientamento consolidato serve una verifica su banca dati completa."
    )
    assert ChatService._ungrounded_case_law_claims(text, []) == []


def test_norm_only_answer_is_not_flagged():
    text = (
        'Il furto è punito da <cite source="cp" part="articolo" num="624"/>: '
        "serve il dolo specifico di profitto."
    )
    assert ChatService._ungrounded_case_law_claims(text, [_norm_hit("cp", "624")]) == []


def test_extreme_pattern_matches_both_forms():
    pat = ChatService._CASE_LAW_EXTREME_PATTERN
    assert pat.search("n. 41570/2023").groups() == ("41570", "2023")
    assert pat.search("n. 41570 del 2023").groups() == ("41570", "2023")


# --------------------- contesto conversazionale retrieval ---------------------


def _request(question: str, history: list[ChatMessage] | None = None) -> ChatRequest:
    return ChatRequest(question=question, history=history or [])


def test_retrieval_query_plain_without_history():
    req = _request("Concezione del profitto nel delitto di furto")
    assert ChatService._build_retrieval_query(req) == req.question


def test_retrieval_query_includes_last_user_turn_for_long_followup():
    # Il caso di prod: follow-up sopra i 25 caratteri, che prima perdeva tutto.
    history = [
        ChatMessage(role="user", content="Concezione del profitto nel delitto di furto"),
        ChatMessage(role="assistant", content="Il profitto ex art. 624 cp..."),
    ]
    req = _request("Per forza di cose deve essere economicamente apprezzabile?", history)
    q = ChatService._build_retrieval_query(req)
    assert "furto" in q
    assert q.endswith("Per forza di cose deve essere economicamente apprezzabile?")


def test_retrieval_query_context_is_truncated():
    history = [ChatMessage(role="user", content="parola " * 200)]
    req = _request("E in appello?", history)
    q = ChatService._build_retrieval_query(req)
    context_part = q.split("\n\n")[0]
    assert len(context_part) <= 400


def test_retrieval_query_skips_duplicate_context():
    history = [ChatMessage(role="user", content="Quanto dura la prescrizione?")]
    req = _request("Quanto dura la prescrizione?", history)
    assert ChatService._build_retrieval_query(req) == "Quanto dura la prescrizione?"


def test_retrieval_query_reaggancia_sentenze_citate():
    # Osservato in prod 2026-08-24: il follow-up perdeva la SS.UU. discussa
    # al turno prima, perché i suoi estremi non entravano nella query e il
    # braccio Cassazione ripartiva da zero.
    history = [
        ChatMessage(role="user", content="Concezione del profitto nel delitto di furto"),
        ChatMessage(
            role="assistant",
            content="Le Sezioni Unite, con la sentenza n. 41570/2023, hanno risolto il contrasto.",
        ),
    ]
    req = _request("Per forza di cose deve essere economicamente apprezzabile?", history)
    q = ChatService._build_retrieval_query(req)
    assert "Cass. n. 41570/2023" in q
    assert q.endswith("Per forza di cose deve essere economicamente apprezzabile?")


def test_case_refs_ignora_estremi_normativi():
    history = [
        ChatMessage(
            role="assistant",
            content="Si applica la legge 7 agosto 1990, n. 241 e il d.lgs. n. 33 del 2013.",
        ),
    ]
    assert ChatService._case_refs_from_history(history) == ""


def test_intento_giurisprudenziale_riconosciuto():
    pat = ChatService._GIURISPRUDENZA_INTENT
    assert pat.search("Concezione del profitto nel delitto di furto cassazione")
    assert pat.search("contesto: Cass. n. 41570/2023\n\nquindi?")
    assert pat.search("qual è l'orientamento delle Sezioni Unite?")
    assert not pat.search("Quanto dura il preavviso di licenziamento?")
    assert not pat.search("Requisiti della comunicazione di avvio del procedimento")


def test_case_refs_dedup_e_ultimi_tre():
    history = [
        ChatMessage(
            role="assistant",
            content=(
                "V. Cass. n. 100/2020; la sentenza n. 200 del 2021; "
                "Cass. ord. n. 300/2022; le Sezioni Unite n. 400/2023; "
                "e ancora Cass. n. 100/2020."
            ),
        ),
    ]
    refs = ChatService._case_refs_from_history(history)
    assert refs == "Cass. n. 200/2021; Cass. n. 300/2022; Cass. n. 400/2023"


def test_generic_giurisprudenza_attribution_is_flagged():
    # Osservato in prod post-fix: «la giurisprudenza ha spesso interpretato…»
    # senza citazioni è comunque un'attribuzione da fondare o dichiarare.
    text = "La giurisprudenza ha spesso interpretato il profitto in senso ampio."
    assert ChatService._ungrounded_case_law_claims(text, [])


# ------------------- risposta di merito senza citazioni -------------------


def test_substantive_answer_without_citations_is_flagged():
    text = (
        "Sì, nel contesto del furto il profitto deve essere economicamente "
        "apprezzabile. Il concetto di profitto implica un vantaggio che può "
        "essere valutato in termini economici, anche se non necessariamente in "
        "denaro contante. Questo significa che il profitto può consistere in "
        "qualsiasi utilità o beneficio che abbia un valore economico, come "
        "l'uso di un bene o il risparmio di una spesa."
    )
    assert ChatService._is_substantive_without_citations(text, 0)


def test_answer_with_citations_is_not_flagged():
    assert not ChatService._is_substantive_without_citations("x" * 400, 2)


def test_short_or_interrogative_answers_are_not_flagged():
    assert not ChatService._is_substantive_without_citations("Ciao! Come posso aiutarti?", 0)
    long_question = ("Per inquadrare il caso mi servono alcuni dettagli. " * 8) + "Com'era?"
    assert not ChatService._is_substantive_without_citations(long_question, 0)


def test_honest_admission_is_not_sent_to_grounding_repair():
    text = (
        "Su questo punto specifico non trovo la norma nel corpus indicizzato: "
        "ti consiglio di verificare su una banca dati completa. " * 5
    )
    assert not ChatService._is_substantive_without_citations(text, 0)


# ----------------------- chunk col principio di diritto -----------------------


def _hit(chunk_id: int, text: str, case: str | None = None):
    from uuid import UUID

    from caucus_rag_core.schemas.retrieval import RetrievalHit

    return RetrievalHit(
        chunk_id=UUID(int=chunk_id),
        partition_id=UUID(int=0),
        text=text,
        score_final=0.5,
        metadata={"case_external_id": case} if case else {},
    )


def test_prefer_principle_chunk_sostituisce_il_rappresentante():
    from caucus_api.services.search_service import SearchService

    ricostruzione = _hit(1, "un orientamento riteneva il profitto patrimoniale", "snpen2023U41570S")
    principio = _hit(
        2, "deve essere enunciato il seguente Principio di diritto: ...", "snpen2023U41570S"
    )
    norma = _hit(3, "articolo 624")
    out = SearchService._prefer_principle_chunks(
        [ricostruzione, norma], [ricostruzione, principio, norma]
    )
    assert out[0].chunk_id == principio.chunk_id
    assert out[1].chunk_id == norma.chunk_id


def test_prefer_principle_chunk_senza_principio_non_tocca_nulla():
    from caucus_api.services.search_service import SearchService

    a = _hit(1, "testo qualunque", "snpen2024X1S")
    b = _hit(2, "articolo 624")
    assert SearchService._prefer_principle_chunks([a, b], [a, b]) == [a, b]
