"""Точка входа отдельного приложения CERBER Admin."""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramNetworkError
from aiogram.fsm.storage.memory import MemoryStorage

from cerber_bot.bot_runtime import build_bot_session, reset_webhook_with_retry
from cerber_bot.container import AppContainer
from cerber_bot.handlers.admin import build_admin_router
from cerber_bot.log_config import setup_logging


logger = logging.getLogger(__name__)

ADMIN_EVENT_POLL_INTERVAL_SECONDS = 2.0


async def run_admin_event_worker(container: AppContainer, admin_bot: Bot) -> None:
    while True:
        try:
            delivered = await container.admin_event_service.deliver_pending(admin_bot)
            if delivered:
                logger.info("Delivered %s admin event(s)", delivered)
        except Exception as error:
            logger.warning("Admin event worker failed: %s", error)
        await asyncio.sleep(ADMIN_EVENT_POLL_INTERVAL_SECONDS)


async def run() -> None:
    setup_logging()
    container = await AppContainer.build()

    if not container.settings.admin_bot_token:
        await container.close()
        raise RuntimeError("ADMIN_BOT_TOKEN не задан. CERBER Admin не может быть запущен отдельно.")

    session = build_bot_session(container.settings)
    bot = Bot(
        token=container.settings.admin_bot_token,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    user_bot_session = build_bot_session(container.settings)
    user_bot = Bot(
        token=container.settings.bot_token,
        session=user_bot_session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dispatcher = Dispatcher(storage=MemoryStorage())
    dispatcher.include_router(build_admin_router(container, user_bot=user_bot))
    worker_task = asyncio.create_task(run_admin_event_worker(container, bot), name="admin_event_worker")

    try:
        await reset_webhook_with_retry(bot)
        await dispatcher.start_polling(bot, allowed_updates=dispatcher.resolve_used_update_types())
    except TelegramNetworkError as error:
        logger.error(
            "Telegram API is unavailable. Check internet access, firewall, proxy or VPN settings. Details: %s",
            error,
        )
    finally:
        worker_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            pass
        await bot.session.close()
        await user_bot.session.close()
        await container.close()


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        logger.info("Admin bot stopped by user.")