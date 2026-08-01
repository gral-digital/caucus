"""Endpoint account per il free tier hosted.

Attivi solo con ``ACCOUNTS_ENABLED=true``: nel self-hosting single-tenant
(default) rispondono 404 e il resto dell'API è identico a prima. Il rate
limit condiviso si applica anche qui (brute-force sul login).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from caucus_api.deps import get_db_session, rate_limit
from caucus_api.services import auth_service
from caucus_rag_core.config import get_settings

router = APIRouter(dependencies=[Depends(rate_limit)])


def _require_accounts_enabled() -> None:
    if not get_settings().accounts_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)


class Credentials(BaseModel):
    email: str = Field(..., max_length=255)
    password: str = Field(..., max_length=512)


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str | None = None


class LoginOut(BaseModel):
    token: str = Field(..., description="Bearer di sessione: mostrato solo ora, conservalo.")
    expires_at: datetime
    user: UserOut


def _bearer(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token mancante.")
    return authorization[7:].strip()


class AuthConfigOut(BaseModel):
    accounts_enabled: bool
    free_daily_chat_limit: int


@router.get("/auth/config", response_model=AuthConfigOut)
async def auth_config() -> AuthConfigOut:
    """Config pubblica per il client: dice alla web app se servono gli account."""
    s = get_settings()
    return AuthConfigOut(
        accounts_enabled=s.accounts_enabled,
        free_daily_chat_limit=s.free_daily_chat_limit,
    )


@router.post("/auth/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def register(
    body: Credentials,
    session: AsyncSession = Depends(get_db_session),
) -> UserOut:
    _require_accounts_enabled()
    try:
        user = await auth_service.register(session, email=body.email, password=body.password)
    except auth_service.AuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    return UserOut(id=user.id, email=user.email, display_name=user.display_name)


@router.post("/auth/login", response_model=LoginOut)
async def login(
    body: Credentials,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> LoginOut:
    _require_accounts_enabled()
    try:
        user, token, expires_at = await auth_service.login(
            session,
            email=body.email,
            password=body.password,
            session_days=get_settings().auth_session_days,
            user_agent=request.headers.get("user-agent"),
        )
    except auth_service.AuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    return LoginOut(
        token=token,
        expires_at=expires_at,
        user=UserOut(id=user.id, email=user.email, display_name=user.display_name),
    )


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    session: AsyncSession = Depends(get_db_session),
    authorization: str | None = Header(None),
) -> None:
    _require_accounts_enabled()
    await auth_service.logout(session, _bearer(authorization))


@router.get("/auth/me", response_model=UserOut)
async def me(
    session: AsyncSession = Depends(get_db_session),
    authorization: str | None = Header(None),
) -> UserOut:
    _require_accounts_enabled()
    user = await auth_service.resolve_session(session, _bearer(authorization))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Sessione scaduta o non valida."
        )
    return UserOut(id=user.id, email=user.email, display_name=user.display_name)
