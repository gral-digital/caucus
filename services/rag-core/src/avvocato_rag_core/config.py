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
    llm_primary_model: str = "vertex_ai/llama-3.3-70b-instruct"
    llm_fallback_model: str = "vertex_ai/claude-sonnet-4-5"
    embedding_model: str = "BAAI/bge-m3"
    embedding_dim: int = 1024
    reranker_model: str = "BAAI/bge-reranker-v2-m3"

    # Ollama (dev locale: zero cloud, zero costi)
    ollama_base_url: str = "http://localhost:11434"
    ollama_llm_model: str = "qwen3:8b"
    ollama_embedding_model: str = "bge-m3"
    # Backend selection: 'ollama' | 'vertex' | 'local'
    embedding_backend: str = "ollama"
    llm_backend: str = "ollama"

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
