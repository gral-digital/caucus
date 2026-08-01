"""Export del parere in .docx con citazioni ri-verificate server-side.

Il client manda la risposta così com'è (markdown + tag ``<cite/>``): il
server NON si fida dello stato client: estrae le citazioni, le risolve di
nuovo contro il DB (rubrica, testo, vigenza/abrogazione) e produce il
documento. Un'eventuale citazione manomessa o scaduta emerge nell'allegato
come «non trovata» o «abrogata», mai come riferimento pulito.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from caucus_api.db.models import NormComma, NormPartition, NormSource
from caucus_api.deps import get_db_session, rate_limit, require_api_auth
from caucus_api.services.docx_export import (
    ResolvedRef,
    cite_display,
    extract_citation_keys,
    render_parere_docx,
)

router = APIRouter(dependencies=[Depends(require_api_auth), Depends(rate_limit)])

_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class ExportDocxRequest(BaseModel):
    question: str = Field(..., max_length=4000)
    answer: str = Field(..., max_length=100_000, description="Markdown con tag <cite/>.")
    effective_at: date | None = Field(None, description="Vigenza di riferimento (default oggi).")


async def _resolve_ref(session: AsyncSession, source: str, num: str, eff: date) -> ResolvedRef:
    display = cite_display(source, num)
    row = (
        await session.execute(
            select(NormPartition, NormSource)
            .join(NormSource, NormSource.id == NormPartition.source_id)
            .where(NormSource.short_id == source)
            .where(NormPartition.kind == "articolo")
            .where(NormPartition.number == num)
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
        return ResolvedRef(source=source, num=num, display=display, found=False)
    partition, norm_source = row

    text = partition.full_text
    if not text:
        commi = (
            (
                await session.execute(
                    select(NormComma)
                    .where(NormComma.partition_id == partition.id)
                    .order_by(NormComma.ordinal)
                )
            )
            .scalars()
            .all()
        )
        text = "\n".join(f"{c.number}. {c.text}" for c in commi) or None

    return ResolvedRef(
        source=source,
        num=num,
        display=display,
        source_title=norm_source.title,
        rubrica=partition.rubrica,
        text=text,
        abrogato=bool((partition.metadata_ or {}).get("abrogato")),
        found=True,
    )


@router.post("/export/docx")
async def export_docx(
    body: ExportDocxRequest,
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    eff = body.effective_at or date.today()
    refs = [
        await _resolve_ref(session, source, num, eff)
        for source, num in extract_citation_keys(body.answer)
    ]
    blob = render_parere_docx(
        question=body.question,
        answer=body.answer,
        refs=refs,
        generated_on=eff,
    )
    filename = f"parere_caucus_{eff.isoformat()}.docx"
    return Response(
        content=blob,
        media_type=_DOCX_MIME,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
