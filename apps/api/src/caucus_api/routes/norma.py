"""Lettura del testo ufficiale di un articolo: destinazione dei link `<cite/>`.

Le citazioni nelle risposte sono rese dalla UI come link a
``/norma/{source}/art/{num}``: senza questo endpoint il trust layer si
fermerebbe a metà — l'utente può vedere che una citazione è verificata ma non
leggere la norma.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from caucus_api.db.models import NormComma, NormPartition, NormSource
from caucus_api.deps import get_db_session, rate_limit, require_api_auth

router = APIRouter(dependencies=[Depends(require_api_auth), Depends(rate_limit)])


class CommaOut(BaseModel):
    number: str
    text: str


class NormaOut(BaseModel):
    source: str = Field(..., description="short_id della fonte, es. 'cc'")
    source_title: str
    articolo: str
    rubrica: str | None = None
    citation: str = Field(..., description="Forma citazionale canonica")
    abrogato: bool = False
    effective_from: date
    effective_to: date | None = None
    commi: list[CommaOut]
    full_text: str | None = None
    source_url: str | None = None


@router.get("/norma/{source}/art/{num}", response_model=NormaOut)
async def get_articolo(
    source: str,
    num: str,
    effective_at: date | None = Query(
        None, description="Testo vigente alla data indicata (default: oggi)."
    ),
    session: AsyncSession = Depends(get_db_session),
) -> NormaOut:
    """Testo di un articolo per (fonte, numero), filtrato per vigenza."""
    eff = effective_at or date.today()
    row = (
        await session.execute(
            select(NormPartition, NormSource)
            .join(NormSource, NormSource.id == NormPartition.source_id)
            .where(NormSource.short_id == source.lower())
            .where(NormPartition.kind == "articolo")
            .where(NormPartition.number == num.lower())
            .where(NormPartition.effective_from <= eff)
            .where(
                or_(
                    NormPartition.effective_to.is_(None),
                    NormPartition.effective_to > eff,
                )
            )
            .limit(1)
        )
    ).first()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Articolo {num} della fonte {source!r} non trovato o non vigente al {eff}.",
        )
    partition, norm_source = row

    commi = (
        await session.execute(
            select(NormComma)
            .where(NormComma.partition_id == partition.id)
            .order_by(NormComma.ordinal)
        )
    ).scalars()

    return NormaOut(
        source=norm_source.short_id,
        source_title=norm_source.title,
        articolo=partition.number,
        rubrica=partition.rubrica,
        citation=partition.citation,
        abrogato=bool((partition.metadata_ or {}).get("abrogato")),
        effective_from=partition.effective_from,
        effective_to=partition.effective_to,
        commi=[CommaOut(number=c.number, text=c.text) for c in commi],
        full_text=partition.full_text,
        source_url=norm_source.source_url,
    )
