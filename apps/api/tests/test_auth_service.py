"""Test delle primitive di autenticazione (parti pure, senza DB)."""

from __future__ import annotations

import pytest

from caucus_api.services.auth_service import (
    AuthError,
    _token_hash,
    hash_password,
    normalize_email,
    validate_password,
    verify_password,
)


def test_password_hash_roundtrip():
    h = hash_password("una-password-lunga")
    assert h.startswith("$argon2id$")
    assert verify_password("una-password-lunga", h)
    assert not verify_password("password-sbagliata", h)


def test_password_hash_is_salted():
    assert hash_password("stessa-password!") != hash_password("stessa-password!")


def test_verify_rejects_garbage_hash():
    assert not verify_password("qualsiasi", "non-un-hash")


def test_normalize_email():
    assert normalize_email("  Avv.Rossi@Studio.IT ") == "avv.rossi@studio.it"
    for bad in ("senza-chiocciola", "a@b", "spazi @dominio.it", ""):
        with pytest.raises(AuthError):
            normalize_email(bad)


def test_validate_password_length():
    with pytest.raises(AuthError):
        validate_password("corta")
    validate_password("abbastanza-lunga")


def test_token_hash_deterministic_and_opaque():
    assert _token_hash("tok") == _token_hash("tok")
    assert _token_hash("tok") != _token_hash("tok2")
    assert len(_token_hash("tok")) == 64  # sha256 hex: nel DB mai il token
