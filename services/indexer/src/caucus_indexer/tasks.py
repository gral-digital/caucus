"""Task Dramatiq per re-indicizzazione e re-embedding.

Invocate da Cloud Scheduler / Cloud Tasks in prod, oppure via CLI in dev.
"""

from __future__ import annotations

import dramatiq
import structlog
from dramatiq.brokers.redis import RedisBroker

from caucus_rag_core.config import get_settings

logger = structlog.get_logger(__name__)

_broker = RedisBroker(url=get_settings().redis_url)  # type: ignore[no-untyped-call]
dramatiq.set_broker(_broker)


@dramatiq.actor(max_retries=3, time_limit=60 * 60 * 1000)
def reindex_corpus(corpus: str) -> None:
    """Rebuild completo dell'indice per un corpus.

    Esempio uso da Python:
        reindex_corpus.send("codici")
    """
    logger.info("reindex_corpus.start", corpus=corpus)
    # TODO: implementare — delete collection Qdrant, re-esegui ingest da snapshots GCS.
    logger.info("reindex_corpus.done", corpus=corpus)


@dramatiq.actor(max_retries=5, time_limit=15 * 60 * 1000)
def refresh_codice(short_id: str) -> None:
    """Re-scarica e re-ingest un codice da Normattiva.

    Idempotente: il loader fa delete-and-replace per fonte. Si può schedulare
    settimanalmente.
    """
    logger.info("refresh_codice.start", short_id=short_id)
    import asyncio

    from caucus_ingestion.cli import _run_ingest

    asyncio.run(_run_ingest(short_id, from_fixture=False, skip_embeddings=False))
    logger.info("refresh_codice.done", short_id=short_id)
