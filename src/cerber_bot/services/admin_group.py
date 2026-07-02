"""Сервис админ-группы.

Хранит привязку Telegram-группы администраторов/гарантов, отправляет туда
уведомления и запросы (диспуты, выводы), создаёт отдельную ветку (forum topic)
для каждого диспута.
"""

from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.exceptions import AiogramError
from aiogram.types import InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from cerber_bot.db.repositories.deals import EscrowDealRepository
from cerber_bot.db.repositories.settings import BotSettingsRepository


logger = logging.getLogger(__name__)

ADMIN_GROUP_CHAT_ID_KEY = "admin_group_chat_id"
ADMIN_GROUP_IS_FORUM_KEY = "admin_group_is_forum"


class AdminGroupService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory
        self._cached_chat_id: int | None = None
        self._cached_is_forum: bool = False
        self._cache_loaded = False

    async def connect_group(self, chat_id: int, *, is_forum: bool) -> None:
        async with self.session_factory() as session:
            repository = BotSettingsRepository(session)
            await repository.set(ADMIN_GROUP_CHAT_ID_KEY, str(chat_id))
            await repository.set(ADMIN_GROUP_IS_FORUM_KEY, "1" if is_forum else "0")
            await session.commit()
        self._cached_chat_id = chat_id
        self._cached_is_forum = is_forum
        self._cache_loaded = True

    async def disconnect_group(self) -> None:
        async with self.session_factory() as session:
            repository = BotSettingsRepository(session)
            await repository.delete(ADMIN_GROUP_CHAT_ID_KEY)
            await repository.delete(ADMIN_GROUP_IS_FORUM_KEY)
            await session.commit()
        self._cached_chat_id = None
        self._cached_is_forum = False
        self._cache_loaded = True

    async def get_group_chat_id(self) -> int | None:
        await self._load_cache()
        return self._cached_chat_id

    async def is_forum_group(self) -> bool:
        await self._load_cache()
        return self._cached_is_forum

    async def _load_cache(self) -> None:
        if self._cache_loaded:
            return
        async with self.session_factory() as session:
            repository = BotSettingsRepository(session)
            raw_chat_id = await repository.get(ADMIN_GROUP_CHAT_ID_KEY)
            raw_is_forum = await repository.get(ADMIN_GROUP_IS_FORUM_KEY)
        self._cached_chat_id = int(raw_chat_id) if raw_chat_id and raw_chat_id.lstrip("-").isdigit() else None
        self._cached_is_forum = raw_is_forum == "1"
        self._cache_loaded = True

    async def send_to_group(
        self,
        bot: Bot,
        text: str,
        *,
        reply_markup: InlineKeyboardMarkup | None = None,
        message_thread_id: int | None = None,
    ) -> bool:
        chat_id = await self.get_group_chat_id()
        if chat_id is None:
            return False
        try:
            await bot.send_message(
                chat_id,
                text,
                parse_mode="HTML",
                reply_markup=reply_markup,
                message_thread_id=message_thread_id,
            )
            return True
        except AiogramError as error:
            logger.warning("Не удалось отправить сообщение в админ-группу %s: %s", chat_id, error)
            return False

    async def ensure_dispute_topic(self, bot: Bot, *, deal_id: int, topic_name: str) -> int | None:
        """Создаёт ветку (forum topic) для диспута и сохраняет её ID на сделке.

        Возвращает message_thread_id или None, если группа не форум/не привязана.
        """
        chat_id = await self.get_group_chat_id()
        if chat_id is None or not await self.is_forum_group():
            return None

        async with self.session_factory() as session:
            deal_repository = EscrowDealRepository(session)
            deal = await deal_repository.get_by_id(deal_id)
            if deal is None:
                return None
            if deal.dispute_topic_id is not None:
                return deal.dispute_topic_id

            try:
                topic = await bot.create_forum_topic(chat_id, name=topic_name)
            except AiogramError as error:
                logger.warning("Не удалось создать ветку диспута в группе %s: %s", chat_id, error)
                return None

            deal.dispute_topic_id = topic.message_thread_id
            await session.commit()
            return topic.message_thread_id

    async def get_dispute_topic_id(self, deal_id: int) -> int | None:
        async with self.session_factory() as session:
            deal_repository = EscrowDealRepository(session)
            deal = await deal_repository.get_by_id(deal_id)
            return deal.dispute_topic_id if deal is not None else None
