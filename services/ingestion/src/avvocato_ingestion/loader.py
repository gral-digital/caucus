"""Loader: persiste CanonicalAct → Postgres + Qdrant.

Idempotenza: delete-and-replace per fonte. Prima di caricare, il loader
elimina tutte le partizioni esistenti della fonte (cascade su commi, chunk,
citazioni via FK) e i punti Qdrant con payload `source == short_id`. Un re-run
produce quindi esattamente lo stesso corpus, mai duplicati.

NB: il versioning multivigenza (chiusura del vecchio record con `effective_to`
+ insert della nuova versione, docs/DATA_MODEL.md §5) NON è ancora
implementato: ogni load rappresenta un singolo snapshot consolidato, datato
con `expression_date` (FRBRExpression/FRBRdate del meta AKN). Un vincolo di
unicità su (source_id, kind, number) non è applicabile oggi: il CC contiene
legittimamente duplicati (artt. 1-31 delle preleggi + artt. 1-31 del codice)
finché la gerarchia resta piatta.
"""

from __future__ import annotations

import time
import uuid
from datetime import date
from uuid import uuid4

import structlog
from sqlalchemy import delete
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
        embedder: EmbeddingProvider | None,
        vectorstore: QdrantStore | None,
        qdrant_collection: str,
        skip_embeddings: bool = False,
    ) -> None:
        if not skip_embeddings and (embedder is None or vectorstore is None):
            raise ValueError("embedder e vectorstore sono richiesti se skip_embeddings=False")
        self._s = session
        self._embedder = embedder
        self._vs = vectorstore
        self._collection = qdrant_collection
        self._skip_embeddings = skip_embeddings

    async def load(self, act: CanonicalAct) -> None:
        logger.info(
            "loader.start",
            urn=act.urn,
            short_id=act.short_id,
            skip_embeddings=self._skip_embeddings,
        )
        if not self._skip_embeddings and self._vs is not None:
            await self._vs.ensure_collection(self._collection)

        source = await self._upsert_source(act)
        await self._delete_existing(source_id=source.id, short_id=act.short_id)
        all_chunks: list[BuiltChunk] = []

        # effective_from = data del consolidato (FRBRdate), NON la data storica
        # di entrata in vigore dell'atto: il testo parsato è quello vigente
        # alla data dello snapshot, non quello del 1942/1993.
        effective_from = act.expression_date or act.in_force_from
        if act.expression_date is None:
            logger.warning(
                "loader.no_expression_date",
                short_id=act.short_id,
                fallback=str(act.in_force_from),
            )

        # Walk top-level: ogni partition è radice (Libri) o Articoli se semplice.
        for top in act.root:
            await self._load_partition(
                top,
                source_id=source.id,
                parent_id=None,
                parent_path=act.short_id,
                source_short_id=act.short_id,
                effective_from_iso=effective_from.isoformat(),
                effective_to_iso=act.in_force_to.isoformat() if act.in_force_to else None,
                chunk_sink=all_chunks,
            )

        await self._s.flush()

        if all_chunks and not self._skip_embeddings:
            await self._embed_and_index_chunks(all_chunks)
        elif all_chunks:
            # Skip embeddings: persistiamo solo norm_chunk con qdrant_point_id=id.
            # Permette di fare un reindex dopo con un worker dedicato.
            await self._persist_chunks_without_embeddings(all_chunks)

        logger.info(
            "loader.done",
            urn=act.urn,
            chunks=len(all_chunks),
            indexed_qdrant=not self._skip_embeddings,
        )

    async def _persist_chunks_without_embeddings(self, chunks: list[BuiltChunk]) -> None:
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

    # ------------------------------------------------------------------

    async def _delete_existing(self, *, source_id: uuid.UUID, short_id: str) -> None:
        """Idempotenza: rimuove il corpus esistente della fonte prima del reload.

        Postgres: delete di norm_partition (cascade FK su commi/chunk/citazioni).
        Qdrant: delete dei punti con payload source == short_id.
        """
        res = await self._s.execute(
            delete(NormPartition).where(NormPartition.source_id == source_id)
        )
        deleted = getattr(res, "rowcount", 0) or 0
        if deleted:
            logger.info("loader.replaced_existing", short_id=short_id, partitions=deleted)
        if self._vs is not None:
            await self._vs.delete_by_payload(
                collection=self._collection, field="source", value=short_id
            )

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
        source_id: uuid.UUID,
        parent_id: uuid.UUID | None,
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
            metadata_={"abrogato": True} if node.abrogato else {},
        )
        # Niente flush per-partizione: gli id sono generati client-side (uuid4),
        # quindi parent_id e partition_id sono già noti. Un flush ogni ~3000
        # partizioni costava un round-trip ciascuno.
        self._s.add(partition)

        # Commi solo per articoli
        commi_rows: list[tuple[uuid.UUID, str, str]] = []
        if node.kind == NormPartitionKind.ARTICOLO and node.commi:
            for idx, c in enumerate(node.commi):
                row = NormComma(
                    id=uuid4(),
                    partition_id=partition.id,
                    ordinal=idx,
                    number=c.number,
                    text=c.text,
                    letters=[{"letter": letter.letter, "text": letter.text} for letter in c.letters]
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
                    abrogato=node.abrogato,
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
        """Processa i chunk in micro-batch per resilienza e visibilità.

        Strategia: N chunk alla volta → embed → persist Postgres → upsert Qdrant
        → commit parziale. Se un batch fallisce il resto del codice è già al
        sicuro su disco e posso ripartire dal checkpoint.
        """
        # Micro-batch scelto per ottimizzare throughput Ollama su Apple Silicon:
        # 64 chunk ≈ una richiesta embed di ~30k token, comfort zone per bge-m3.
        micro_batch = 64
        total = len(chunks)
        start_time = time.perf_counter()

        assert self._embedder is not None and self._vs is not None  # guardato nel costruttore

        for i in range(0, total, micro_batch):
            batch = chunks[i : i + micro_batch]
            texts = [c.text for c in batch]
            vectors = await self._embedder.embed(texts, kind="passage")

            for chunk in batch:
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

            await self._vs.upsert(
                collection=self._collection,
                ids=[c.id for c in batch],
                embeddings=vectors,
                payloads=[{**c.metadata, "text": c.text} for c in batch],
            )
            # Commit parziale: se l'ingestione si interrompe, il lavoro fatto resta.
            await self._s.commit()

            done = i + len(batch)
            elapsed = time.perf_counter() - start_time
            rate = done / elapsed if elapsed > 0 else 0.0
            eta = (total - done) / rate if rate > 0 else 0.0
            logger.info(
                "loader.batch_done",
                done=done,
                total=total,
                pct=f"{100 * done / total:.1f}%",
                rate_per_sec=f"{rate:.1f}",
                eta_sec=int(eta),
            )


# ----------------------------------------------------------------------


def _parse_iso(v: str) -> date:
    return date.fromisoformat(v)


def _build_ltree_path(parent_path: str, node: CanonicalPartition) -> str:
    """Costruisce un segmento ltree-safe dal nodo.

    ltree consente solo [A-Za-z0-9_]. Convertiamo quindi numeri romani e
    'bis/ter' in snake_case preservato.
    """
    segment = f"{node.kind.value}_{node.number}".lower()
    # "/" e "." compaiono nei numeri storici ("314/2") e nei sotto-numeri
    # ("2-quaterdecies.1"): vanno mappati a separatore esplicito, non rimossi,
    # altrimenti "314/2" collassa su "3142".
    segment = segment.replace("-", "_").replace(" ", "_").replace("/", "_").replace(".", "_")
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
    "cds": "cod. strada",
    "cdc": "cod. cons.",
    "ccii": "CCII",
    "ccp": "cod. contr. pubbl.",
    "cad": "CAD",
    "cts": "CTS",
    "tus": "TU stup.",
    "tui": "TU imm.",
    "tue": "TU ed.",
    "tusl": "TU sic. lav.",
    "tub": "TUB",
    "tuf": "TUF",
    "tuir": "TUIR",
    "cpriv": "cod. privacy",
    "l241": "L. 241/1990",
    "stat": "St. Lav.",
    "l689": "L. 689/1981",
    "lpf": "L. 247/2012",
}
