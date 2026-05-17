from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from httpx import ASGITransport, AsyncClient

from cerber_bot.config import Settings
from cerber_bot.container import AppContainer
from cerber_bot.db.repositories.tgaccounts import TgAccountRepository
from cerber_bot.db.repositories.users import UserRepository
from cerber_bot.handlers.tgaccounts import build_getmytg_callback_url
from cerber_bot.web.app import create_web_app


class StubBot:
    def __init__(self) -> None:
        self.messages: list[dict[str, object]] = []

    async def send_message(
        self,
        chat_id: int,
        text: str,
        parse_mode: str | None = None,
        reply_markup: object | None = None,
    ) -> None:
        self.messages.append(
            {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": parse_mode,
                "reply_markup": reply_markup,
            }
        )


def _build_settings(database_path: Path, *, webhook_secret: str | None = None) -> Settings:
    return Settings(
        BOT_TOKEN="123456:FAKE_TOKEN_FOR_TESTS",
        DATABASE_URL=f"sqlite+aiosqlite:///{database_path.as_posix()}",
        GIFTAPI_TOKEN=None,
        GIFTAPI_SECRET=None,
        GETMYTG_API_KEY="test-key",
        GETMYTG_WEBHOOK_SECRET=webhook_secret,
        NICEPAY_MERCHANT_ID=None,
        NICEPAY_SECRET=None,
        WEB_ENABLED=True,
        WEB_BASE_URL="https://example.test",
    )


def _path_and_query(url: str) -> str:
    parts = urlsplit(url)
    return parts.path + (f"?{parts.query}" if parts.query else "")


async def _seed_purchase(container: AppContainer) -> int:
    async with container.session_factory() as session:
        users = UserRepository(session)
        tg_repo = TgAccountRepository(session)
        user, _ = await users.get_or_create(
            telegram_id=1001,
            username="buyer",
            first_name="Buyer",
            last_name=None,
            language_code="ru",
            is_bot=False,
            balance_currency="USD",
        )
        user.balance = Decimal("20.00")
        purchase = await tg_repo.create(
            telegram_id=1001,
            getmytg_purchase_id=321,
            country_code="US",
            phone_number="+12025550123",
            status="PENDING",
            amount=Decimal("5.00"),
            currency="USD",
            purchase_type="SINGLE",
        )
        await session.commit()
        return purchase.id


@pytest.mark.asyncio
async def test_getmytg_webhook_updates_purchase_and_notifies_once(tmp_path: Path) -> None:
    container = await AppContainer.build(
        _build_settings(tmp_path / "getmytg-webhook.db", webhook_secret="super-secret")
    )
    bot = StubBot()
    try:
        local_purchase_id = await _seed_purchase(container)
        callback_url = build_getmytg_callback_url(container)
        assert callback_url is not None

        payload = {
            "result": "success",
            "timestamp": "2026-05-10T00:00:00.000Z",
            "data": {
                "purchase": {
                    "id": 321,
                    "country_code": "US",
                    "phone_number": "+12025550123",
                },
                "verification": {
                    "code": "12345",
                    "password": "secret123",
                },
            },
        }

        app = create_web_app(container, bot=bot)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(_path_and_query(callback_url), json=payload)
            duplicate = await client.post(_path_and_query(callback_url), json=payload)

        assert response.status_code == 200
        assert duplicate.status_code == 200

        async with container.session_factory() as session:
            tg_repo = TgAccountRepository(session)
            purchase = await tg_repo.get_by_getmytg_id(321)

        assert purchase is not None
        assert purchase.id == local_purchase_id
        assert purchase.status == "SUCCESS"
        assert purchase.verification_code == "12345"
        assert purchase.verification_password == "secret123"

        assert len(bot.messages) == 1
        assert bot.messages[0]["chat_id"] == 1001
        assert f"#{local_purchase_id}" in str(bot.messages[0]["text"])
        assert "12345" in str(bot.messages[0]["text"])
        assert bot.messages[0]["parse_mode"] == "HTML"
    finally:
        await container.close()


@pytest.mark.asyncio
async def test_getmytg_webhook_rejects_invalid_signature(tmp_path: Path) -> None:
    container = await AppContainer.build(
        _build_settings(tmp_path / "getmytg-webhook-invalid.db", webhook_secret="super-secret")
    )
    try:
        app = create_web_app(container)
        transport = ASGITransport(app=app)
        payload = {
            "result": "failed",
            "timestamp": "2026-05-10T00:00:00.000Z",
            "data": {
                "purchase": {
                    "id": 321,
                    "country_code": "US",
                    "phone_number": "+12025550123",
                },
                "error": {
                    "message": "Failed to get code",
                },
            },
        }
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/webhooks/getmytg?sig=invalid", json=payload)

        assert response.status_code == 403
    finally:
        await container.close()
