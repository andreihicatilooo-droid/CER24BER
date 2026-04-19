"""Точка входа CEER Bot.

Собирает Dispatcher, регистрирует роутеры, запускает polling.
Запуск: python -m ceer_bot
"""

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

import uvicorn

from ceer_bot.config import load_settings
from ceer_bot.container import AppContainer
from ceer_bot.handlers.chat_events import build_chat_events_router
from ceer_bot.handlers.game import build_game_router
from ceer_bot.handlers.start import build_start_router
from ceer_bot.handlers.tictactoe import build_tictactoe_router
from ceer_bot.handlers.blackjack import build_blackjack_router
from ceer_bot.handlers.durak import build_durak_router

logger = logging.getLogger(__name__)

WEBHOOK_RESET_RETRIES = 3
WEBHOOK_RESET_BASE_DELAY_SECONDS = 2.0


async def _reset_webhook(bot: Bot) -> None:
    for attempt in range(1, WEBHOOK_RESET_RETRIES + 1):
        try:
            await bot.delete_webhook(drop_pending_updates=True)
            return
        except TelegramNetworkError as exc:
            if attempt == WEBHOOK_RESET_RETRIES:
                logger.warning("Не удалось сбросить webhook после %s попыток: %s", WEBHOOK_RESET_RETRIES, exc)
                return
            delay = WEBHOOK_RESET_BASE_DELAY_SECONDS * attempt
            logger.warning("Ошибка сброса webhook (%s/%s): %s. Повтор через %.1f сек.", attempt, WEBHOOK_RESET_RETRIES, exc, delay)
            await asyncio.sleep(delay)


async def run() -> None:
    """Основной цикл CEER Bot."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stdout,
    )

    settings = load_settings()
    container = await AppContainer.build(settings)

    bot = Bot(
        token=settings.ceer_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    container.bot = bot
    bot_info = await bot.get_me()
    container.bot_username = bot_info.username or ""

    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(build_start_router(container))
    dp.include_router(build_chat_events_router(container))
    dp.include_router(build_game_router(container))
    dp.include_router(build_tictactoe_router(container))
    dp.include_router(build_blackjack_router(container))
    dp.include_router(build_durak_router(container))

    # Web-сервер Mini App (если задан URL туннеля)
    if settings.ceer_web_url:
        from ceer_bot.keyboards.game_menu import set_ttt_web_url
        set_ttt_web_url(settings.ceer_web_url)
        logger.info("TTT Mini App URL: %s", settings.ceer_web_url)

    logger.info("CEER Bot запущен.")
    try:
        await _reset_webhook(bot)
        if settings.ceer_web_url:
            from ceer_bot.web.app import create_web_app
            web_app = create_web_app(container)
            web_config = uvicorn.Config(
                web_app,
                host="0.0.0.0",
                port=settings.ceer_web_port,
                log_level="warning",
            )
            web_server = uvicorn.Server(web_config)
            async with asyncio.TaskGroup() as tg:
                tg.create_task(dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types()))
                tg.create_task(web_server.serve())
        else:
            await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await container.close()
        await bot.session.close()
        logger.info("CEER Bot остановлен.")
