"""Test della fusione RRF: priorità dei metadata e pinning."""

from __future__ import annotations

from uuid import uuid4

from avvocato_rag_core.hit_merge import ensure_direct_articles_first, reciprocal_rank_fusion
from avvocato_rag_core.schemas.citation import NormCitation
from avvocato_rag_core.schemas.retrieval import RetrievalHit


def _hit(
    chunk_id, *, lookup: str | None = None, source: str = "cp", num: str = "575"
) -> RetrievalHit:
    meta: dict[str, object] = {"source": source, "articolo": num}
    if lookup:
        meta["lookup"] = lookup
    return RetrievalHit(
        chunk_id=chunk_id,
        partition_id=uuid4(),
        citation=NormCitation(source=source, part="articolo", num=num),
        text="testo",
        score_final=1.0,
        metadata=meta,
    )


def test_rrf_preserves_direct_lookup_metadata():
    """Se lo stesso chunk arriva da direct E vettoriale, il metadata 'direct'
    deve sopravvivere (regressione: l'ultima lista sovrascriveva)."""
    cid = uuid4()
    direct = [_hit(cid, lookup="direct")]
    vector = [_hit(cid, lookup=None)]

    merged = reciprocal_rank_fusion([direct, vector], top_k=5)
    assert len(merged) == 1
    assert merged[0].metadata.get("lookup") == "direct"


def test_rrf_sums_scores_across_lists():
    cid_shared = uuid4()
    cid_solo = uuid4()
    list_a = [_hit(cid_shared, lookup="fts"), _hit(cid_solo)]
    list_b = [_hit(cid_shared)]

    merged = reciprocal_rank_fusion([list_a, list_b], top_k=5)
    # Il chunk presente in due liste deve avere score più alto e stare primo
    assert merged[0].chunk_id == cid_shared
    assert merged[0].score_final > merged[1].score_final


def test_rrf_pin_first_keeps_pinned_on_top():
    pinned_id = uuid4()
    other = uuid4()
    direct = [_hit(pinned_id, lookup="direct")]
    vector = [_hit(other), _hit(pinned_id)]

    merged = reciprocal_rank_fusion([direct, vector], top_k=5, pin_first=[pinned_id])
    assert merged[0].chunk_id == pinned_id


def test_ensure_direct_articles_first_reorders():
    a = _hit(uuid4(), source="cp", num="589")
    b = _hit(uuid4(), lookup="direct", source="cp", num="575")
    out = ensure_direct_articles_first([a, b], direct=[("cp", "575")], top_k=5)
    assert out[0].citation is not None and out[0].citation.num == "575"


def test_rrf_weights_favor_direct_list():
    """Con weights, un hit in cima alla lista pesata batte un hit in cima a una lista non pesata."""
    direct_id = uuid4()
    vector_id = uuid4()
    direct = [_hit(direct_id, lookup="direct", num="575")]
    vector = [_hit(vector_id, num="589"), _hit(direct_id, lookup=None, num="575")]

    merged = reciprocal_rank_fusion([direct, vector], top_k=5, weights=[3.0, 1.0])
    assert merged[0].chunk_id == direct_id


def test_rrf_weights_length_mismatch_raises():
    import pytest

    with pytest.raises(ValueError):
        reciprocal_rank_fusion([[_hit(uuid4())]], top_k=5, weights=[1.0, 2.0])
