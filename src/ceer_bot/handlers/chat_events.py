"""Обработчик событий чата: добавление бота в группу."""

from __future__ import annotations

import logging

from aiogram import Router
from aiogram.filters import IS_NOT_MEMBER, ChatMemberUpdatedFilter
from aiogram.types import ChatMemberUpdated

from ceer_bot.container import AppContainer
from ceer_bot.texts import CHAT_EVENTS_TEXT

logger = logging.getLogger(__name__)


def build_chat_events_router(container: AppContainer) -> Router:
    router = Router(name="ceer_chat_events")

    @router.my_chat_member(ChatMemberUpdatedFilter(IS_NOT_MEMBER >> ~IS_NOT_MEMBER))
    async def bot_added_to_chat(event: ChatMemberUpdated) -> None:
        """Бот добавлен в чат — приветствие."""
        try:
            await event.answer(
                CHAT_EVENTS_TEXT.HELLO,
                parse_mode="HTML",
            )
        except Exception as exc:
            logger.warning("Не удалось отправить приветствие в чат %s: %s", event.chat.id, exc)

    return router
