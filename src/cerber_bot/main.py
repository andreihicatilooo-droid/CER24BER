"""Точка входа CERBER Telegram Bot.

Создаёт бота, подключает все роутеры, запускает NicePay webhook-сервер
и polling-цикл aiogram.  Запуск: ``python -m cerber_bot``.
"""

import asyncio
import logging
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramNetworkError
from aiogram.fsm.storage.memory import MemoryStorage

from cerber_bot.container import AppContainer
from cerber_bot.handlers.giftapi import build_giftapi_router
from cerber_bot.handlers.menu import build_deals_router, build_menu_router
from cerber_bot.handlers.start import build_start_router
from cerber_bot.handlers.storefront import build_storefront_router
from cerber_bot.log_config import setup_logging
from cerber_bot.nicepay_webhook import NicePayWebhookServer
from cerber_bot.web.app import create_web_app


logger = logging.getLogger(__name__)

WEBHOOK_RESET_RETRIES = 3
WEBHOOK_RESET_BASE_DELAY_SECONDS = 2.0


async def reset_webhook_with_retry(bot: Bot) -> None:
    for attempt in range(1, WEBHOOK_RESET_RETRIES + 1):
        try:
            await bot.delete_webhook(drop_pending_updates=True)
            if attempt > 1:
                logger.info("Telegram webhook reset succeeded on retry %s", attempt)
            return
        except TelegramNetworkError as error:
            if attempt == WEBHOOK_RESET_RETRIES:
                logger.warning(
                    "Failed to reset Telegram webhook after %s attempts: %s. "
                    "Continuing to polling mode; aiogram will keep retrying network requests.",
                    WEBHOOK_RESET_RETRIES,
                    error,
                )
                return

            delay = WEBHOOK_RESET_BASE_DELAY_SECONDS * attempt
            logger.warning(
                "Telegram API is unavailable during webhook reset (%s/%s): %s. Retry in %.1f seconds.",
                attempt,
                WEBHOOK_RESET_RETRIES,
                error,
                delay,
            )
            await asyncio.sleep(delay)


async def run() -> None:
    setup_logging()
    container = await AppContainer.build()

    session = None
    proxy = container.settings.telegram_proxy or None
    custom_api = container.settings.telegram_api_url
    if proxy or (custom_api and custom_api != "https://api.telegram.org"):
        session = AiohttpSession(proxy=proxy)
        if custom_api and custom_api != "https://api.telegram.org":
            session.api = TelegramAPIServer.from_base(custom_api)
            logger.info("Using custom Telegram API URL: %s", custom_api)
        if proxy:
            logger.info("Using Telegram proxy: %s", proxy)

    bot = Bot(
        token=container.settings.bot_token,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    webhook_server = NicePayWebhookServer(container=container, bot=bot)
    dispatcher = Dispatcher(storage=MemoryStorage())
    dispatcher.include_router(build_start_router(container))
    dispatcher.include_router(build_storefront_router(container))
    dispatcher.include_router(build_giftapi_router(container))
    dispatcher.include_router(build_deals_router(container))
    dispatcher.include_router(build_menu_router(container))

    try:
        await reset_webhook_with_retry(bot)
        await webhook_server.start()

        web_server = None
        if container.settings.web_enabled:
            import uvicorn
            web_app = create_web_app(container, bot=bot)
            web_config = uvicorn.Config(
                web_app,
                host=container.settings.web_host,
                port=container.settings.web_port,
                log_level="info",
            )
            web_server = uvicorn.Server(web_config)
            asyncio.create_task(web_server.serve())
            logger.info(
                "Web app started at http://%s:%s",
                container.settings.web_host,
                container.settings.web_port,
            )

        await dispatcher.start_polling(bot, allowed_updates=dispatcher.resolve_used_update_types())
    except TelegramNetworkError as error:
        logger.error(
            "Telegram API is unavailable. Check internet access, firewall, proxy or VPN settings. Details: %s",
            error,
        )
    finally:
        await webhook_server.stop()
        await bot.session.close()
        await container.close()


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user.")