from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from aiogram import Dispatcher

from cerber_admin.main import run_admin_event_worker
from cerber_bot.config import Settings
from cerber_bot.container import AppContainer
from cerber_bot.handlers.admin import build_admin_router


class FakeBot:
    def __init__(self) -> None:
        self.messages: list[tuple[int, str]] = []

    async def send_message(self, telegram_id: int, text: str, parse_mode=None, reply_markup=None) -> None:
        self.messages.append((telegram_id, text))


def _build_settings(database_path: Path) -> Settings:
    return Settings(
        BOT_TOKEN="123456:FAKE_TOKEN_FOR_TESTS",
        ADMIN_BOT_TOKEN="123456:FAKE_ADMIN_TOKEN_FOR_TESTS",
        DATABASE_URL=f"sqlite+aiosqlite:///{database_path.as_posix()}",
        GIFTAPI_TOKEN=None,
        GIFTAPI_SECRET=None,
        NICEPAY_MERCHANT_ID=None,
        NICEPAY_SECRET=None,
        WEB_ENABLED=False,
        MODERATOR_IDS="7001",
    )


@pytest.mark.asyncio
async def test_admin_router_can_be_included_in_dispatcher(tmp_path: Path) -> None:
    container = await AppContainer.build(_build_settings(tmp_path / "admin-router.db"))
    try:
        router = build_admin_router(container, user_bot=FakeBot())
        dispatcher = Dispatcher()
        dispatcher.include_router(router)
        assert router.name == "admin"
    finally:
        await container.close()


@pytest.mark.asyncio
async def test_admin_event_worker_delivers_pending_events(tmp_path: Path) -> None:
    container = await AppContainer.build(_build_settings(tmp_path / "admin-worker.db"))
    try:
        await container.admin_event_service.enqueue_deal_alert(
            text="<b>moderator alert</b>",
            deal_id=101,
            disputed=True,
        )

        bot = FakeBot()
        task = asyncio.create_task(run_admin_event_worker(container, bot))
        await asyncio.sleep(0.2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert bot.messages, "Worker did not deliver pending admin events"
        assert bot.messages[0] == (7001, "<b>moderator alert</b>")
    finally:
        await container.close()