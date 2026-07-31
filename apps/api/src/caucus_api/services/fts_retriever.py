"""Retrieval Postgres FTS + lookup diretto articolo per numero.

Entrambi i rami applicano il filtro di vigenza (``effective_at``, default oggi)
su ``norm_partition.effective_from/effective_to`` — stessa semantica del ramo
vettoriale (``HybridRetriever._build_filters``). Senza questo filtro, FTS e
lookup diretto restituivano versioni non vigenti alla data richiesta, e il
lookup diretto le pinnava pure in cima.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from caucus_api.db.models import NormChunk, NormPartition, NormSource
from caucus_api.db.models import NormCitation as NormCitationRow
from caucus_rag_core.query_router import ArticleRef, RoutedQuery
from caucus_rag_core.schemas.citation import NormCitation
from caucus_rag_core.schemas.retrieval import RetrievalHit

logger = structlog.get_logger(__name__)


class FtsRetriever:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def search(
        self,
        routed: RoutedQuery,
        *,
        limit: int = 20,
        effective_at: date | None = None,
    ) -> list[RetrievalHit]:
        """FTS italiano su norm_chunk, filtrato per vigenza."""
        terms = [routed.original_text]
        if routed.fts_extra_terms:
            terms.append(" ".join(routed.fts_extra_terms))
        fts_query = " ".join(terms)

        eff = effective_at or date.today()
        source_filter = ""
        params: dict[str, object] = {"q": fts_query, "lim": limit, "eff": eff}
        if routed.sources:
            source_filter = "AND ns.short_id = ANY(:sources)"
            params["sources"] = routed.sources

        sql = text(
            f"""
            SELECT
                nc.id AS chunk_id,
                nc.partition_id,
                nc.comma_id,
                nc.text,
                nc.metadata AS chunk_meta,
                np.number AS articolo,
                np.metadata AS partition_meta,
                ns.short_id AS source,
                ts_rank(nc.text_tsv, websearch_to_tsquery('italian_unaccent', :q)) AS rank
            FROM norm_chunk nc
            JOIN norm_partition np ON np.id = nc.partition_id
            JOIN norm_source ns ON ns.id = np.source_id
            WHERE nc.text_tsv @@ websearch_to_tsquery('italian_unaccent', :q)
              AND np.effective_from <= :eff
              AND (np.effective_to IS NULL OR np.effective_to > :eff)
              {source_filter}
            ORDER BY rank DESC
            LIMIT :lim
            """
        )

        rows = (await self._session.execute(sql, params)).mappings().all()
        or_fallback = False
        if not rows:
            # websearch_to_tsquery è AND-semantico: con query lunghe (es. dopo
            # query expansion) l'AND di 15+ termini non matcha nulla. Fallback:
            # OR dei termini significativi — ts_rank premia chi ne matcha di più.
            # I risultati OR sono però rumorosi (articoli lunghi pieni di parole
            # comuni): vengono marcati "fts-or" e NON ricevono boost dal reranker.
            words = set(re.findall(r"[a-zà-ù0-9]{3,}", fts_query.lower()))
            if words:
                params["q"] = " OR ".join(sorted(words)[:32])
                rows = (await self._session.execute(sql, params)).mappings().all()
                or_fallback = True
        hits: list[RetrievalHit] = []
        for row in rows:
            hit = self._row_to_hit(row, score=float(row["rank"]))
            if or_fallback:
                hit = hit.model_copy(update={"metadata": {**hit.metadata, "lookup": "fts-or"}})
            hits.append(hit)
        logger.info("fts_search.done", n=len(hits), intent=routed.intent, effective_at=str(eff))
        return hits

    async def direct_articles(
        self,
        articles: tuple[ArticleRef, ...],
        *,
        effective_at: date | None = None,
        per_ref_limit: int = 8,
    ) -> list[RetrievalHit]:
        """Lookup esatto per (source, numero articolo), filtrato per vigenza.

        ``per_ref_limit`` limita i chunk per articolo: i candidati suggeriti
        (espansione/regole di materia) sono ipotesi e non devono occupare più
        slot del merge di quanto serva a rappresentare l'articolo.
        """
        if not articles:
            return []

        eff = effective_at or date.today()
        hits: list[RetrievalHit] = []
        for ref in articles:
            stmt = (
                select(
                    NormChunk.id,
                    NormChunk.partition_id,
                    NormChunk.comma_id,
                    NormChunk.text,
                    NormPartition.number,
                    NormPartition.metadata_,
                    NormSource.short_id,
                )
                .join(NormPartition, NormPartition.id == NormChunk.partition_id)
                .join(NormSource, NormSource.id == NormPartition.source_id)
                .where(NormSource.short_id == ref.source)
                .where(NormPartition.kind == "articolo")
                .where(NormPartition.number == ref.num)
                .where(NormPartition.effective_from <= eff)
                .where(
                    or_(
                        NormPartition.effective_to.is_(None),
                        NormPartition.effective_to > eff,
                    )
                )
                # "articolo-full" < "comma" < "window": col limite basso il
                # chunk rappresentativo dell'articolo intero entra per primo.
                .order_by(NormChunk.chunk_kind, NormChunk.id)
                .limit(per_ref_limit)
            )
            rows = (await self._session.execute(stmt)).all()
            for i, row in enumerate(rows):
                chunk_id, part_id, comma_id, txt, num, part_meta, src = row
                metadata: dict[str, Any] = {"source": src, "articolo": num, "lookup": "direct"}
                if (part_meta or {}).get("abrogato"):
                    metadata["abrogato"] = True
                hits.append(
                    RetrievalHit(
                        chunk_id=chunk_id,
                        partition_id=part_id,
                        comma_id=comma_id,
                        citation=NormCitation(source=src, part="articolo", num=num),
                        text=txt,
                        score_final=10.0 - i * 0.01,  # pin forte, ordine stabile
                        metadata=metadata,
                    )
                )
        logger.info(
            "fts_direct.done",
            n=len(hits),
            articles=[(a.source, a.num) for a in articles],
            effective_at=str(eff),
        )
        return hits

    async def expand_citations(
        self,
        hits: list[RetrievalHit],
        *,
        max_extra: int = 3,
        effective_at: date | None = None,
    ) -> list[RetrievalHit]:
        """One-hop expansion sul grafo dei rinvii (norm_citation).

        Il testo di legge è denso di rinvii ("salvo quanto previsto
        dall'art. …"): l'articolo citato serve spesso a rispondere quanto
        quello recuperato. Per i top hit, recupera gli articoli che essi
        rinviano e li aggiunge al contesto (marcati ``lookup="ref"``).
        """
        if not hits or max_extra <= 0:
            return []

        eff = effective_at or date.today()
        from_ids = [h.partition_id for h in hits]
        already = {h.partition_id for h in hits}

        rows = (
            await self._session.execute(
                select(
                    NormChunk.id,
                    NormChunk.partition_id,
                    NormChunk.comma_id,
                    NormChunk.text,
                    NormChunk.chunk_kind,
                    NormPartition.number,
                    NormPartition.metadata_,
                    NormSource.short_id,
                    NormCitationRow.raw_text,
                )
                .join(
                    NormCitationRow,
                    NormCitationRow.to_partition_id == NormChunk.partition_id,
                )
                .join(NormPartition, NormPartition.id == NormChunk.partition_id)
                .join(NormSource, NormSource.id == NormPartition.source_id)
                .where(NormCitationRow.from_partition_id.in_(from_ids))
                .where(NormPartition.effective_from <= eff)
                .where(
                    or_(
                        NormPartition.effective_to.is_(None),
                        NormPartition.effective_to > eff,
                    )
                )
                # Un solo chunk rappresentativo per articolo: preferiamo
                # articolo-full, poi comma (ordinamento sotto + dedup in Python).
                .order_by(NormChunk.partition_id, NormChunk.chunk_kind)
                .limit(max_extra * 8)
            )
        ).all()

        extra: list[RetrievalHit] = []
        seen_partitions: set[UUID] = set()
        for chunk_id, part_id, comma_id, txt, chunk_kind, num, part_meta, src, raw in rows:
            if part_id in already or part_id in seen_partitions:
                continue
            # "articolo-full" < "comma" < "window" alfabeticamente: il primo
            # chunk per partizione è quello preferito grazie all'order_by.
            del chunk_kind
            seen_partitions.add(part_id)
            metadata: dict[str, Any] = {
                "source": src,
                "articolo": num,
                "lookup": "ref",
                "ref_raw": raw[:120],
            }
            if (part_meta or {}).get("abrogato"):
                metadata["abrogato"] = True
            extra.append(
                RetrievalHit(
                    chunk_id=chunk_id,
                    partition_id=part_id,
                    comma_id=comma_id,
                    citation=NormCitation(source=src, part="articolo", num=num),
                    text=txt,
                    score_final=0.01,  # in coda: contesto ausiliario, non risultato primario
                    metadata=metadata,
                )
            )
            if len(extra) >= max_extra:
                break
        if extra:
            logger.info(
                "ref_expansion.done",
                n=len(extra),
                targets=[(h.citation.source, h.citation.num) for h in extra if h.citation],
            )
        return extra

    @staticmethod
    def _row_to_hit(row: Any, *, score: float) -> RetrievalHit:
        r = row  # RowMapping
        src = r["source"]
        num = r["articolo"]
        metadata: dict[str, Any] = {"source": src, "articolo": num, "lookup": "fts"}
        if (r["partition_meta"] or {}).get("abrogato") or (r["chunk_meta"] or {}).get("abrogato"):
            metadata["abrogato"] = True
        return RetrievalHit(
            chunk_id=UUID(str(r["chunk_id"])),
            partition_id=UUID(str(r["partition_id"])),
            comma_id=UUID(str(r["comma_id"])) if r["comma_id"] else None,
            citation=NormCitation(source=src, part="articolo", num=num),
            text=r["text"],
            score_final=score,
            metadata=metadata,
        )
