import hashlib
import hmac
import json
from decimal import Decimal

import httpx
import pytest

from cerber_bot.integrations.giftapi import GiftApiClient


@pytest.mark.asyncio
async def test_giftapi_client_signs_order_requests() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["authorization"] = request.headers.get("Authorization")
        captured["timestamp"] = request.headers.get("X-Timestamp")
        captured["signature"] = request.headers.get("X-Signature")
        captured["payload"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(
            status_code=201,
            json={
                "success": True,
                "data": {
                    "id": "12161770-8560-4377-9795-e8a70aaceb07",
                    "external_id": "CERBER-1001",
                    "status": "completed",
                    "total_amount": 29.09,
                    "currency": "USD",
                    "created_at": "2026-01-15T12:58:23+00:00",
                    "items": [
                        {
                            "sku_id": "sku-1",
                            "sku_name": "Apple Gift Card",
                            "quantity": 1,
                            "price": 29.09,
                            "currency": "USD",
                            "status": "completed",
                            "delivery_data": [{"pin": "CODE-123"}],
                            "customer_data": None,
                            "error_message": None,
                        }
                    ],
                },
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = GiftApiClient(
            base_url="https://sandbox.giftapi.io/api/v1/partner",
            http_client=http_client,
            token="gift-token",
            secret="gift-secret",
            locale="ru",
        )
        order = await client.create_order(
            external_id="CERBER-1001",
            sku_id="sku-1",
            fields={"quantity": 1},
            metadata={"source": "telegram"},
        )

    assert captured["authorization"] == "Bearer gift-token"
    expected_signature = hmac.new(
        b"gift-secret",
        f"{captured['timestamp']}sku-1CERBER-1001".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    assert captured["signature"] == expected_signature
    assert captured["payload"] == {
        "external_id": "CERBER-1001",
        "item": {"sku_id": "sku-1", "fields": {"quantity": 1}},
        "metadata": {"source": "telegram"},
    }
    assert order.external_id == "CERBER-1001"
    assert order.total_amount == Decimal("29.09")
