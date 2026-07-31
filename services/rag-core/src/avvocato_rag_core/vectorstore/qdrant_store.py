"""Client Qdrant async con hybrid search (dense + sparse) e payload filtering.

Le collection sono create con schema fisso:
- vectors:  { dense: size=<dim>, distance=Cosine }
- sparse_vectors: { sparse: ... }  # se il provider embeddings supporta sparse
- payload schema indicizzato per lookup veloce (source, articolo, effective_*)
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any
from uuid import UUID

from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models as qm

from avvocato_rag_core.embeddings.base import EmbeddingVector


class QdrantStore:
    """Wrapper di convenienza per operazioni comuni su Qdrant."""

    def __init__(
        self,
        *,
        url: str,
        api_key: str | None = None,
        dense_dim: int = 1024,
    ) -> None:
        self._client = AsyncQdrantClient(url=url, api_key=api_key, prefer_grpc=False)
        self._dense_dim = dense_dim

    async def ensure_collection(self, name: str) -> None:
        """Crea la collection se non esiste, con schema hybrid dense+sparse."""
        existing = await self._client.get_collections()
        if any(c.name == name for c in existing.collections):
            info = await self._client.get_collection(name)
            vectors = info.config.params.vectors
            dense_cfg = vectors.get("dense") if isinstance(vectors, dict) else vectors
            current_dim = getattr(dense_cfg, "size", None) if dense_cfg else None
            if current_dim is not None and current_dim != self._dense_dim:
                # MAI cancellare silenziosamente: un cambio di EMBEDDING_DIM
                # distruggerebbe l'intero indice senza conferma. La collection
                # va eliminata esplicitamente (o EMBEDDING_DIM allineato).
                raise RuntimeError(
                    f"Collection {name!r} ha dense_dim={current_dim}, "
                    f"config richiede {self._dense_dim}. Rifiutato per evitare "
                    "perdita dati: allinea EMBEDDING_DIM/EMBEDDING_MODEL oppure "
                    "elimina la collection esplicitamente e re-ingesta."
                )
            return

        await self._client.create_collection(
            collection_name=name,
            vectors_config={
                "dense": qm.VectorParams(
                    size=self._dense_dim,
                    distance=qm.Distance.COSINE,
                    on_disk=True,
                ),
            },
            sparse_vectors_config={
                "sparse": qm.SparseVectorParams(
                    index=qm.SparseIndexParams(on_disk=True),
                ),
            },
            hnsw_config=qm.HnswConfigDiff(m=16, ef_construct=128, on_disk=True),
            optimizers_config=qm.OptimizersConfigDiff(default_segment_number=2),
        )

        # Payload indexes critici per filtering veloce su query legali
        for field, schema in (
            ("source", qm.PayloadSchemaType.KEYWORD),
            ("kind", qm.PayloadSchemaType.KEYWORD),
            ("articolo", qm.PayloadSchemaType.KEYWORD),
            ("effective_from", qm.PayloadSchemaType.DATETIME),
            ("effective_to", qm.PayloadSchemaType.DATETIME),
            ("tenant_id", qm.PayloadSchemaType.KEYWORD),
        ):
            await self._client.create_payload_index(
                collection_name=name, field_name=field, field_schema=schema
            )

    async def upsert(
        self,
        collection: str,
        ids: Sequence[UUID | str],
        embeddings: Sequence[EmbeddingVector],
        payloads: Sequence[dict[str, Any]],
    ) -> None:
        points = []
        for pid, vec, payload in zip(ids, embeddings, payloads, strict=True):
            vectors: dict[str, Any] = {"dense": vec.dense}
            if vec.sparse is not None:
                vectors["sparse"] = qm.SparseVector(
                    indices=vec.sparse.indices, values=vec.sparse.values
                )
            points.append(
                qm.PointStruct(
                    id=str(pid),
                    vector=vectors,
                    payload=payload,
                )
            )
        await self._client.upsert(collection_name=collection, points=points, wait=False)

    async def delete_by_payload(self, *, collection: str, field: str, value: str) -> None:
        """Elimina tutti i punti con payload ``field == value`` (no-op se la collection non esiste)."""
        existing = await self._client.get_collections()
        if not any(c.name == collection for c in existing.collections):
            return
        await self._client.delete(
            collection_name=collection,
            points_selector=qm.FilterSelector(
                filter=qm.Filter(
                    must=[qm.FieldCondition(key=field, match=qm.MatchValue(value=value))]
                )
            ),
            wait=True,
        )

    async def hybrid_search(
        self,
        collection: str,
        *,
        query: EmbeddingVector,
        limit: int,
        filters: Iterable[qm.FieldCondition] | None = None,
    ) -> list[qm.ScoredPoint]:
        """Hybrid search con RRF fusion di dense e sparse."""
        prefetch: list[qm.Prefetch] = [
            qm.Prefetch(query=query.dense, using="dense", limit=limit),
        ]
        if query.sparse is not None:
            prefetch.append(
                qm.Prefetch(
                    query=qm.SparseVector(indices=query.sparse.indices, values=query.sparse.values),
                    using="sparse",
                    limit=limit,
                )
            )

        must: list[qm.FieldCondition] = list(filters or [])
        query_filter = qm.Filter(must=must) if must else None

        response = await self._client.query_points(
            collection_name=collection,
            prefetch=prefetch,
            query=qm.FusionQuery(fusion=qm.Fusion.RRF),
            query_filter=query_filter,
            limit=limit,
            with_payload=True,
        )
        return response.points

    async def close(self) -> None:
        await self._client.close()

    @property
    def client(self) -> AsyncQdrantClient:
        """Escape hatch per operazioni avanzate non coperte dal wrapper."""
        return self._client
