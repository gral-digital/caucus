"""CLI `avvocato-ingest`. Entry-point invocabile via Makefile / Cloud Run Jobs."""

from __future__ import annotations

import asyncio
from typing import Annotated

import structlog
import typer
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from avvocato_ingestion.loader import Loader
from avvocato_ingestion.parsers.normattiva import NormattivaParser
from avvocato_rag_core.config import get_settings
from avvocato_rag_core.embeddings.local import LocalBGEM3Provider
from avvocato_rag_core.vectorstore.qdrant_store import QdrantStore

logger = structlog.get_logger(__name__)
app = typer.Typer(add_completion=False, help="Ingestion CLI per Avvocato.")


@app.command("normattiva")
def cmd_normattiva(
    codice: Annotated[
        str,
        typer.Option(
            "--codice",
            "-c",
            help="Short-id del codice: cc | cp | cpc | cpp | cost",
        ),
    ],
) -> None:
    """Scarica e indicizza un codice da Normattiva."""
    asyncio.run(_run_normattiva(codice))


async def _run_normattiva(codice: str) -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    parser = NormattivaParser(user_agent=settings.normattiva_user_agent)
    act = await parser.fetch_codice(codice)
    await parser.aclose()

    embedder = LocalBGEM3Provider(model_name=settings.embedding_model)
    vectorstore = QdrantStore(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key,
        dense_dim=settings.embedding_dim,
    )

    async with session_maker() as session:
        loader = Loader(
            session=session,
            embedder=embedder,
            vectorstore=vectorstore,
            qdrant_collection=settings.qdrant_collection_codici,
        )
        await loader.load(act)
        await session.commit()

    await vectorstore.close()
    logger.info("ingestion.complete", codice=codice)


if __name__ == "__main__":  # pragma: no cover
    app()
