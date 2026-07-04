"""Точка входа CERBER Telegram Bot.

Создаёт основного бота и (опционально) административного бота,
подключает все роутеры, запускает web-приложение FastAPI
и polling-циклы aiogram. Запуск: ``python -m cerber_bot``.
"""

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
from cerber_bot.handlers.giftapi import build_giftapi_router
from cerber_bot.handlers.inline import build_inline_router
from cerber_bot.handlers.menu import build_deals_router, build_menu_router
from cerber_bot.handlers.moderation import build_moderation_router
from CRP.bot import build_crp_router
from cerber_bot.handlers.start import build_start_router
from cerber_bot.handlers.storefront import build_storefront_router
from cerber_bot.handlers.tgaccounts import build_tgaccounts_router
from cerber_bot.log_config import setup_logging
from cerber_bot.web.app import create_web_app


logger = logging.getLogger(__name__)


async def run() -> None:
    setup_logging()
    container = await AppContainer.build()

    session = build_bot_session(container.settings)

    bot = Bot(
        token=container.settings.bot_token,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    dispatcher = Dispatcher(storage=MemoryStorage())
    dispatcher.include_router(build_start_router(container))
    dispatcher.include_router(build_moderation_router(container))
    dispatcher.include_router(build_storefront_router(container))
    dispatcher.include_router(build_tgaccounts_router(container))
    dispatcher.include_router(build_giftapi_router(container))
    dispatcher.include_router(build_crp_router(container))
    dispatcher.include_router(build_deals_router(container))
    dispatcher.include_router(build_menu_router(container))

    try:
        await reset_webhook_with_retry(bot)

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

        asyncio.create_task(run_auto_release_loop(container, bot))

        await dispatcher.start_polling(bot, allowed_updates=dispatcher.resolve_used_update_types())
    except TelegramNetworkError as error:
        logger.error(
            "Telegram API is unavailable. Check internet access, firewall, proxy or VPN settings. Details: %s",
            error,
        )
    finally:
        await bot.session.close()
        await container.close()


async def run_auto_release_loop(container: AppContainer, bot: Bot, *, interval_seconds: int = 1800) -> None:
    """Периодически закрывает сделки, где товар выдан более 24 часов назад."""
    from aiogram.exceptions import AiogramError

    from cerber_bot.texts import DEAL_HANDLER_TEXT

    while True:
        try:
            results = await container.deal_service.auto_release_delivered()
            for result in results:
                text = DEAL_HANDLER_TEXT.AUTO_RELEASE_NOTIFICATION.format(deal_id=result.deal_id)
                for telegram_id in (result.buyer_telegram_id, result.seller_telegram_id):
                    try:
                        await bot.send_message(telegram_id, text)
                    except AiogramError:
                        pass
        except Exception:  # noqa: BLE001 - фоновая задача не должна падать
            logger.exception("Auto-release loop iteration failed")
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user.")