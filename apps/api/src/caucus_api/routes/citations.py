"""Validazione citazioni di un testo arbitrario (Word add-in, integrazioni).

Stesso trust layer della chat, esposto come endpoint: estrae i riferimenti
normativi (tag ``<cite/>`` e prosa «art. 2043 c.c.») e li verifica contro il
corpus — esistenza, fonte, vigenza, abrogazione. A differenza della chat non
c'è un contesto di retrieval, quindi il campo ``grounding`` non viene
riportato: qui si giudica il testo dell'utente, non una risposta del modello.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from caucus_api.deps import get_db_session, rate_limit, require_api_auth
from caucus_api.services.chat_service import ChatService

router = APIRouter(dependencies=[Depends(require_api_auth), Depends(rate_limit)])


class ValidateRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=300_000)


class ValidateResponse(BaseModel):
    valid: list[dict[str, str | bool]]
    invalid: list[dict[str, str | bool]]
    total: int


@router.post("/citations/validate", response_model=ValidateResponse)
async def validate_citations(
    body: ValidateRequest,
    session: AsyncSession = Depends(get_db_session),
) -> ValidateResponse:
    service = ChatService.build(session)
    result = await service._validate_citations(body.text, hits=[])
    for c in result["valid"]:
        c.pop("grounding", None)
    return ValidateResponse(valid=result["valid"], invalid=result["invalid"], total=result["total"])
