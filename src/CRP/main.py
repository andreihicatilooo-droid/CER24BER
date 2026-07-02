"""Точка входа CRP — бота репутации для чатов."""

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
from cerber_bot.config import load_settings
from cerber_bot.container import AppContainer
from cerber_bot.log_config import setup_logging
from CRP.bot import build_crp_router


logger = logging.getLogger(__name__)


async def run() -> None:
    setup_logging()
    settings = load_settings()
    if not settings.crp_bot_token:
        raise RuntimeError("CRP_BOT_TOKEN не задан. Бот репутации не может быть запущен.")

    container = await AppContainer.build(settings)
    session = build_bot_session(settings)
    bot = Bot(
        token=settings.crp_bot_token,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    dispatcher = Dispatcher(storage=MemoryStorage())
    dispatcher.include_router(build_crp_router(container))

    try:
        await reset_webhook_with_retry(bot)
        await dispatcher.start_polling(bot, allowed_updates=dispatcher.resolve_used_update_types())
    except TelegramNetworkError as error:
        logger.error("Telegram API is unavailable. Check internet access, firewall, proxy or VPN settings. Details: %s", error)
    finally:
        await bot.session.close()
        await container.close()


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        logger.info("CRP bot stopped by user.")
