"""CLI ``caucus-ingest``.

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

from caucus_ingestion.fetchers.normattiva import NormattivaFetcher
from caucus_ingestion.parsers.normattiva_akn import (
    CODICI_CATALOG,
    NormattivaAknParser,
)
from caucus_rag_core.config import get_settings

logger = structlog.get_logger(__name__)
app = typer.Typer(
    add_completion=False,
    help="Ingestion CLI per Caucus. Scarica/parsa fonti italiane ed europee.",
    no_args_is_help=True,
)


FIXTURE_DIR = Path("data/fixtures/normattiva")


# Nomi storici che non seguono il pattern codice_{short_id}_*.akn.xml.
_LEGACY_FIXTURE_PREFIX = {"cc": "codice_civile", "cp": "codice_penale"}


def _fixture_path(short_id: str) -> Path:
    """Trova la fixture più recente per una fonte del catalogo.

    Pattern: ``codice_{short_id}_YYYYMMDD.akn.xml`` (cc/cp usano i nomi storici
    ``codice_civile_*`` / ``codice_penale_*``). Con più snapshot, vince il più
    recente (ordinamento lessicografico della data nel nome).
    """
    if short_id not in CODICI_CATALOG:
        raise typer.BadParameter(
            f"Fonte sconosciuta: {short_id!r}. Valori validi: {', '.join(sorted(CODICI_CATALOG))}"
        )
    prefix = _LEGACY_FIXTURE_PREFIX.get(short_id, f"codice_{short_id}")
    candidates = sorted(FIXTURE_DIR.glob(f"{prefix}_*.akn.xml"))
    if not candidates:
        raise typer.BadParameter(
            f"Nessuna fixture per {short_id!r} in {FIXTURE_DIR}. "
            f"Esegui `caucus-ingest fetch -c {short_id}`."
        )
    return candidates[-1]


# ----------------------------------------------------------------------


@app.command("fetch")
def cmd_fetch(
    codice: Annotated[
        str,
        typer.Option(
            "--codice", "-c", help="short_id dal catalogo (cc, cp, cds, ...; vedi CODICI_CATALOG)"
        ),
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
    codice: Annotated[
        str,
        typer.Option(
            "--codice", "-c", help="short_id dal catalogo (cc, cp, cds, ...; vedi CODICI_CATALOG)"
        ),
    ],
    xml_path: Annotated[
        Path | None,
        typer.Option("--xml", help="Path al file AKN XML (default: fixture repo)"),
    ] = None,
) -> None:
    """Parsa un XML AKN e stampa il count articoli (senza indicizzazione)."""
    path = xml_path or _fixture_path(codice)
    if not path.exists():
        raise typer.BadParameter(
            f"File non trovato: {path}. Esegui prima `caucus-ingest fetch -c {codice}`."
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
    codice: Annotated[
        str,
        typer.Option(
            "--codice", "-c", help="short_id dal catalogo (cc, cp, cds, ...; vedi CODICI_CATALOG)"
        ),
    ],
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
                f"Fixture mancante: {xml_path}. Esegui `caucus-ingest fetch -c {codice}` prima."
            )
        logger.info("ingest.using_fixture", path=str(xml_path))
        act = parser.parse_file(xml_path, short_id=codice)
    else:
        fetcher = NormattivaFetcher(user_agent=settings.normattiva_user_agent)
        dl = await fetcher.fetch_codice(codice)
        hint = None
        if len(dl.dataVigenza) == 8 and dl.dataVigenza.isdigit():
            from datetime import date as _date

            hint = _date(
                int(dl.dataVigenza[:4]), int(dl.dataVigenza[4:6]), int(dl.dataVigenza[6:8])
            )
        act = parser.parse_bytes(dl.xml_bytes, short_id=codice, expression_date_hint=hint)

    # 2. Persistence
    engine = create_async_engine(settings.database_url)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    # Import locali per mantenere la CLI veloce per `parse`.
    from caucus_ingestion.loader import Loader
    from caucus_rag_core.embeddings.factory import create_embedding_provider
    from caucus_rag_core.vectorstore.qdrant_store import QdrantStore

    embedder = None
    vectorstore = None

    if not skip_embeddings:
        embedder = create_embedding_provider(settings)
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


# ----------------------------------------------------------------------
# EUR-Lex (regolamenti e direttive UE in italiano)
# ----------------------------------------------------------------------

EURLEX_FIXTURE_DIR = Path("data/fixtures/eurlex")


def _eurlex_fixture_path(short_id: str) -> Path:
    from caucus_ingestion.fetchers.eurlex import EURLEX_CATALOG

    if short_id not in EURLEX_CATALOG:
        raise typer.BadParameter(
            f"Atto UE sconosciuto: {short_id!r}. Validi: {', '.join(sorted(EURLEX_CATALOG))}"
        )
    candidates = sorted(EURLEX_FIXTURE_DIR.glob(f"{short_id}_*.html"))
    if not candidates:
        raise typer.BadParameter(
            f"Nessuna fixture per {short_id!r} in {EURLEX_FIXTURE_DIR}. "
            f"Esegui `caucus-ingest fetch-eu -c {short_id}`."
        )
    return candidates[-1]


@app.command("fetch-eu")
def cmd_fetch_eu(
    atto: Annotated[str, typer.Option("--atto", "-c", help="short_id UE (gdpr, aiact, ...)")],
) -> None:
    """Scarica l'HTML italiano di un atto UE da EUR-Lex e lo salva come fixture."""
    asyncio.run(_run_fetch_eu(atto))


async def _run_fetch_eu(atto: str) -> None:
    from datetime import date as _date

    from caucus_ingestion.fetchers.eurlex import EurlexFetcher

    settings = get_settings()
    fetcher = EurlexFetcher(user_agent=settings.normattiva_user_agent)
    html = await fetcher.fetch(atto)
    EURLEX_FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    target = EURLEX_FIXTURE_DIR / f"{atto}_{_date.today().strftime('%Y%m%d')}.html"
    target.write_bytes(html)
    typer.echo(f"✓ {atto} scaricato: {target} ({len(html) / 1024:.0f} KB)")


@app.command("ingest-eu")
def cmd_ingest_eu(
    atto: Annotated[str, typer.Option("--atto", "-c", help="short_id UE (gdpr, aiact, ...)")],
    from_fixture: Annotated[bool, typer.Option("--from-fixture")] = False,
    skip_embeddings: Annotated[bool, typer.Option("--skip-embeddings")] = False,
) -> None:
    """Ingesta un atto UE in Postgres + (opzionale) Qdrant."""
    asyncio.run(_run_ingest_eu(atto, from_fixture, skip_embeddings))


async def _run_ingest_eu(atto: str, from_fixture: bool, skip_embeddings: bool) -> None:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from caucus_ingestion.fetchers.eurlex import EurlexFetcher, EurlexParser
    from caucus_ingestion.loader import Loader
    from caucus_rag_core.embeddings.factory import create_embedding_provider
    from caucus_rag_core.vectorstore.qdrant_store import QdrantStore

    settings = get_settings()
    parser = EurlexParser()

    if from_fixture:
        html = _eurlex_fixture_path(atto).read_bytes()
    else:
        html = await EurlexFetcher(user_agent=settings.normattiva_user_agent).fetch(atto)
    act = parser.parse_bytes(html, short_id=atto)

    engine = create_async_engine(settings.database_url)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    embedder = None
    vectorstore = None
    if not skip_embeddings:
        embedder = create_embedding_provider(settings)
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
    typer.echo(f"✓ {atto} (EUR-Lex) ingesto in Postgres{'' if skip_embeddings else ' + Qdrant'}.")


# ----------------------------------------------------------------------
# Cassazione (SentenzeWeb)
# ----------------------------------------------------------------------


@app.command("ingest-cassazione")
def cmd_ingest_cassazione(
    kind: Annotated[str, typer.Option("--kind", "-k", help="snciv | snpen")] = "snpen",
    max_docs: Annotated[int, typer.Option("--max", help="Numero massimo di sentenze")] = 500,
    start: Annotated[int, typer.Option("--start", help="Offset di partenza (paginazione)")] = 0,
    rows: Annotated[int, typer.Option("--rows", help="Sentenze per pagina")] = 50,
    anno: Annotated[
        int | None,
        typer.Option(
            "--anno",
            help=(
                "Limita l'harvest a un anno di decisione. Senza filtro la "
                "paginazione parte dal più recente: il corpus resta schiacciato "
                "sugli ultimi anni (misurato in prod: copertura solo 2025+)."
            ),
        ),
    ] = None,
) -> None:
    """Harvest incrementale da SentenzeWeb → Postgres + Qdrant (collection cassazione).

    Idempotente per external_id: rilanciare riprende senza duplicare.
    """
    if kind not in ("snciv", "snpen"):
        raise typer.BadParameter("kind deve essere snciv o snpen")
    asyncio.run(_run_ingest_cassazione(kind, max_docs, start, rows, anno))


async def _run_ingest_cassazione(
    kind: str, max_docs: int, start: int, rows: int, anno: int | None = None
) -> None:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from caucus_ingestion.cassazione_loader import CassazioneLoader
    from caucus_ingestion.fetchers.cassazione import SentenzeWebFetcher
    from caucus_rag_core.embeddings.factory import create_embedding_provider
    from caucus_rag_core.vectorstore.qdrant_store import QdrantStore

    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    vectorstore = QdrantStore(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key,
        dense_dim=settings.embedding_dim,
    )
    embedder = create_embedding_provider(settings)

    loaded = 0
    offset = start
    async with (
        SentenzeWebFetcher(user_agent=settings.normattiva_user_agent) as fetcher,
        session_maker() as session,
    ):
        loader = CassazioneLoader(
            session=session,
            embedder=embedder,
            vectorstore=vectorstore,
            collection=settings.qdrant_collection_cassazione,
        )
        query_extra = f'anno:"{anno}"' if anno is not None else None
        while loaded < max_docs:
            num_found, docs, received = await fetcher.search(
                kind=kind, start=offset, rows=rows, query_extra=query_extra
            )
            if received == 0:
                break
            n = await loader.load_batch(docs[: max_docs - loaded])
            loaded += n
            offset += received
            typer.echo(
                f"  {kind}: +{n} nuove (tot {loaded}/{max_docs}, offset {offset}/{num_found})"
            )
            if offset >= num_found:
                break
    await vectorstore.close()
    typer.echo(f"✓ Cassazione {kind}: {loaded} sentenze indicizzate.")


@app.command("ingest-ga")
def cmd_ingest_ga(
    sede: Annotated[
        str, typer.Option("--sede", help='"Consiglio di Stato" o città TAR (es. "Roma")')
    ] = "Consiglio di Stato",
    anno: Annotated[int, typer.Option("--anno", help="Anno dei provvedimenti")] = 2026,
    tipo: Annotated[
        str, typer.Option("--tipo", help="Sentenza | Ordinanza | Decreto")
    ] = "Sentenza",
    max_docs: Annotated[int, typer.Option("--max", help="Numero massimo di provvedimenti")] = 200,
    page_size: Annotated[int, typer.Option("--page-size")] = 60,
) -> None:
    """Harvest giustizia amministrativa (TAR/CdS) → Postgres + Qdrant.

    Idempotente per external_id (ECLI): rilanciare riprende senza duplicare.
    I provvedimenti disponibili solo in PDF vengono scartati (v1).
    """
    asyncio.run(_run_ingest_ga(sede, anno, tipo, max_docs, page_size))


async def _run_ingest_ga(sede: str, anno: int, tipo: str, max_docs: int, page_size: int) -> None:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from caucus_ingestion.fetchers.giustizia_amministrativa import GiustiziaAmministrativaFetcher
    from caucus_ingestion.ga_loader import GALoader
    from caucus_rag_core.embeddings.factory import create_embedding_provider
    from caucus_rag_core.vectorstore.qdrant_store import QdrantStore

    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    vectorstore = QdrantStore(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key,
        dense_dim=settings.embedding_dim,
    )
    embedder = create_embedding_provider(settings)

    loaded = skipped = no_text = 0
    page = 1
    async with (
        GiustiziaAmministrativaFetcher(user_agent=settings.normattiva_user_agent) as fetcher,
        session_maker() as session,
    ):
        loader = GALoader(
            session=session,
            embedder=embedder,
            vectorstore=vectorstore,
            collection=settings.qdrant_collection_cassazione,
        )
        while loaded < max_docs:
            docs = await fetcher.search(
                sede=sede, anno=anno, tipo=tipo, page=page, page_size=page_size
            )
            if not docs:
                break
            known = await loader.existing_ids([d.external_id for d in docs])
            for doc in docs:
                if loaded >= max_docs:
                    break
                if doc.external_id in known:
                    skipped += 1
                    continue
                text = await fetcher.fetch_text(doc)
                if not text:
                    no_text += 1
                    continue
                if await loader.load_one(doc, text):
                    loaded += 1
            typer.echo(
                f"  {sede} {anno}: +{loaded} nuovi (pag. {page}, saltati {skipped}, senza testo {no_text})"
            )
            page += 1
    await vectorstore.close()
    typer.echo(f"✓ GA {sede} {anno} ({tipo}): {loaded} provvedimenti indicizzati.")
