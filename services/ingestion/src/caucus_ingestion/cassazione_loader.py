"""Loader per la giurisprudenza di Cassazione → Postgres + Qdrant (`cassazione`).

Idempotenza incrementale: le sentenze sono identificate da ``external_id``
(id SentenzeWeb); quelle già presenti vengono saltate — l'harvest può essere
rilanciato quante volte si vuole e riprende da dove era arrivato.
"""

from __future__ import annotations

import uuid
from uuid import uuid4

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from caucus_api.db.models import CaseLaw, CaseLawChunk
from caucus_ingestion.chunker import estimate_tokens
from caucus_ingestion.fetchers.cassazione import SentenzaDoc
from caucus_rag_core.embeddings.base import EmbeddingProvider
from caucus_rag_core.vectorstore.qdrant_store import QdrantStore

logger = structlog.get_logger(__name__)

_WINDOW = 2400  # caratteri ≈ 600 token
_OVERLAP = 300

_KIND_DISPLAY = {"snciv": "Cass. civ.", "snpen": "Cass. pen."}


def case_display(doc: SentenzaDoc) -> str:
    """ "Cass. pen., Sez. 3, Sentenza n. 27992/2026 (dep. 23/07/2026)"."""
    bits = [_KIND_DISPLAY.get(doc.kind, "Cass.")]
    if doc.sezione:
        bits.append(f"Sez. {doc.sezione}")
    tip = doc.tipoprov or "Sentenza"
    bits.append(f"{tip} n. {doc.numero}/{doc.anno}")
    dep = f" (dep. {doc.data_deposito.strftime('%d/%m/%Y')})" if doc.data_deposito else ""
    return ", ".join(bits) + dep


def build_case_chunks(doc: SentenzaDoc, case_id: uuid.UUID) -> list[CaseLawChunk]:
    """Finestre con header contestuale + chunk dedicato per il dispositivo."""
    header = case_display(doc)
    if doc.materia:
        header += f" — {doc.materia}"
    eff_date = doc.data_deposito or doc.data_decisione
    eff = eff_date.isoformat() if eff_date is not None else "1900-01-01"
    base_meta: dict[str, object] = {
        "source": "cass",
        "kind": doc.kind,
        "case_external_id": doc.external_id,
        "display": header,
        "numero": doc.numero,
        "anno": doc.anno,
        "sezione": doc.sezione,
        # Necessari per il filtro di vigenza obbligatorio del retriever:
        # una sentenza "vale" dal deposito in poi.
        "effective_from": eff,
        "effective_to": "9999-12-31",
        "abrogato": False,
    }

    chunks: list[CaseLawChunk] = []

    def add(kind: str, text: str, extra: dict[str, object] | None = None) -> None:
        chunks.append(
            CaseLawChunk(
                id=uuid4(),
                case_id=case_id,
                chunk_kind=kind,
                text=text,
                token_count=estimate_tokens(text),
                qdrant_point_id=uuid4(),
                metadata_={**base_meta, "chunk_kind": kind, **(extra or {})},
            )
        )

    if doc.dispositivo:
        add("dispositivo", f"[Fonte] {header} — dispositivo\n\n{doc.dispositivo}")

    text = doc.full_text
    start = 0
    idx = 0
    while start < len(text):
        end = min(start + _WINDOW, len(text))
        piece = text[start:end]
        add("testo", f"[Fonte] {header}\n\n{piece}", {"window": idx})
        if end == len(text):
            break
        start = end - _OVERLAP
        idx += 1
    return chunks


class CassazioneLoader:
    def __init__(
        self,
        *,
        session: AsyncSession,
        embedder: EmbeddingProvider,
        vectorstore: QdrantStore,
        collection: str,
    ) -> None:
        self._s = session
        self._embedder = embedder
        self._vs = vectorstore
        self._collection = collection

    async def existing_ids(self, external_ids: list[str]) -> set[str]:
        if not external_ids:
            return set()
        rows = await self._s.execute(
            select(CaseLaw.external_id).where(CaseLaw.external_id.in_(external_ids))
        )
        return {r[0] for r in rows}

    async def load_batch(self, docs: list[SentenzaDoc]) -> int:
        """Persiste e indicizza le sentenze non ancora presenti. Ritorna quante nuove."""
        if not docs:
            return 0
        await self._vs.ensure_collection(self._collection)
        known = await self.existing_ids([d.external_id for d in docs])
        new_docs = [d for d in docs if d.external_id not in known]
        if not new_docs:
            return 0

        all_chunks: list[CaseLawChunk] = []
        for doc in new_docs:
            case = CaseLaw(
                id=uuid4(),
                external_id=doc.external_id,
                kind=doc.kind,
                tipoprov=doc.tipoprov,
                sezione=doc.sezione,
                numero=doc.numero,
                anno=doc.anno,
                ecli=doc.ecli,
                data_decisione=doc.data_decisione,
                data_deposito=doc.data_deposito,
                presidente=doc.presidente,
                relatore=doc.relatore,
                materia=doc.materia,
                dispositivo=doc.dispositivo,
                full_text=doc.full_text,
                filename=doc.filename,
                metadata_={"riferimenti": doc.riferimenti},
            )
            self._s.add(case)
            all_chunks.extend(build_case_chunks(doc, case.id))
        await self._s.flush()

        micro = 64
        for i in range(0, len(all_chunks), micro):
            batch = all_chunks[i : i + micro]
            vectors = await self._embedder.embed([c.text for c in batch], kind="passage")
            for c in batch:
                self._s.add(c)
            await self._s.flush()
            await self._vs.upsert(
                collection=self._collection,
                ids=[c.qdrant_point_id for c in batch],
                embeddings=vectors,
                payloads=[{**c.metadata_, "text": c.text} for c in batch],
            )
            await self._s.commit()

        logger.info("cassazione.batch_loaded", cases=len(new_docs), chunks=len(all_chunks))
        return len(new_docs)
