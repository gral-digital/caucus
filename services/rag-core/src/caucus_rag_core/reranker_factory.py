"""Factory reranker: cohere → local bge → keyword boost → noop."""

from __future__ import annotations

import importlib.util

import structlog

from caucus_rag_core.config import Settings, get_settings
from caucus_rag_core.reranker import (
    CohereReranker,
    CrossEncoderReranker,
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
        # Verifica di disponibilità QUI (i loader dei modelli sono lazy: un
        # try/except sul costruttore non proteggerebbe nulla). Preferenza:
        # sentence-transformers (CrossEncoder, compatibile con transformers
        # recenti) > FlagEmbedding > keyword.
        if importlib.util.find_spec("sentence_transformers") is not None:
            return CrossEncoderReranker(
                model_name=cfg.reranker_model,
                device=cfg.reranker_device,
            )
        if importlib.util.find_spec("FlagEmbedding") is not None:
            return LocalBGEReranker(
                model_name=cfg.reranker_model,
                device=cfg.reranker_device,
                use_fp16=cfg.reranker_device != "cpu",
            )
        # Fallback RUMOROSO: il keyword reranker è molto più debole del
        # cross-encoder richiesto. Un degrado silenzioso ha già falsato una
        # sessione di eval (recall giù di punti senza che nulla lo segnalasse).
        structlog.get_logger(__name__).warning(
            "reranker_local_deps_missing_fallback_keyword",
            hint="uv sync --all-packages installa caucus-rag-core[reranker-local]",
        )
        return KeywordBoostReranker()

    if backend == "keyword":
        return KeywordBoostReranker()

    # auto: cohere se key, altrimenti keyword (sempre attivo, zero deps)
    if cfg.cohere_api_key:
        return CohereReranker(api_key=cfg.cohere_api_key, model=cfg.cohere_rerank_model)
    return KeywordBoostReranker()
