"""Точка входа CERBER Telegram Bot.

Создаёт основного бота и (опционально) административного бота,
подключает все роутеры, запускает NicePay webhook-сервер
и polling-циклы aiogram.  Запуск: ``python -m cerber_bot``.
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
from cerber_bot.handlers.admin import build_admin_router
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


def _build_bot_session(settings) -> AiohttpSession | None:
    """Создаёт общую aiohttp-сессию для bot-инстансов (proxy / custom API)."""
    proxy = settings.telegram_proxy or None
    custom_api = settings.telegram_api_url
    if proxy or (custom_api and custom_api != "https://api.telegram.org"):
        session = AiohttpSession(proxy=proxy)
        if custom_api and custom_api != "https://api.telegram.org":
            session.api = TelegramAPIServer.from_base(custom_api)
            logger.info("Using custom Telegram API URL: %s", custom_api)
        if proxy:
            logger.info("Using Telegram proxy: %s", proxy)
        return session
    return None


async def run() -> None:
    setup_logging()
    container = await AppContainer.build()

    session = _build_bot_session(container.settings)

    bot = Bot(
        token=container.settings.bot_token,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    container.user_bot = bot

    webhook_server = NicePayWebhookServer(container=container, bot=bot)
    dispatcher = Dispatcher(storage=MemoryStorage())
    dispatcher.include_router(build_start_router(container))
    dispatcher.include_router(build_storefront_router(container))
    dispatcher.include_router(build_giftapi_router(container))
    dispatcher.include_router(build_deals_router(container))
    dispatcher.include_router(build_menu_router(container))

    # ── Админ-бот (опциональный) ─────────────────────────────
    admin_bot: Bot | None = None
    admin_dispatcher: Dispatcher | None = None
    if container.settings.admin_bot_token:
        admin_session = _build_bot_session(container.settings) if session is not None else None
        admin_bot = Bot(
            token=container.settings.admin_bot_token,
            session=admin_session,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )
        container.admin_bot = admin_bot
        admin_dispatcher = Dispatcher(storage=MemoryStorage())
        admin_dispatcher.include_router(build_admin_router(container))
        logger.info("Admin bot configured and will start polling.")

    try:
        await reset_webhook_with_retry(bot)
        if admin_bot is not None:
            await reset_webhook_with_retry(admin_bot)
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
            # Логируем URL для NicePay webhook
            base_url = (container.settings.web_base_url or "").rstrip("/")
            if base_url:
                logger.info("NicePay webhook URL: %s/webhooks/nicepay", base_url)
            else:
                logger.warning(
                    "WEB_BASE_URL не задан — NicePay webhook URL неизвестен. "
                    "Запустите лаунчер (Cloudflare Tunnel задаёт его автоматически)."
                )

        # Запускаем оба polling-цикла параллельно
        polling_tasks: list[asyncio.Task] = []
        polling_tasks.append(
            asyncio.create_task(
                dispatcher.start_polling(bot, allowed_updates=dispatcher.resolve_used_update_types()),
                name="user_bot_polling",
            )
        )
        if admin_bot is not None and admin_dispatcher is not None:
            polling_tasks.append(
                asyncio.create_task(
                    admin_dispatcher.start_polling(admin_bot, allowed_updates=admin_dispatcher.resolve_used_update_types()),
                    name="admin_bot_polling",
                )
            )

        done, pending = await asyncio.wait(polling_tasks, return_when=asyncio.FIRST_EXCEPTION)
        for task in done:
            if task.exception() is not None:
                raise task.exception()  # type: ignore[misc]
    except TelegramNetworkError as error:
        logger.error(
            "Telegram API is unavailable. Check internet access, firewall, proxy or VPN settings. Details: %s",
            error,
        )
    finally:
        await webhook_server.stop()
        await bot.session.close()
        if admin_bot is not None:
            await admin_bot.session.close()
        await container.close()


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user.")