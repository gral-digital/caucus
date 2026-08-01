"""Embedding provider via Vertex AI Publisher Models.

In fase 2 Vertex ospita direttamente bge-m3 via Model Garden, oppure un
text-embedding Google (`text-multilingual-embedding-002`). L'interfaccia resta
identica: i call sites non cambiano quando si switcha modello.
"""

from __future__ import annotations

from collections.abc import Sequence

import httpx

from caucus_rag_core.embeddings.base import EmbeddingProvider, EmbeddingVector


class VertexEmbeddingProvider(EmbeddingProvider):
    """Chiama un endpoint Vertex AI per dense embeddings.

    Non produce sparse: per hybrid search in prod, o si usa LocalBGEM3Provider in
    un worker offline, o si ospita bge-m3 come custom container su Vertex.
    """

    def __init__(
        self,
        *,
        project: str,
        region: str,
        model_id: str = "text-multilingual-embedding-002",
        dense_dim: int = 768,
        access_token_factory: AccessTokenFactory,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._project = project
        self._region = region
        self._model_id = model_id
        self._dense_dim = dense_dim
        self._access_token_factory = access_token_factory
        self._http = http_client or httpx.AsyncClient(timeout=30.0)

    @property
    def model_name(self) -> str:
        return self._model_id

    @property
    def dense_dim(self) -> int:
        return self._dense_dim

    async def embed(
        self,
        texts: Sequence[str],
        *,
        kind: str = "passage",
    ) -> list[EmbeddingVector]:
        url = (
            f"https://{self._region}-aiplatform.googleapis.com/v1/projects/"
            f"{self._project}/locations/{self._region}/publishers/google/models/"
            f"{self._model_id}:predict"
        )
        task_type = "RETRIEVAL_DOCUMENT" if kind == "passage" else "RETRIEVAL_QUERY"
        instances = [{"content": t, "task_type": task_type} for t in texts]
        token = await self._access_token_factory()
        resp = await self._http.post(
            url,
            headers={"Authorization": f"Bearer {token}"},
            json={"instances": instances},
        )
        resp.raise_for_status()
        data = resp.json()
        return [
            EmbeddingVector(dense=p["embeddings"]["values"]) for p in data.get("predictions", [])
        ]


from collections.abc import Awaitable, Callable  # noqa: E402

AccessTokenFactory = Callable[[], Awaitable[str]]
