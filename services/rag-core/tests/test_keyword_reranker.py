"""Test keyword reranker disambigua omicidio volontario vs colposo."""

from __future__ import annotations

import asyncio
from uuid import uuid4

from avvocato_rag_core.reranker import KeywordBoostReranker
from avvocato_rag_core.schemas.citation import NormCitation
from avvocato_rag_core.schemas.retrieval import RetrievalHit


def _hit(num: str, text: str, lookup: str = "vector") -> RetrievalHit:
    return RetrievalHit(
        chunk_id=uuid4(),
        partition_id=uuid4(),
        citation=NormCitation(source="cp", part="articolo", num=num),
        text=text,
        score_final=0.5,
        metadata={"lookup": lookup, "articolo": num},
    )


def test_penalizes_colposo_when_query_volontario():
    reranker = KeywordBoostReranker()
    hits = [
        _hit("589", "[Rubrica] Omicidio colposo\n\nChiunque cagiona per colpa la morte"),
        _hit("575", "[Rubrica] Omicidio\n\nChiunque cagiona la morte di un uomo"),
    ]
    out = asyncio.run(
        reranker.rerank("Come è definito il reato di omicidio volontario?", hits, top_k=2)
    )
    assert out[0].citation is not None
    assert out[0].citation.num == "575"


def test_rubrica_boost_active():
    """Regressione: il boost rubrica cercava '(Rubrica)' ma il chunker scrive '[Rubrica]'."""
    from avvocato_rag_core.reranker import _extract_rubrica

    assert _extract_rubrica("[Rubrica] Omicidio\n\nChiunque cagiona...") == "Omicidio"


def test_abrogato_penalized():
    import asyncio
    from uuid import uuid4

    from avvocato_rag_core.reranker import KeywordBoostReranker
    from avvocato_rag_core.schemas.retrieval import RetrievalHit

    vig = RetrievalHit(
        chunk_id=uuid4(),
        partition_id=uuid4(),
        text="Chiunque cagiona la morte di un uomo",
        score_final=0.5,
        metadata={},
    )
    abr = RetrievalHit(
        chunk_id=uuid4(),
        partition_id=uuid4(),
        text="Chiunque cagiona la morte di un uomo",
        score_final=0.5,
        metadata={"abrogato": True},
    )
    out = asyncio.run(KeywordBoostReranker().rerank("cagiona la morte", [abr, vig], top_k=2))
    assert out[0].metadata.get("abrogato") is None
