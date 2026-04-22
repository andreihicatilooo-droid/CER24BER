"""Общие runtime-утилиты для Telegram-ботов CERBER.

Содержит создание bot-session и безопасный сброс webhook перед polling.
"""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.exceptions import TelegramNetworkError


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


def build_bot_session(settings) -> AiohttpSession | None:
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