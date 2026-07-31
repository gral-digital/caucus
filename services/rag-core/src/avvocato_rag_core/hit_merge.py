"""Fusione risultati multi-retriever con Reciprocal Rank Fusion (RRF)."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from avvocato_rag_core.schemas.retrieval import RetrievalHit

# Priorità del ramo di provenienza quando lo stesso chunk arriva da più liste:
# il metadata del ramo più autorevole (lookup diretto > FTS > vettoriale) deve
# sopravvivere alla fusione, altrimenti il boost del reranker sul lookup
# diretto non scatta proprio sui chunk confermati da più rami.
_LOOKUP_PRIORITY = {"direct": 2, "fts": 1}


def _lookup_priority(hit: RetrievalHit) -> int:
    return _LOOKUP_PRIORITY.get(str(hit.metadata.get("lookup", "")), 0)


def reciprocal_rank_fusion(
    ranked_lists: Sequence[Sequence[RetrievalHit]],
    *,
    k: int = 60,
    top_k: int,
    pin_first: Sequence[UUID] | None = None,
    weights: Sequence[float] | None = None,
) -> list[RetrievalHit]:
    """Fonde liste già ordinate per rank.

    ``weights`` (uno per lista, default 1.0) permette di pesare i rami: in
    dominio legale il lookup deterministico per numero di articolo è più
    autorevole del retrieval probabilistico e non deve pareggiare con esso.
    ``pin_first`` forza chunk in cima a valle della fusione.
    """
    if weights is not None and len(weights) != len(ranked_lists):
        raise ValueError("weights deve avere la stessa lunghezza di ranked_lists")

    scores: dict[UUID, float] = {}
    hits_by_id: dict[UUID, RetrievalHit] = {}

    for i, ranked in enumerate(ranked_lists):
        w = weights[i] if weights is not None else 1.0
        for rank, hit in enumerate(ranked, start=1):
            scores[hit.chunk_id] = scores.get(hit.chunk_id, 0.0) + w / (k + rank)
            existing = hits_by_id.get(hit.chunk_id)
            if existing is None or _lookup_priority(hit) > _lookup_priority(existing):
                hits_by_id[hit.chunk_id] = hit

    ordered = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    merged: list[RetrievalHit] = []
    seen: set[UUID] = set()

    if pin_first:
        for cid in pin_first:
            if cid in hits_by_id and cid in scores and cid not in seen:
                h = hits_by_id[cid]
                merged.append(h.model_copy(update={"score_final": scores[cid]}))
                seen.add(cid)

    for cid, score in ordered:
        if cid in seen:
            continue
        merged.append(hits_by_id[cid].model_copy(update={"score_final": score}))
        seen.add(cid)
        if len(merged) >= top_k:
            break

    return merged[:top_k]


def ensure_direct_articles_first(
    hits: list[RetrievalHit],
    *,
    direct: Sequence[tuple[str, str]],
    top_k: int,
) -> list[RetrievalHit]:
    """Dopo il rerank, garantisce che gli articoli lookup diretto restino in top-k."""
    if not direct:
        return hits[:top_k]

    wanted = {(s, n) for s, n in direct}
    pinned: list[RetrievalHit] = []
    rest: list[RetrievalHit] = []
    seen: set[UUID] = set()

    for hit in hits:
        if hit.citation and (hit.citation.source, hit.citation.num) in wanted:
            if hit.chunk_id not in seen:
                pinned.append(hit)
                seen.add(hit.chunk_id)
        else:
            rest.append(hit)

    # Se un articolo diretto non è passato dal rerank, non lo forziamo (non abbiamo il hit).
    out = pinned + [h for h in rest if h.chunk_id not in seen]
    return out[:top_k]
