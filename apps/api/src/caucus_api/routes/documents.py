"""Upload di documenti per l'analisi documentale.

Il file viene convertito in testo all'upload e scartato: in Postgres resta
solo il testo (v1, niente storage del binario). Il client referenzia il
documento per id nei turni di chat (``ChatRequest.document_ids``).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from caucus_api.db.models import UserDocument
from caucus_api.deps import get_db_session, rate_limit, require_api_auth
from caucus_api.services.document_extract import DocumentExtractionError, extract_text

router = APIRouter(dependencies=[Depends(require_api_auth), Depends(rate_limit)])

# Un contratto di 100 pagine scansionato male non supera i 15 MB; oltre è
# quasi sempre un upload sbagliato (e un vettore di DoS sulla memoria).
MAX_UPLOAD_BYTES = 15 * 1024 * 1024


class DocumentOut(BaseModel):
    id: uuid.UUID
    filename: str
    media_type: str
    char_count: int
    truncated: bool
    excerpt: str
    created_at: datetime


@router.post("/documents", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile,
    session: AsyncSession = Depends(get_db_session),
) -> DocumentOut:
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"File troppo grande (max {MAX_UPLOAD_BYTES // (1024 * 1024)} MB).",
        )
    filename = file.filename or "documento"
    try:
        extracted = extract_text(filename, data)
    except DocumentExtractionError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc

    row = UserDocument(
        filename=filename[:255],
        media_type=extracted.media_type,
        text=extracted.text,
        char_count=len(extracted.text),
        truncated=extracted.truncated,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)

    return DocumentOut(
        id=row.id,
        filename=row.filename,
        media_type=row.media_type,
        char_count=row.char_count,
        truncated=row.truncated,
        excerpt=row.text[:280],
        created_at=row.created_at,
    )


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
) -> None:
    row = (
        await session.execute(select(UserDocument).where(UserDocument.id == document_id))
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Documento non trovato.")
    await session.delete(row)
    await session.commit()
