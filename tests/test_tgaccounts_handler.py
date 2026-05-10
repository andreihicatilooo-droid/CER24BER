from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from aiogram import Dispatcher

from cerber_bot.config import Settings
from cerber_bot.container import AppContainer
from cerber_bot.handlers.tgaccounts import build_getmytg_callback_url, build_tgaccounts_router, render_country_detail_screen
from cerber_bot.services.tgaccounts import TgCountryDetails


def _build_settings(database_path: Path) -> Settings:
    return Settings(
        BOT_TOKEN="123456:FAKE_TOKEN_FOR_TESTS",
        DATABASE_URL=f"sqlite+aiosqlite:///{database_path.as_posix()}",
        GIFTAPI_TOKEN=None,
        GIFTAPI_SECRET=None,
        GETMYTG_API_KEY="test-key",
        NICEPAY_MERCHANT_ID=None,
        NICEPAY_SECRET=None,
        WEB_ENABLED=False,
        WEB_BASE_URL="https://example.test",
    )


@pytest.mark.asyncio
async def test_tgaccounts_router_can_be_included_in_dispatcher(tmp_path: Path) -> None:
    container = await AppContainer.build(_build_settings(tmp_path / "tgaccounts-router.db"))
    try:
        router = build_tgaccounts_router(container)
        dispatcher = Dispatcher()
        dispatcher.include_router(router)
        assert router.name == "tgaccounts"
    finally:
        await container.close()


def test_render_country_detail_screen_includes_optional_fields() -> None:
    details = TgCountryDetails(
        country_code="RU",
        emoji="🇷🇺",
        display_name="Россия",
        amount=Decimal("5.00"),
        currency="USD",
        available=True,
        available_count=12,
        base_price=Decimal("6.00"),
        discount_percent=17,
    )

    screen = render_country_detail_screen(details)

    assert "Россия" in screen
    assert "5 USD" in screen
    assert "6 USD" in screen
    assert "17%" in screen
    assert "12" in screen


@pytest.mark.asyncio
async def test_build_getmytg_callback_url_uses_settings_path(tmp_path: Path) -> None:
    container = await AppContainer.build(_build_settings(tmp_path / "tgaccounts-callback.db"))
    try:
        assert build_getmytg_callback_url(container) == "https://example.test/webhooks/getmytg"
    finally:
        await container.close()