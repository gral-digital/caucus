"""Loader giustizia amministrativa (TAR + CdS) → Postgres + Qdrant.

Riusa la tabella ``case_law`` e la collection della giurisprudenza: il
provvedimento amministrativo è una decisione come quelle di Cassazione, con
``kind`` = "ga_" + schema del portale ("ga_cds", "ga_tar_rm", …) e display
citazionale proprio («Cons. St., Sez. 4, Sentenza n. 6189/2026», «TAR Roma,
Sez. 5, …»). Idempotente per external_id (ECLI): rilanciare riprende.
"""

from __future__ import annotations

import re
import uuid
from uuid import uuid4

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from caucus_api.db.models import CaseLaw, CaseLawChunk
from caucus_ingestion.chunker import estimate_tokens
from caucus_ingestion.fetchers.giustizia_amministrativa import GAProvvedimento
from caucus_rag_core.embeddings.base import EmbeddingProvider
from caucus_rag_core.vectorstore.qdrant_store import QdrantStore

logger = structlog.get_logger(__name__)

_WINDOW = 2400
_OVERLAP = 300


def _kind_for(doc: GAProvvedimento) -> str:
    m = re.search(r"schema=([a-z_]+)", doc.doc_url)
    schema = m.group(1) if m else "ga"
    return f"ga_{schema}"[:16]


def _sezione_breve(sezione: str | None) -> str | None:
    """«SEZIONE 4» → «4» (la colonna case_law.sezione è varchar(8))."""
    if not sezione:
        return None
    breve = re.sub(r"sezione\s*", "", sezione, flags=re.I).strip()
    return (breve or sezione)[:8]


def ga_display(doc: GAProvvedimento) -> str:
    """«Cons. St., Sez. 4, Sentenza n. 6189/2026» / «TAR Roma, Sez. 5, …»."""
    sede = doc.sede.title()
    if "Consiglio Di Stato" in sede:
        corte = "Cons. St."
    elif "C.G.A" in doc.sede.upper():
        corte = "C.G.A.R.S."
    else:
        corte = f"TAR {sede}"
    bits = [corte]
    if doc.sezione:
        num = _sezione_breve(doc.sezione)
        bits.append(f"Sez. {num}" if num else doc.sezione.title())
    # Il numero provvedimento del portale è AAAANNNNN: in citazione va il
    # progressivo senza l'anno ("6189/2026", non "202606189/2026").
    breve = doc.numero[4:].lstrip("0") if len(doc.numero) >= 8 else doc.numero
    bits.append(f"{doc.tipo.title()} n. {breve}/{doc.anno}")
    return ", ".join(bits)


def build_ga_chunks(doc: GAProvvedimento, full_text: str, case_id: uuid.UUID) -> list[CaseLawChunk]:
    header = ga_display(doc)
    base_meta: dict[str, object] = {
        "source": "ga",
        "kind": _kind_for(doc),
        "case_external_id": doc.external_id,
        "display": header,
        "numero": doc.numero,
        "anno": doc.anno,
        "sezione": _sezione_breve(doc.sezione),
        "sede": doc.sede,
        # Vigenza: il provvedimento "vale" dall'anno di pubblicazione (la data
        # di deposito esatta non è nei risultati di ricerca; v1 usa l'anno).
        "effective_from": f"{doc.anno or 1900}-01-01",
        "effective_to": "9999-12-31",
        "abrogato": False,
    }
    chunks: list[CaseLawChunk] = []
    start = 0
    idx = 0
    while start < len(full_text):
        end = min(start + _WINDOW, len(full_text))
        piece = full_text[start:end]
        chunks.append(
            CaseLawChunk(
                id=uuid4(),
                case_id=case_id,
                chunk_kind="testo",
                text=f"[Fonte] {header}\n\n{piece}",
                token_count=estimate_tokens(piece),
                qdrant_point_id=uuid4(),
                metadata_={**base_meta, "chunk_kind": "testo", "window": idx},
            )
        )
        if end == len(full_text):
            break
        start = end - _OVERLAP
        idx += 1
    return chunks


class GALoader:
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

    async def load_one(self, doc: GAProvvedimento, full_text: str) -> bool:
        """Persiste e indicizza un provvedimento. False se già presente."""
        await self._vs.ensure_collection(self._collection)
        if await self.existing_ids([doc.external_id]):
            return False
        case = CaseLaw(
            id=uuid4(),
            external_id=doc.external_id,
            kind=_kind_for(doc),
            tipoprov=doc.tipo.title(),
            sezione=_sezione_breve(doc.sezione),
            numero=doc.numero,
            anno=doc.anno,
            ecli=doc.ecli,
            full_text=full_text,
            metadata_={"sede": doc.sede, "nrg": doc.nrg, "doc_url": doc.doc_url},
        )
        self._s.add(case)
        chunks = build_ga_chunks(doc, full_text, case.id)
        await self._s.flush()

        micro = 64
        for i in range(0, len(chunks), micro):
            batch = chunks[i : i + micro]
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
        logger.info("ga.loaded", external_id=doc.external_id, chunks=len(chunks))
        return True
