from __future__ import annotations

import base64
import json
from decimal import Decimal

import httpx
import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from cerber_bot.integrations.cerber_core import CerberCoreClient


SECRET_KEY_BYTES = bytes(range(32))
SECRET_KEY_B64 = base64.b64encode(SECRET_KEY_BYTES).decode("ascii")


def encrypt_payload(payload: object) -> str:
    nonce = b"0123456789ab"
    aesgcm = AESGCM(SECRET_KEY_BYTES)
    ciphertext = aesgcm.encrypt(nonce, json.dumps(payload).encode("utf-8"), None)
    return base64.b64encode(nonce + ciphertext).decode("ascii")


@pytest.mark.asyncio
async def test_cerber_core_client_lists_transactions() -> None:
    captured: dict[str, str | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["api_key"] = request.headers.get("X-API-Key")
        captured["limit"] = request.url.params.get("limit")
        captured["offset"] = request.url.params.get("offset")
        captured["encrypted_user_hash"] = request.url.params.get("encrypted_user_hash")
        return httpx.Response(
            status_code=200,
            json={
                "data": encrypt_payload(
                    [
                        {
                            "id": "tx-1",
                            "service_id": "svc-1",
                            "user_hash": "hash-1",
                            "type": "topup",
                            "amount_usdt": 15.25,
                            "amount_rub": 1372.5,
                            "rate": 90.0,
                            "description": "Topup confirmed",
                            "created_at": "2026-05-17T10:00:00Z",
                        }
                    ]
                )
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = CerberCoreClient(
            base_url="https://core.example",
            http_client=http_client,
            api_key="api-key-1",
            secret_key=SECRET_KEY_B64,
        )
        transactions = await client.list_transactions(123456789, limit=5, offset=10)

    assert len(transactions) == 1
    assert transactions[0].id == "tx-1"
    assert transactions[0].amount_usdt == pytest.approx(15.25)
    assert transactions[0].description == "Topup confirmed"
    assert captured["path"] == "/api/v1/balance/history"
    assert captured["api_key"] == "api-key-1"
    assert captured["limit"] == "5"
    assert captured["offset"] == "10"
    assert captured["encrypted_user_hash"]


@pytest.mark.asyncio
async def test_cerber_core_client_adjusts_balance() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["api_key"] = request.headers.get("X-API-Key")
        captured["payload"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(
            status_code=200,
            json={
                "data": encrypt_payload(
                    {
                        "balance_usdt": 42.5,
                        "balance_rub": 3825.0,
                        "rate_usdt_rub": 90.0,
                    }
                )
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = CerberCoreClient(
            base_url="https://core.example",
            http_client=http_client,
            api_key="api-key-1",
            secret_key=SECRET_KEY_B64,
        )
        balance = await client.adjust_balance(
            123456789,
            delta_usdt=Decimal("-7.50"),
            tx_type="withdrawal",
            description="admin adjustment",
            operation_id="admin-adjust:1",
        )

    assert balance.balance_usdt == pytest.approx(42.5)
    assert balance.balance_rub == pytest.approx(3825.0)
    assert captured["path"] == "/api/v1/balance/adjust"
    assert captured["api_key"] == "api-key-1"
    payload = captured["payload"]
    assert isinstance(payload, dict)
    assert payload["delta_usdt"] == -7.5
    assert payload["tx_type"] == "withdrawal"
    assert payload["description"] == "admin adjustment"
    assert payload["operation_id"] == "admin-adjust:1"
    assert payload["encrypted_user_hash"]