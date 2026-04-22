from __future__ import annotations

import httpx
import pytest

from cerber_bot.integrations.getmytg import (
    GetMyTGClient,
    GetMyTGConfigError,
    GetMyTGError,
    GetMyTGRequestError,
)


@pytest.mark.asyncio
async def test_getmytg_public_health_does_not_send_api_key() -> None:
    captured: dict[str, str | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["api_key"] = request.headers.get("x-api-key")
        return httpx.Response(status_code=200, json={"status": "ok"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = GetMyTGClient(
            base_url="https://api.getmytg.com",
            http_client=http_client,
            api_key="secret-key",
        )
        payload = await client.health_check()

    assert payload["status"] == "ok"
    assert captured["path"] == "/v1/service/health"
    assert captured["api_key"] is None


@pytest.mark.asyncio
async def test_getmytg_personal_endpoints_send_api_key() -> None:
    captured: dict[str, str | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["api_key"] = request.headers.get("x-api-key")
        return httpx.Response(status_code=200, json={"items": []})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = GetMyTGClient(
            base_url="https://api.getmytg.com",
            http_client=http_client,
            api_key="secret-key",
        )
        await client.list_countries_personal()

    assert captured["path"] == "/v1/accounts"
    assert captured["api_key"] == "secret-key"


@pytest.mark.asyncio
async def test_getmytg_protected_endpoints_require_api_key() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(status_code=200, json={"ok": True}))
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = GetMyTGClient(
            base_url="https://api.getmytg.com",
            http_client=http_client,
            api_key=None,
        )
        with pytest.raises(GetMyTGConfigError):
            await client.get_profile()


@pytest.mark.asyncio
async def test_getmytg_request_error_contains_status_code() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(status_code=409, json={"error": "Purchase conflict"})
    )
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = GetMyTGClient(
            base_url="https://api.getmytg.com",
            http_client=http_client,
            api_key="secret-key",
        )
        with pytest.raises(GetMyTGRequestError) as error:
            await client.request_code(11)

    assert error.value.status_code == 409
    assert error.value.error == "Purchase conflict"


@pytest.mark.asyncio
async def test_getmytg_wraps_connect_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = GetMyTGClient(
            base_url="https://api.getmytg.com",
            http_client=http_client,
            api_key="secret-key",
        )
        with pytest.raises(GetMyTGError):
            await client.get_purchase(1)
