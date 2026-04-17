"""CLI ``avvocato-ingest``.

Comandi:
  - ``fetch``: scarica AKN XML da Normattiva e lo salva come fixture.
  - ``ingest``: parsa AKN XML (da fixture o freshly downloaded) e lo indicizza
                in Postgres + Qdrant.
  - ``parse``: solo parse di un file locale (debug/inspection).

Per ambienti senza rete (CI, dev offline) preferire ``--from-fixture`` che usa
gli XML sotto ``data/fixtures/normattiva/``.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated

import structlog
import typer

from avvocato_ingestion.fetchers.normattiva import NormattivaFetcher
from avvocato_ingestion.parsers.normattiva_akn import (
    CODICI_CATALOG,
    NormattivaAknParser,
)
from avvocato_rag_core.config import get_settings

logger = structlog.get_logger(__name__)
app = typer.Typer(
    add_completion=False,
    help="Ingestion CLI per Avvocato. Scarica/parsa codici italiani da Normattiva.",
    no_args_is_help=True,
)


FIXTURE_DIR = Path("data/fixtures/normattiva")


def _fixture_path(short_id: str) -> Path:
    mapping = {
        "cc": "codice_civile_20260417.akn.xml",
        "cp": "codice_penale_20260417.akn.xml",
        "cpc": "codice_procedura_civile_20260417.akn.xml",
        "cpp": "codice_procedura_penale_20260417.akn.xml",
    }
    return FIXTURE_DIR / mapping[short_id]


# ----------------------------------------------------------------------


@app.command("fetch")
def cmd_fetch(
    codice: Annotated[
        str, typer.Option("--codice", "-c", help="cc | cp | cpc | cpp")
    ],
    output: Annotated[
        Path, typer.Option("--output", "-o", help="Destinazione XML (file o cartella)")
    ] = FIXTURE_DIR,
) -> None:
    """Scarica l'XML AKN di un codice da Normattiva."""
    asyncio.run(_run_fetch(codice, output))


async def _run_fetch(codice: str, output: Path) -> None:
    settings = get_settings()
    fetcher = NormattivaFetcher(user_agent=settings.normattiva_user_agent)
    dl = await fetcher.fetch_codice(codice)

    if output.is_dir() or str(output).endswith("/"):
        output.mkdir(parents=True, exist_ok=True)
        target = output / f"codice_{codice}_{dl.dataVigenza}.akn.xml"
    else:
        target = output
        target.parent.mkdir(parents=True, exist_ok=True)

    target.write_bytes(dl.xml_bytes)
    logger.info("fetch.done", codice=codice, path=str(target), size=len(dl.xml_bytes))
    typer.echo(f"✓ {codice} scaricato: {target} ({len(dl.xml_bytes) / 1024:.0f} KB)")


# ----------------------------------------------------------------------


@app.command("parse")
def cmd_parse(
    codice: Annotated[str, typer.Option("--codice", "-c", help="cc | cp | cpc | cpp")],
    xml_path: Annotated[
        Path | None,
        typer.Option("--xml", help="Path al file AKN XML (default: fixture repo)"),
    ] = None,
) -> None:
    """Parsa un XML AKN e stampa il count articoli (senza indicizzazione)."""
    path = xml_path or _fixture_path(codice)
    if not path.exists():
        raise typer.BadParameter(
            f"File non trovato: {path}. Esegui prima `avvocato-ingest fetch -c {codice}`."
        )

    parser = NormattivaAknParser()
    act = parser.parse_file(path, short_id=codice)
    root = act.root[0]
    articles = root.children
    with_rubrica = sum(1 for a in articles if a.rubrica)
    typer.echo(
        f"✓ {codice} parsato: {len(articles)} articoli, "
        f"{with_rubrica} con rubrica ({100 * with_rubrica / max(len(articles), 1):.1f}%)"
    )
    # Preview primi 3
    for a in articles[:3]:
        preview = (a.full_text or "")[:100].replace("\n", " ")
        typer.echo(f"   art. {a.number}: rubrica={a.rubrica!r}  commi={len(a.commi)}  «{preview}…»")


# ----------------------------------------------------------------------


@app.command("ingest")
def cmd_ingest(
    codice: Annotated[str, typer.Option("--codice", "-c", help="cc | cp | cpc | cpp")],
    from_fixture: Annotated[
        bool,
        typer.Option(
            "--from-fixture",
            help="Usa XML fixture già scaricato invece di ri-scaricare (preferito in CI/offline)",
        ),
    ] = False,
    skip_embeddings: Annotated[
        bool,
        typer.Option(
            "--skip-embeddings",
            help="Scrivi solo Postgres; salta embedding e upsert Qdrant (iterazione veloce)",
        ),
    ] = False,
) -> None:
    """Ingesta un codice in Postgres + (opzionale) Qdrant."""
    asyncio.run(_run_ingest(codice, from_fixture, skip_embeddings))


async def _run_ingest(codice: str, from_fixture: bool, skip_embeddings: bool) -> None:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    settings = get_settings()
    parser = NormattivaAknParser()

    # 1. Source XML
    if from_fixture:
        xml_path = _fixture_path(codice)
        if not xml_path.exists():
            raise RuntimeError(
                f"Fixture mancante: {xml_path}. Esegui `avvocato-ingest fetch -c {codice}` prima."
            )
        logger.info("ingest.using_fixture", path=str(xml_path))
        act = parser.parse_file(xml_path, short_id=codice)
    else:
        fetcher = NormattivaFetcher(user_agent=settings.normattiva_user_agent)
        dl = await fetcher.fetch_codice(codice)
        act = parser.parse_bytes(dl.xml_bytes, short_id=codice)

    # 2. Persistence
    engine = create_async_engine(settings.database_url)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    # Import locali per mantenere la CLI veloce per `parse`.
    from avvocato_ingestion.loader import Loader
    from avvocato_rag_core.embeddings.base import EmbeddingProvider
    from avvocato_rag_core.vectorstore.qdrant_store import QdrantStore

    embedder: EmbeddingProvider | None = None
    vectorstore: QdrantStore | None = None

    if not skip_embeddings:
        from avvocato_rag_core.embeddings.local import LocalBGEM3Provider

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
            skip_embeddings=skip_embeddings,
        )
        await loader.load(act)
        await session.commit()

    if vectorstore is not None:
        await vectorstore.close()
    logger.info("ingest.complete", codice=codice)
    typer.echo(f"✓ {codice} ingesto in Postgres{'' if skip_embeddings else ' + Qdrant'}.")


if __name__ == "__main__":  # pragma: no cover
    app()
