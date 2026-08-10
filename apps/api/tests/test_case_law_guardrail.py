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


def test_generic_giurisprudenza_attribution_is_flagged():
    # Osservato in prod post-fix: «la giurisprudenza ha spesso interpretato…»
    # senza citazioni è comunque un'attribuzione da fondare o dichiarare.
    text = "La giurisprudenza ha spesso interpretato il profitto in senso ampio."
    assert ChatService._ungrounded_case_law_claims(text, [])
