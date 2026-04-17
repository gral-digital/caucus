"""Loader: persiste CanonicalAct → Postgres + Qdrant.

Idempotente: rieseguito, fa upsert. Il criterio di idempotenza è:
- `norm_source` per `urn` (unique key).
- `norm_partition` per (source_id, kind, number, effective_from).
- `norm_comma` per (partition_id, ordinal, effective_from).

Quando un testo cambia, il loader chiude il vecchio record con `effective_to`
e inserisce uno nuovo con `effective_from` oggi. Questo è lo schema di
versioning documentato in docs/DATA_MODEL.md §5.
"""

from __future__ import annotations

from uuid import uuid4

import structlog
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from avvocato_api.db.models import (
    NormChunk,
    NormComma,
    NormPartition,
    NormSource,
)
from avvocato_ingestion.canonical import (
    CanonicalAct,
    CanonicalPartition,
)
from avvocato_ingestion.chunker import BuiltChunk, build_chunks
from avvocato_rag_core.embeddings.base import EmbeddingProvider
from avvocato_rag_core.schemas.norm import NormPartitionKind
from avvocato_rag_core.vectorstore.qdrant_store import QdrantStore

logger = structlog.get_logger(__name__)


class Loader:
    def __init__(
        self,
        *,
        session: AsyncSession,
        embedder: EmbeddingProvider,
        vectorstore: QdrantStore,
        qdrant_collection: str,
    ) -> None:
        self._s = session
        self._embedder = embedder
        self._vs = vectorstore
        self._collection = qdrant_collection

    async def load(self, act: CanonicalAct) -> None:
        logger.info("loader.start", urn=act.urn, short_id=act.short_id)
        await self._vs.ensure_collection(self._collection)

        source = await self._upsert_source(act)
        all_chunks: list[BuiltChunk] = []

        # Walk top-level: ogni partition è radice (Libri) o Articoli se semplice.
        for top in act.root:
            await self._load_partition(
                top,
                source_id=source.id,
                parent_id=None,
                parent_path=act.short_id,
                source_short_id=act.short_id,
                effective_from_iso=act.in_force_from.isoformat(),
                effective_to_iso=act.in_force_to.isoformat() if act.in_force_to else None,
                chunk_sink=all_chunks,
            )

        await self._s.flush()

        if all_chunks:
            await self._embed_and_index_chunks(all_chunks)

        logger.info(
            "loader.done",
            urn=act.urn,
            chunks=len(all_chunks),
            collection=self._collection,
        )

    # ------------------------------------------------------------------

    async def _upsert_source(self, act: CanonicalAct) -> NormSource:
        stmt = (
            insert(NormSource)
            .values(
                urn=act.urn,
                short_id=act.short_id,
                title=act.title,
                type=act.type.value,
                issued_at=act.issued_at,
                in_force_from=act.in_force_from,
                in_force_to=act.in_force_to,
                source_url=act.source_url,
                source_hash=act.source_hash,
            )
            .on_conflict_do_update(
                index_elements=[NormSource.urn],
                set_={
                    "title": act.title,
                    "source_hash": act.source_hash,
                    "in_force_to": act.in_force_to,
                },
            )
            .returning(NormSource)
        )
        res = await self._s.execute(stmt)
        return res.scalar_one()

    async def _load_partition(
        self,
        node: CanonicalPartition,
        *,
        source_id,
        parent_id,
        parent_path: str,
        source_short_id: str,
        effective_from_iso: str,
        effective_to_iso: str | None,
        chunk_sink: list[BuiltChunk],
    ) -> None:
        path = _build_ltree_path(parent_path, node)
        citation = _build_citation(node, source_short_id)

        partition = NormPartition(
            id=uuid4(),
            source_id=source_id,
            parent_id=parent_id,
            kind=node.kind.value,
            number=node.number,
            label=node.label,
            ordinal=0,  # ordine viene ricalcolato a query time con ltree
            path=path,
            citation=citation,
            rubrica=node.rubrica,
            full_text=node.full_text,
            effective_from=_parse_iso(effective_from_iso),
            effective_to=_parse_iso(effective_to_iso) if effective_to_iso else None,
        )
        self._s.add(partition)
        await self._s.flush()

        # Commi solo per articoli
        commi_rows: list[tuple] = []
        if node.kind == NormPartitionKind.ARTICOLO and node.commi:
            for idx, c in enumerate(node.commi):
                row = NormComma(
                    id=uuid4(),
                    partition_id=partition.id,
                    ordinal=idx,
                    number=c.number,
                    text=c.text,
                    letters=[dict(letter=l.letter, text=l.text) for l in c.letters]
                    if c.letters
                    else None,
                    effective_from=_parse_iso(effective_from_iso),
                    effective_to=_parse_iso(effective_to_iso) if effective_to_iso else None,
                )
                self._s.add(row)
                commi_rows.append((row.id, c.number, c.text))

            chunk_sink.extend(
                build_chunks(
                    partition_id=partition.id,
                    articolo_num=node.number,
                    source_short_id=source_short_id,
                    path=path,
                    rubrica=node.rubrica,
                    commi=commi_rows,
                    effective_from_iso=effective_from_iso,
                    effective_to_iso=effective_to_iso,
                )
            )

        for child in node.children:
            await self._load_partition(
                child,
                source_id=source_id,
                parent_id=partition.id,
                parent_path=path,
                source_short_id=source_short_id,
                effective_from_iso=effective_from_iso,
                effective_to_iso=effective_to_iso,
                chunk_sink=chunk_sink,
            )

    async def _embed_and_index_chunks(self, chunks: list[BuiltChunk]) -> None:
        texts = [c.text for c in chunks]
        vectors = await self._embedder.embed(texts, kind="passage")

        # Persistenza Postgres
        for chunk in chunks:
            self._s.add(
                NormChunk(
                    id=chunk.id,
                    partition_id=chunk.partition_id,
                    comma_id=chunk.comma_id,
                    chunk_kind=chunk.chunk_kind.value,
                    text=chunk.text,
                    token_count=chunk.token_count,
                    qdrant_point_id=chunk.id,
                    metadata_=chunk.metadata,
                )
            )
        await self._s.flush()

        # Upsert Qdrant
        await self._vs.upsert(
            collection=self._collection,
            ids=[c.id for c in chunks],
            embeddings=vectors,
            payloads=[{**c.metadata, "text": c.text} for c in chunks],
        )


# ----------------------------------------------------------------------


def _parse_iso(v: str):
    from datetime import date

    return date.fromisoformat(v)


def _build_ltree_path(parent_path: str, node: CanonicalPartition) -> str:
    """Costruisce un segmento ltree-safe dal nodo.

    ltree consente solo [A-Za-z0-9_]. Convertiamo quindi numeri romani e
    'bis/ter' in snake_case preservato.
    """
    segment = f"{node.kind.value}_{node.number}".lower()
    segment = segment.replace("-", "_").replace(" ", "_")
    segment = "".join(ch for ch in segment if ch.isalnum() or ch == "_")
    return f"{parent_path}.{segment}"


def _build_citation(node: CanonicalPartition, source_short_id: str) -> str:
    if node.kind == NormPartitionKind.ARTICOLO:
        suffix = _CITATION_SUFFIX.get(source_short_id, source_short_id)
        return f"art. {node.number} {suffix}"
    return f"{node.kind.value} {node.number}"


_CITATION_SUFFIX = {
    "cc": "c.c.",
    "cp": "c.p.",
    "cpc": "c.p.c.",
    "cpp": "c.p.p.",
    "cost": "Cost.",
}
