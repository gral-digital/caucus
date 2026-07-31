"""Retrieval Postgres FTS + lookup diretto articolo per numero.

Entrambi i rami applicano il filtro di vigenza (``effective_at``, default oggi)
su ``norm_partition.effective_from/effective_to`` — stessa semantica del ramo
vettoriale (``HybridRetriever._build_filters``). Senza questo filtro, FTS e
lookup diretto restituivano versioni non vigenti alla data richiesta, e il
lookup diretto le pinnava pure in cima.
"""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from avvocato_api.db.models import NormChunk, NormPartition, NormSource
from avvocato_rag_core.query_router import ArticleRef, RoutedQuery
from avvocato_rag_core.schemas.citation import NormCitation
from avvocato_rag_core.schemas.retrieval import RetrievalHit

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
        hits: list[RetrievalHit] = []
        for row in rows:
            hits.append(self._row_to_hit(row, score=float(row["rank"])))
        logger.info("fts_search.done", n=len(hits), intent=routed.intent, effective_at=str(eff))
        return hits

    async def direct_articles(
        self,
        articles: tuple[ArticleRef, ...],
        *,
        effective_at: date | None = None,
    ) -> list[RetrievalHit]:
        """Lookup esatto per (source, numero articolo), filtrato per vigenza."""
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
                .limit(8)
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
