"""Autenticazione account (free tier hosted).

Scelte di sicurezza, non negoziabili:
- password con Argon2id (argon2-cffi, parametri di default della libreria,
  aggiornati a monte); mai altri schemi, mai password loggata;
- token di sessione opachi (256 bit urlsafe) consegnati UNA volta al client:
  nel DB vive solo lo SHA-256, quindi un dump del DB non ruba sessioni;
- lookup sessione in tempo costante sull'hash, scadenza controllata lato
  server; il logout revoca la riga.
"""

from __future__ import annotations

import hashlib
import re
import secrets
from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from caucus_api.db.models import AuthSession, UserAccount

_hasher = PasswordHasher()

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD_LEN = 10


class AuthError(ValueError):
    """Errore utente (email invalida, credenziali errate, …)."""


def normalize_email(email: str) -> str:
    email = email.strip().lower()
    if not _EMAIL_RE.match(email) or len(email) > 255:
        raise AuthError("Indirizzo email non valido.")
    return email


def validate_password(password: str) -> None:
    if len(password) < MIN_PASSWORD_LEN:
        raise AuthError(f"Password troppo corta: minimo {MIN_PASSWORD_LEN} caratteri.")
    if len(password) > 512:
        raise AuthError("Password troppo lunga.")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def register(session: AsyncSession, *, email: str, password: str) -> UserAccount:
    email = normalize_email(email)
    validate_password(password)
    existing = (
        await session.execute(select(UserAccount.id).where(UserAccount.email == email))
    ).scalar_one_or_none()
    if existing is not None:
        raise AuthError("Esiste già un account con questa email.")
    user = UserAccount(email=email, password_hash=hash_password(password))
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def login(
    session: AsyncSession,
    *,
    email: str,
    password: str,
    session_days: int,
    user_agent: str | None = None,
) -> tuple[UserAccount, str, datetime]:
    """(utente, token in chiaro — consegnato UNA volta, scadenza)."""
    email = normalize_email(email)
    user = (
        await session.execute(select(UserAccount).where(UserAccount.email == email))
    ).scalar_one_or_none()
    # Verifica comunque un hash anche se l'utente non esiste: niente oracolo
    # temporale sull'esistenza dell'email.
    if user is None:
        verify_password(password, hash_password("timing-equalizer"))
        raise AuthError("Email o password errati.")
    if not verify_password(password, user.password_hash):
        raise AuthError("Email o password errati.")

    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(UTC) + timedelta(days=session_days)
    session.add(
        AuthSession(
            user_id=user.id,
            token_hash=_token_hash(token),
            expires_at=expires_at,
            user_agent=(user_agent or "")[:255] or None,
        )
    )
    user.last_login_at = datetime.now(UTC)
    await session.commit()
    return user, token, expires_at


async def resolve_session(session: AsyncSession, token: str) -> UserAccount | None:
    """Utente della sessione, o None se token invalido/scaduto."""
    if not token:
        return None
    row = (
        await session.execute(
            select(AuthSession, UserAccount)
            .join(UserAccount, UserAccount.id == AuthSession.user_id)
            .where(AuthSession.token_hash == _token_hash(token))
        )
    ).first()
    if row is None:
        return None
    auth_session: AuthSession = row[0]
    user: UserAccount = row[1]
    if auth_session.expires_at <= datetime.now(UTC):
        await session.delete(auth_session)
        await session.commit()
        return None
    return user


async def logout(session: AsyncSession, token: str) -> None:
    row = (
        await session.execute(
            select(AuthSession).where(AuthSession.token_hash == _token_hash(token))
        )
    ).scalar_one_or_none()
    if row is not None:
        await session.delete(row)
        await session.commit()
