"""Test del layer anti-allucinazione: regex citazioni, normalizzazione sigle,
promozione delle citazioni in prosa a tag <cite/>."""

from __future__ import annotations

from uuid import uuid4

from avvocato_api.routes.chat import ChatMessage, ChatRequest
from avvocato_api.services.chat_service import ChatService
from avvocato_rag_core.schemas.citation import NormCitation
from avvocato_rag_core.schemas.retrieval import RetrievalHit


def _hit(source: str, num: str) -> RetrievalHit:
    return RetrievalHit(
        chunk_id=uuid4(),
        partition_id=uuid4(),
        citation=NormCitation(source=source, part="articolo", num=num),
        text="testo",
        score_final=1.0,
        metadata={"source": source, "articolo": num},
    )


def test_cite_tag_pattern_extracts_source_and_num():
    text = 'Vedi <cite source="cp" part="articolo" num="575"/> e <cite source="cc" part="articolo" num="2043" comma="1"/>.'
    found = ChatService._CITE_PATTERN.findall(text)
    assert ("cp", "575") in found
    assert ("cc", "2043") in found


def test_normalize_suffix_common_forms():
    assert ChatService._normalize_suffix("c.c.") == "cc"
    assert ChatService._normalize_suffix("c.p.") == "cp"
    assert ChatService._normalize_suffix("c. p. p.") == "cpp"
    assert ChatService._normalize_suffix("cod. strada") == "cds"
    assert ChatService._normalize_suffix("sigla-inventata") is None


def test_freeform_citation_detected():
    m = ChatService._FREEFORM_CITE_PATTERN.search("si applica l'art. 2043 c.c. in questi casi")
    assert m is not None
    assert m.group(1) == "2043"


def test_promote_freeform_only_when_grounded():
    hits = [_hit("cc", "2043")]
    text = "Risponde ex art. 2043 c.c.; invece l'art. 9999 c.c. non esiste nel contesto."
    out = ChatService._promote_freeform_citations(text, hits)
    assert '<cite source="cc" part="articolo" num="2043"/>' in out
    # La citazione non presente tra gli hit resta in prosa (verrà flaggata dal validator)
    assert "art. 9999 c.c." in out


def test_chat_request_caps_history():
    import pytest
    from pydantic import ValidationError

    msgs = [ChatMessage(role="user", content="ciao")] * 41
    with pytest.raises(ValidationError):
        ChatRequest(question="test", history=msgs)

    with pytest.raises(ValidationError):
        ChatMessage(role="user", content="x" * 8001)
