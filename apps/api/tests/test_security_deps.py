"""Test delle dependency di sicurezza: auth a token e rate limiting."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from avvocato_api import deps
from avvocato_rag_core.config import Settings


class _FakeClient:
    host = "10.0.0.1"


class _FakeRequest:
    def __init__(self, headers: dict[str, str] | None = None, host: str = "10.0.0.1") -> None:
        self.headers = headers or {}
        self.client = _FakeClient()
        self.client.host = host


def _settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, **overrides)  # type: ignore[call-arg]


@pytest.fixture(autouse=True)
def _patch_settings(monkeypatch):
    """Ogni test imposta le proprie settings via _use()."""

    def _use(settings: Settings) -> None:
        monkeypatch.setattr(deps, "get_settings", lambda: settings)

    yield _use
    deps._RATE_BUCKETS.clear()


async def test_auth_open_in_local_without_token(_patch_settings):
    _patch_settings(_settings(app_env="local", api_auth_token=None))
    await deps.require_api_auth(_FakeRequest())  # non deve sollevare


async def test_auth_fail_closed_outside_local(_patch_settings):
    _patch_settings(_settings(app_env="prod", api_auth_token=None))
    with pytest.raises(HTTPException) as exc:
        await deps.require_api_auth(_FakeRequest())
    assert exc.value.status_code == 503


async def test_auth_rejects_wrong_token(_patch_settings):
    _patch_settings(_settings(app_env="prod", api_auth_token="segreto"))
    with pytest.raises(HTTPException) as exc:
        await deps.require_api_auth(_FakeRequest({"authorization": "Bearer sbagliato"}))
    assert exc.value.status_code == 401


async def test_auth_accepts_bearer_and_x_api_key(_patch_settings):
    _patch_settings(_settings(app_env="prod", api_auth_token="segreto"))
    await deps.require_api_auth(_FakeRequest({"authorization": "Bearer segreto"}))
    await deps.require_api_auth(_FakeRequest({"x-api-key": "segreto"}))


async def test_rate_limit_blocks_after_threshold(_patch_settings):
    _patch_settings(_settings(rate_limit_per_minute=3))
    req = _FakeRequest(host="10.9.9.9")
    for _ in range(3):
        await deps.rate_limit(req)
    with pytest.raises(HTTPException) as exc:
        await deps.rate_limit(req)
    assert exc.value.status_code == 429


async def test_rate_limit_disabled_with_zero(_patch_settings):
    _patch_settings(_settings(rate_limit_per_minute=0))
    req = _FakeRequest(host="10.8.8.8")
    for _ in range(100):
        await deps.rate_limit(req)
