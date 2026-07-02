from __future__ import annotations

import json
from decimal import Decimal

import httpx
import pytest

from cerber_bot.integrations.cerber_core import CerberCoreClient
from cerber_bot.services.ledger import LedgerConfigurationError, LedgerService
from tests.test_cerber_core_client import SECRET_KEY_B64, encrypt_payload


@pytest.mark.asyncio
async def test_cerber_core_client_holds_funds() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["payload"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(
            status_code=200,
            json={
                "data": encrypt_payload(
                    {
                        "balance_usdt": 12.5,
                        "balance_rub": 1125.0,
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
        balance = await client.hold_funds(
            123456789,
            amount_usdt=Decimal("5.00"),
            description="deal hold",
            operation_id="deal:42:hold",
        )

    assert balance.balance_usdt == pytest.approx(Decimal("12.5"))
    assert captured["path"] == "/api/v1/balance/hold"
    payload = captured["payload"]
    assert isinstance(payload, dict)
    assert payload["amount_usdt"] == 5.0
    assert payload["operation_id"] == "deal:42:hold"
    assert payload["encrypted_user_hash"]


@pytest.mark.asyncio
async def test_cerber_core_client_transfers_funds() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["payload"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(
            status_code=200,
            json={
                "data": encrypt_payload(
                    {
                        "from": {
                            "balance_usdt": 10.0,
                            "balance_rub": 900.0,
                            "rate_usdt_rub": 90.0,
                        },
                        "to": {
                            "balance_usdt": 15.0,
                            "balance_rub": 1350.0,
                            "rate_usdt_rub": 90.0,
                        },
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
        from_balance, to_balance = await client.transfer_funds(
            111,
            222,
            amount_usdt=Decimal("5.00"),
            description="escrow release",
            operation_id="deal:7:transfer",
        )

    assert from_balance.balance_usdt == pytest.approx(Decimal("10"))
    assert to_balance.balance_usdt == pytest.approx(Decimal("15"))
    assert captured["path"] == "/api/v1/balance/transfer"
    payload = captured["payload"]
    assert isinstance(payload, dict)
    assert payload["from_encrypted_user_hash"]
    assert payload["to_encrypted_user_hash"]


def test_ledger_service_requires_configured_client() -> None:
    with pytest.raises(LedgerConfigurationError):
        LedgerService.from_client(None)


@pytest.mark.asyncio
async def test_ledger_service_hold_delegates_to_client() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=200,
            json={
                "data": encrypt_payload(
                    {
                        "balance_usdt": 99.0,
                        "balance_rub": 8910.0,
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
        ledger = LedgerService.from_client(client)
        snapshot = await ledger.hold(
            555,
            amount_usdt=Decimal("1.00"),
            description="test hold",
            operation_id="deal:1:hold",
        )

    assert snapshot.available_usdt == pytest.approx(Decimal("99"))
    assert snapshot.rate_usdt_rub == pytest.approx(Decimal("90"))
