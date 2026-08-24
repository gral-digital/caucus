"""Service di ricerca: vector + FTS + lookup diretto → merge RRF → rerank."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from functools import lru_cache
from time import perf_counter

import structlog
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from caucus_api.deps import get_corpus_map, get_db_session, get_llm_router, get_vectorstore
from caucus_api.services.fts_retriever import FtsRetriever
from caucus_rag_core.config import get_settings
from caucus_rag_core.embeddings.base import EmbeddingProvider
from caucus_rag_core.embeddings.factory import create_embedding_provider
from caucus_rag_core.hit_merge import ensure_direct_articles_first, reciprocal_rank_fusion
from caucus_rag_core.query_expander import LLMQueryExpander
from caucus_rag_core.query_router import ArticleRef, apply_routing, route_query
from caucus_rag_core.reranker import Reranker
from caucus_rag_core.reranker_factory import create_reranker
from caucus_rag_core.retriever import HybridRetriever
from caucus_rag_core.schemas.retrieval import (
    CorpusFilter,
    RetrievalHit,
    RetrievalQuery,
    RetrievalResult,
)
from caucus_rag_core.vectorstore.qdrant_store import QdrantStore

logger = structlog.get_logger(__name__)


@lru_cache(maxsize=1)
def _get_embedder() -> EmbeddingProvider:
    return create_embedding_provider(get_settings())


@lru_cache(maxsize=1)
def _get_reranker() -> Reranker:
    return create_reranker(get_settings())


@lru_cache(maxsize=1)
def _get_expander() -> LLMQueryExpander | None:
    if not get_settings().query_expansion_enabled:
        return None
    return LLMQueryExpander(get_llm_router(), model=get_settings().query_expansion_model)


class SearchService:
    def __init__(
        self,
        retriever: HybridRetriever,
        reranker: Reranker,
        fts: FtsRetriever,
    ) -> None:
        self._retriever = retriever
        self._reranker = reranker
        self._fts = fts

    @classmethod
    def factory(
        cls,
        vectorstore: QdrantStore = Depends(get_vectorstore),
        corpus_map: dict[CorpusFilter, str] = Depends(get_corpus_map),
        session: AsyncSession = Depends(get_db_session),
    ) -> SearchService:
        retriever = HybridRetriever(
            embedder=_get_embedder(),
            vectorstore=vectorstore,
            corpus_collection_map=corpus_map,
            case_law_ratio=get_settings().case_law_candidate_ratio,
        )
        return cls(
            retriever=retriever,
            reranker=_get_reranker(),
            fts=FtsRetriever(session),
        )

    @classmethod
    def build(cls, session: AsyncSession) -> SearchService:
        """Costruzione fuori dal ciclo di vita delle dependency FastAPI.

        Usata dagli endpoint streaming, dove la sessione DB deve vivere dentro
        il generatore (vedi routes/chat.py) e non può essere una dependency.
        """
        return cls(
            retriever=HybridRetriever(
                embedder=_get_embedder(),
                vectorstore=get_vectorstore(),
                corpus_collection_map=get_corpus_map(),
                case_law_ratio=get_settings().case_law_candidate_ratio,
            ),
            reranker=_get_reranker(),
            fts=FtsRetriever(session),
        )

    @staticmethod
    def _prefer_principle_chunks(
        reranked: list[RetrievalHit], merged: list[RetrievalHit]
    ) -> list[RetrievalHit]:
        """Per ogni sentenza nel top-k, il chunk col principio di diritto.

        Una pronuncia (specie le Sezioni Unite) ricostruisce prima gli
        orientamenti che poi supera: se a rappresentarla nel contesto finisce
        un chunk della ricostruzione, il modello può attribuirle la tesi
        OPPOSTA a quella accolta (osservato in prod 2026-08-24 sulla
        41570/2023). Se tra i candidati del merge c'è il chunk che enuncia il
        principio di diritto, è quello a rappresentare la sentenza.
        """
        principle_by_case: dict[str, RetrievalHit] = {}
        for h in merged:
            ext = h.metadata.get("case_external_id")
            if (
                ext
                and ext not in principle_by_case
                and "principio di diritto" in (h.text or "").lower()
            ):
                principle_by_case[ext] = h
        out: list[RetrievalHit] = []
        for h in reranked:
            ext = h.metadata.get("case_external_id")
            swap = principle_by_case.get(ext) if ext else None
            if swap is not None and swap.chunk_id != h.chunk_id:
                out.append(swap.model_copy(update={"score_final": h.score_final}))
            else:
                out.append(h)
        return out

    async def search(self, query: RetrievalQuery) -> RetrievalResult:
        t0 = perf_counter()
        routed = route_query(query.text, base_sources=query.sources)
        effective_query = apply_routing(query, routed)

        logger.info(
            "search.route",
            intent=routed.intent,
            sources=effective_query.sources,
            direct=[(a.source, a.num) for a in routed.direct_articles],
        )

        # L'espansione LLM (la parte lenta, ~1-2s) parte SUBITO; in parallelo
        # girano i rami DB sul testo originale. ATTENZIONE: le chiamate che
        # usano la AsyncSession (direct, fts, exp_lookup) devono restare
        # SEQUENZIALI tra loro: la sessione SQLAlchemy non ammette operazioni
        # concorrenti ("This session is provisioning a new connection...").
        # Se l'utente ha già citato un articolo per numero, il lookup diretto
        # è la chiave di retrieval: l'espansione aggiungerebbe solo latenza.
        expander = _get_expander() if not routed.direct_articles else None
        expansion_task = (
            asyncio.create_task(expander.expand(routed.original_text))
            if expander is not None
            else None
        )
        # Il ramo vettoriale parte SUBITO sulla query routata (pre-espansione),
        # in parallelo all'espansione LLM: attendere l'espansione per embeddare
        # il testo arricchito metteva in serie i due passi più lenti
        # (espansione ~1.7s + vettoriale ~0.5s). Il gap lessicale che
        # l'embedding perde è coperto dai candidati d'espansione, dal FTS
        # scoped e dal reranker (che riceve comunque la query espansa).
        vector_task = asyncio.create_task(self._retriever.retrieve(effective_query))
        direct_hits = await self._fts.direct_articles(
            routed.direct_articles, effective_at=effective_query.effective_at
        )
        fts_hits = await self._fts.search(
            routed,
            limit=effective_query.top_k_retrieve,
            effective_at=effective_query.effective_at,
        )

        # I suggerimenti euristici del router (regole di materia) entrano come
        # candidati NON pinnati, allo stesso rango dei riferimenti proposti
        # dall'espansione LLM: sono ipotesi, non certezze.
        suggested_refs: tuple[ArticleRef, ...] = routed.suggested_articles[:4]
        expansion_refs: tuple[ArticleRef, ...] = ()
        fts_scoped_hits: list[RetrievalHit] = []
        if expansion_task is not None:
            expansion = await expansion_task
            if expansion:
                effective_query = effective_query.model_copy(
                    update={"text": f"{effective_query.text}\n{expansion.text}"}
                )
                # Candidati di lookup NON pinnati: prima i riferimenti
                # strutturati della riga RIF (validati contro il catalogo
                # fonti), poi quelli scritti in prosa nella query arricchita
                # ("art. 2043 codice civile"). Se il modello ha suggerito
                # l'articolo giusto è un hit esatto, se ha sbagliato il
                # reranker lo affossa.
                exp_routed = route_query(expansion.text)
                user_refs = {(a.source, a.num) for a in routed.direct_articles}
                expansion_refs = tuple(
                    a
                    for a in dict.fromkeys((*expansion.refs, *exp_routed.direct_articles))
                    if (a.source, a.num) not in user_refs
                )[:6]
                # FTS RISTRETTO alle fonti individuate dall'espansione, con la
                # terminologia normativa espansa: quando il modello riconosce
                # la fonte giusta ma sbaglia il numero d'articolo (tipico sui
                # decreti recenti, es. whistleblowing), il testo trova
                # l'articolo che il numero manca. Limite basso e ambito
                # ristretto: un ramo FTS globale sul testo espanso è già stato
                # misurato dannoso (diluizione del merge, recall 96%→92%).
                scoped_sources = list(dict.fromkeys(a.source for a in expansion_refs))[:3]
                if scoped_sources:
                    fts_scoped_hits = await self._fts.search(
                        replace(exp_routed, sources=scoped_sources),
                        limit=8,
                        effective_at=effective_query.effective_at,
                    )

        expansion_hits = []
        candidate_refs = tuple(
            dict.fromkeys((*expansion_refs, *suggested_refs))
        )  # dedup preservando l'ordine
        if candidate_refs:
            expansion_hits = [
                h.model_copy(
                    update={
                        "score_final": 1.0,
                        "metadata": {**h.metadata, "lookup": "expansion"},
                    }
                )
                # 2 chunk per articolo (articolo-full + primo comma): con 6+
                # candidati, 8 chunk ciascuno inonderebbero il merge RRF
                # spingendo i rami FTS/vettoriale fuori dai rerank_candidates.
                for h in await self._fts.direct_articles(
                    candidate_refs,
                    effective_at=effective_query.effective_at,
                    per_ref_limit=2,
                )
            ]
        vector_result = await vector_task

        pin_ids = [h.chunk_id for h in direct_hits]
        merged = reciprocal_rank_fusion(
            [direct_hits, expansion_hits, fts_scoped_hits, fts_hits, vector_result.hits],
            top_k=effective_query.top_k_retrieve,
            pin_first=pin_ids or None,
            # Il lookup per numero di articolo è deterministico: pesa il triplo
            # dei rami probabilistici. I candidati dell'espansione LLM pesano
            # più del probabilistico ma meno del lookup utente.
            # NB (misurato): un ramo FTS GLOBALE sul testo espanso NON va
            # aggiunto: i chunk contati due volte nei rami probabilistici
            # superano i candidati d'espansione nel merge e li spingono fuori
            # dai rerank_candidates (recall 96%→92%, MRR 0.89→0.77). Il ramo
            # scoped (max 8 hit, max 3 fonti) non ha lo stesso effetto.
            weights=[3.0, 1.5, 1.2, 1.0, 1.0],
        )

        # Il reranker riceve la query ESPANSA: il cross-encoder è debole sul
        # gap dottrina↔testo normativo ("responsabilità extracontrattuale" vs
        # art. 2043: 0.0002), fortissimo quando la query contiene la
        # terminologia della norma (0.98). Misurato, non teorico.
        reranked = await self._reranker.rerank(
            effective_query.text,
            merged[: get_settings().rerank_candidates],
            top_k=effective_query.top_k_rerank,
        )
        direct_keys = [(a.source, a.num) for a in routed.direct_articles]
        reranked = ensure_direct_articles_first(
            reranked, direct=direct_keys, top_k=effective_query.top_k_rerank
        )
        # Dedup per partizione: lo stesso articolo non deve occupare più slot
        # del top-k con chunk diversi (articolo-full + comma): spreca contesto
        # e maschera articoli diversi rilevanti. I chunk giurisprudenziali non
        # hanno partition_id nel payload (tutti UUID(0): il dedup ne salvava
        # UNO in assoluto): per loro la chiave è la sentenza di provenienza.
        seen_partitions: set[object] = set()
        deduped = []
        for h in reranked:
            key = (
                h.metadata.get("case_external_id")
                if h.metadata.get("case_external_id")
                else h.partition_id
            )
            if key in seen_partitions:
                continue
            seen_partitions.add(key)
            deduped.append(h)
        reranked = deduped

        # Query a primaria normativa: al massimo UNA sentenza nel top-k. È il
        # comportamento storico (già validato dall'eval) che il vecchio dedup
        # produceva per accidente collassando tutti i chunk giurisprudenziali
        # su UUID(0): più slot alla giurisprudenza diluiscono il contesto
        # normativo e nei gap-case sopprimono l'ammissione di assenza
        # (misurato su gap-regionale: 3/3 pass -> 1/3).
        if not (effective_query.corpora and effective_query.corpora[0] == CorpusFilter.CASSAZIONE):
            kept_hits: list[RetrievalHit] = []
            case_slot_used = False
            for h in reranked:
                if h.metadata.get("case_external_id"):
                    if case_slot_used:
                        continue
                    case_slot_used = True
                kept_hits.append(h)
            reranked = kept_hits

        # Garanzia giurisprudenziale: con la Cassazione come corpus primario
        # (toggle o intento rilevato), 4 rami del merge su 5 producono solo
        # normativa e il cross-encoder — tarato sul confronto con articoli
        # brevi e puliti — può espellere ogni sentenza dal top-k (osservato
        # in prod 2026-08-24 proprio sulla domanda-campione delle SS.UU.
        # 41570/2023). Rientro deterministico: le migliori sentenze del merge
        # prendono la coda del top-k, una per pronuncia.
        if effective_query.corpora and effective_query.corpora[0] == CorpusFilter.CASSAZIONE:
            min_case_law = 2
            present = {
                h.metadata.get("case_external_id")
                for h in reranked
                if h.metadata.get("case_external_id")
            }
            if len(present) < min_case_law:
                refill = []
                for h in merged:
                    ext = h.metadata.get("case_external_id")
                    if not ext or ext in present:
                        continue
                    present.add(ext)
                    refill.append(h)
                    if len(present) >= min_case_law:
                        break
                if refill:
                    drop = len(reranked) + len(refill) - effective_query.top_k_rerank
                    if drop > 0:
                        kept: list[RetrievalHit] = []
                        for h in reversed(reranked):
                            if drop > 0 and not h.metadata.get("case_external_id"):
                                drop -= 1
                                continue
                            kept.append(h)
                        reranked = list(reversed(kept))
                    reranked = reranked + refill

        reranked = self._prefer_principle_chunks(reranked, merged)

        # One-hop expansion sul grafo dei rinvii: gli articoli citati dai top
        # hit entrano nel contesto come materiale ausiliario (in coda).
        ref_hits = await self._fts.expand_citations(
            reranked[:3], max_extra=3, effective_at=effective_query.effective_at
        )
        if ref_hits:
            reranked = reranked + ref_hits

        latency_ms = int((perf_counter() - t0) * 1000)
        logger.info(
            "search.done",
            vector=len(vector_result.hits),
            fts=len(fts_hits),
            direct=len(direct_hits),
            merged=len(merged),
            final=len(reranked),
            latency_ms=latency_ms,
        )

        return vector_result.model_copy(
            update={
                "query": effective_query,
                "hits": reranked,
                "total_retrieved": len(merged),
                "latency_ms": latency_ms,
            }
        )
