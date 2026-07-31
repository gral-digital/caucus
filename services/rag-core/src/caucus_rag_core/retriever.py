"""Retriever hybrid con filtri legal-aware.

Pipeline:
1. Embed query (dense + sparse se disponibile).
2. Hybrid search su Qdrant con filtri (source, effective_at, tenant).
3. Hydrate payload in RetrievalHit.
4. Il rerank è responsabilità di un modulo separato (Reranker).
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, date, datetime, time
from time import perf_counter
from uuid import UUID

import structlog
from qdrant_client.http import models as qm

from caucus_rag_core.embeddings.base import EmbeddingProvider
from caucus_rag_core.schemas.citation import NormCitation
from caucus_rag_core.schemas.retrieval import (
    CorpusFilter,
    RetrievalHit,
    RetrievalQuery,
    RetrievalResult,
)
from caucus_rag_core.vectorstore.qdrant_store import QdrantStore

logger = structlog.get_logger(__name__)


class HybridRetriever:
    """Retriever che interroga una o più collection Qdrant e fonde i risultati."""

    def __init__(
        self,
        *,
        embedder: EmbeddingProvider,
        vectorstore: QdrantStore,
        corpus_collection_map: dict[CorpusFilter, str],
        case_law_ratio: float = 0.25,
    ) -> None:
        self._embedder = embedder
        self._store = vectorstore
        self._corpus_map = corpus_collection_map
        # Frazione del budget candidati riservata alla giurisprudenza.
        self._case_law_ratio = case_law_ratio

    async def retrieve(self, query: RetrievalQuery) -> RetrievalResult:
        t0 = perf_counter()
        [query_vec] = await self._embedder.embed([query.text], kind="query")

        used_corpora: list[CorpusFilter] = []
        per_corpus: list[list[qm.ScoredPoint]] = []
        total_points = 0

        for i, corpus in enumerate(query.corpora):
            collection = self._corpus_map.get(corpus)
            if collection is None:
                logger.warning("corpus_not_configured", corpus=corpus)
                continue
            # Il filtro `sources` (short_id normativi) non ha senso sulla
            # giurisprudenza: applicarlo azzererebbe i risultati Cassazione
            # ogni volta che il router pinna una fonte normativa.
            skip_sources = corpus == CorpusFilter.CASSAZIONE
            filters = list(self._build_filters(query, skip_sources=skip_sources))
            # Quota per corpus: il PRIMO corpus in query.corpora è la fonte
            # primaria, gli altri sono di supporto e ricevono una frazione del
            # budget. Senza quota il corpus più grande (oggi Cassazione: 285k
            # chunk vs 64k di norme) si mangia gli slot e i risultati primari
            # non arrivano nemmeno al reranker. L'ordine di query.corpora è
            # quindi semantico: [codici, cassazione] per la ricerca normativa,
            # [cassazione, codici] per la ricerca giurisprudenziale.
            limit = query.top_k_retrieve
            if i > 0:
                limit = max(4, int(query.top_k_retrieve * self._case_law_ratio))
            points = await self._store.hybrid_search(
                collection,
                query=query_vec,
                limit=limit,
                filters=filters,
            )
            used_corpora.append(corpus)
            per_corpus.append(points)
            total_points += len(points)

        # Fusione inter-collection PROPORZIONALE: gli score RRF di collection
        # diverse non sono comparabili (dipendono dalla profondità della
        # lista), quindi si fonde per posizione. Un round-robin 1:1 però
        # sprecherebbe metà dei primi rank per la giurisprudenza: si inserisce
        # invece una voce secondaria ogni `stride` voci primarie, così la
        # normativa mantiene le posizioni di testa e la giurisprudenza resta
        # presente come supporto.
        interleaved: list[qm.ScoredPoint] = []
        if per_corpus:
            primary, *secondary = per_corpus
            stride = max(1, round(1 / self._case_law_ratio)) if self._case_law_ratio else 0
            sec_queue = [iter(lst) for lst in secondary]
            for i, point in enumerate(primary, start=1):
                interleaved.append(point)
                if stride and i % stride == 0:
                    for it in sec_queue:
                        nxt = next(it, None)
                        if nxt is not None:
                            interleaved.append(nxt)
            # Coda: eventuali secondari rimasti
            for it in sec_queue:
                interleaved.extend(it)

        hits = [self._to_hit(p) for p in interleaved]
        latency_ms = int((perf_counter() - t0) * 1000)
        logger.info(
            "retrieval_completed",
            n_hits=len(hits),
            corpora=used_corpora,
            latency_ms=latency_ms,
        )
        return RetrievalResult(
            query=query,
            hits=hits,
            total_retrieved=total_points,
            latency_ms=latency_ms,
            used_corpora=used_corpora,
        )

    def _build_filters(
        self, query: RetrievalQuery, *, skip_sources: bool = False
    ) -> Iterable[qm.FieldCondition]:
        if query.sources and not skip_sources:
            yield qm.FieldCondition(
                key="source",
                match=qm.MatchAny(any=list(query.sources)),
            )
        if query.tenant_id:
            yield qm.FieldCondition(
                key="tenant_id", match=qm.MatchValue(value=str(query.tenant_id))
            )
        # Il docstring di RetrievalQuery promette "None = oggi": il filtro di
        # vigenza è SEMPRE attivo. Senza default, versioni abrogate e vigenti
        # verrebbero mescolate silenziosamente.
        effective_at = query.effective_at or date.today()
        ref_dt = datetime.combine(effective_at, time.min, tzinfo=UTC)
        # effective_from <= ref_dt AND (effective_to IS NULL OR effective_to > ref_dt)
        yield qm.FieldCondition(key="effective_from", range=qm.DatetimeRange(lte=ref_dt))
        # NB: Qdrant non ha OR con null; la semantica "effective_to IS NULL or > X" è
        # implementata a livello di ingestione ponendo effective_to = "9999-12-31"
        # per norme vigenti, così il range funziona uniformemente.
        yield qm.FieldCondition(key="effective_to", range=qm.DatetimeRange(gt=ref_dt))

    @staticmethod
    def _to_hit(point: qm.ScoredPoint) -> RetrievalHit:
        payload = point.payload or {}
        citation: NormCitation | None = None
        if payload.get("source") and payload.get("articolo"):
            citation = NormCitation(
                source=str(payload["source"]),
                part="articolo",
                num=str(payload["articolo"]),
                comma=payload.get("comma"),
            )
        partition_id = (
            UUID(str(payload["partition_id"])) if "partition_id" in payload else UUID(int=0)
        )
        comma_id = UUID(str(payload["comma_id"])) if payload.get("comma_id") else None
        return RetrievalHit(
            chunk_id=UUID(str(point.id)),
            partition_id=partition_id,
            comma_id=comma_id,
            citation=citation,
            text=payload.get(
                "text", ""
            ),  # opzionale: alcuni indici non salvano il testo nel payload
            score_final=float(point.score or 0.0),
            metadata=payload,
        )
