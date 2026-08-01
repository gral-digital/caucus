"""Factory condivisa per selezionare l'embedding provider da env."""

from __future__ import annotations

from caucus_rag_core.config import Settings, get_settings
from caucus_rag_core.embeddings.base import EmbeddingProvider


def create_embedding_provider(settings: Settings | None = None) -> EmbeddingProvider:
    """Istanzia l'embedder in base a ``EMBEDDING_BACKEND``.

    - ``openai``: OpenAI API (SaaS, nessuna dipendenza locale)
    - ``ollama``: Ollama locale (dev offline)
    - ``local``: FlagEmbedding bge-m3 in-process (richiede torch)
    - ``vertex``: Vertex AI (prod GCP, TBD)
    """
    cfg = settings or get_settings()
    backend = cfg.embedding_backend.lower()

    provider: EmbeddingProvider
    if backend == "openai":
        from caucus_rag_core.embeddings.openai import OpenAIEmbeddingProvider

        provider = OpenAIEmbeddingProvider(
            model=cfg.openai_embedding_model,
            dense_dim=cfg.embedding_dim,
            api_key=cfg.openai_api_key,
        )
    elif backend == "ollama":
        from caucus_rag_core.embeddings.ollama import OllamaEmbeddingProvider

        provider = OllamaEmbeddingProvider(
            base_url=cfg.ollama_base_url,
            model=cfg.ollama_embedding_model,
            dense_dim=cfg.embedding_dim,
        )
    elif backend == "local":
        from caucus_rag_core.embeddings.local import LocalBGEM3Provider

        provider = LocalBGEM3Provider(model_name=cfg.embedding_model)
    elif backend == "vertex":
        raise NotImplementedError(
            "VertexEmbeddingProvider richiede access_token_factory; config TBD in prod."
        )
    else:
        raise ValueError(f"Unknown embedding_backend: {backend!r}")

    # Guardia di coerenza: EMBEDDING_DIM guida lo schema della collection
    # Qdrant (deps.get_vectorstore). Un provider che produce vettori di
    # dimensione diversa (es. bge-m3 = 1024 vs EMBEDDING_DIM=1536) causerebbe
    # mismatch a runtime: meglio fallire subito con un messaggio chiaro.
    if provider.dense_dim != cfg.embedding_dim:
        raise ValueError(
            f"EMBEDDING_DIM={cfg.embedding_dim} ma il backend {backend!r} produce "
            f"vettori a {provider.dense_dim} dimensioni. Allinea EMBEDDING_DIM "
            f"a {provider.dense_dim} (e re-ingesta se la collection esiste già)."
        )
    return provider
