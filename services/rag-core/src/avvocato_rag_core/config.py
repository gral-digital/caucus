"""Configurazione runtime letta da env. Singleton via lru_cache."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configurazione globale condivisa tra api / workers / ingestion."""

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env", "../../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Runtime
    app_env: Literal["local", "dev", "prod"] = "local"
    log_level: str = "INFO"

    # API security
    # Token condiviso richiesto su /chat e /search (header Authorization: Bearer
    # o X-API-Key). Se vuoto: consentito SOLO con app_env=local; in dev/prod
    # l'API rifiuta le richieste (fail-closed) finché non è configurato.
    api_auth_token: str | None = None
    # Origini CORS ammesse, separate da virgola.
    cors_allow_origins: str = (
        "http://localhost:3000,http://localhost:3100,http://127.0.0.1:3000,http://127.0.0.1:3100"
    )
    # Richieste per minuto per IP su /chat e /search (0 = disabilitato).
    # NB: limiter in-memory per processo; con più istanze passare a Redis.
    rate_limit_per_minute: int = 30

    # Postgres
    database_url: str = Field(
        "postgresql+asyncpg://avvocato:avvocato@localhost:5432/avvocato",
        description="URL SQLAlchemy async.",
    )

    # Qdrant
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str | None = None
    qdrant_collection_codici: str = "codici"
    qdrant_collection_leggi: str = "leggi"
    qdrant_collection_cassazione: str = "cassazione"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Storage
    storage_provider: Literal["minio", "gcs"] = "minio"
    storage_endpoint: str | None = "http://localhost:9000"
    storage_access_key: str | None = None
    storage_secret_key: str | None = None
    storage_bucket_documents: str = "avvocato-documents"
    storage_bucket_sources: str = "avvocato-sources"

    # Langfuse
    langfuse_host: str | None = "http://localhost:3001"
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None

    # LLM
    llm_primary_model: str = "openai/gpt-4o-mini"
    llm_fallback_model: str = "openai/gpt-4o"
    # NB: embedding_model è usato SOLO dal backend "local" (bge-m3 → 1024 dim).
    # embedding_dim deve essere coerente col backend attivo: 1536 per il default
    # openai/text-embedding-3-small, 1024 per local/bge-m3 e ollama/bge-m3.
    # La factory (embeddings/factory.py) fallisce con messaggio chiaro se divergono.
    embedding_model: str = "BAAI/bge-m3"
    embedding_dim: int = 1536
    reranker_model: str = "BAAI/bge-reranker-v2-m3"
    # auto | keyword | cohere | local | noop
    reranker_backend: str = "auto"
    cohere_api_key: str | None = None
    cohere_rerank_model: str = "rerank-multilingual-v3.0"

    # OpenAI (SaaS default)
    openai_api_key: str | None = None
    openai_embedding_model: str = "text-embedding-3-small"

    # Ollama (dev locale offline: zero cloud, zero costi)
    ollama_base_url: str = "http://localhost:11434"
    ollama_llm_model: str = "qwen3:8b"
    ollama_embedding_model: str = "bge-m3"
    # Backend selection: 'openai' | 'ollama' | 'vertex' | 'local'
    embedding_backend: str = "openai"
    llm_backend: str = "openai"

    # GCP
    gcp_project: str | None = None
    gcp_region: str = "europe-west1"
    google_application_credentials: str | None = None
    anthropic_vertex_project_id: str | None = None
    anthropic_vertex_region: str = "europe-west1"

    # Ingestion
    normattiva_user_agent: str = "AvvocatoBot/0.1 (contact: dev@avvocato.it)"
    ingestion_rate_limit_per_second: float = 1.0


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
