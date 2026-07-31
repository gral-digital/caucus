"""Factory reranker: cohere → local bge → keyword boost → noop."""

from __future__ import annotations

import importlib.util

from avvocato_rag_core.config import Settings, get_settings
from avvocato_rag_core.reranker import (
    CohereReranker,
    KeywordBoostReranker,
    LocalBGEReranker,
    NoopReranker,
    Reranker,
)


def create_reranker(settings: Settings | None = None) -> Reranker:
    cfg = settings or get_settings()
    backend = cfg.reranker_backend.lower()

    if backend == "noop":
        return NoopReranker()

    if backend == "cohere":
        if not cfg.cohere_api_key:
            raise ValueError("COHERE_API_KEY richiesta per reranker_backend=cohere")
        return CohereReranker(api_key=cfg.cohere_api_key, model=cfg.cohere_rerank_model)

    if backend == "local":
        # LocalBGEReranker importa FlagEmbedding solo al primo rerank (lazy):
        # un try/except sul costruttore non protegge nulla — verifichiamo la
        # disponibilità del modulo QUI, così il fallback avviene alla factory
        # e non con un crash alla prima query utente.
        if importlib.util.find_spec("FlagEmbedding") is not None:
            return LocalBGEReranker(model_name=cfg.reranker_model)
        return KeywordBoostReranker()

    if backend == "keyword":
        return KeywordBoostReranker()

    # auto: cohere se key, altrimenti keyword (sempre attivo, zero deps)
    if cfg.cohere_api_key:
        return CohereReranker(api_key=cfg.cohere_api_key, model=cfg.cohere_rerank_model)
    return KeywordBoostReranker()
