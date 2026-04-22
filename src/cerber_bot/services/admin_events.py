"""Outbox-сервис уведомлений для отдельного CERBER Admin."""

from __future__ import annotations

import json
import logging

from aiogram import Bot
from aiogram.exceptions import AiogramError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from cerber_bot.db.repositories.admin_events import AdminEventRepository
from cerber_bot.keyboards.admin import (
    build_admin_deal_keyboard,
    build_admin_deal_readonly_keyboard,
    build_admin_home_keyboard,
    build_withdrawals_list_keyboard,
)


logger = logging.getLogger(__name__)


class AdminEventService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession], *, moderator_ids: tuple[int, ...]) -> None:
        self.session_factory = session_factory
        self.moderator_ids = moderator_ids

    async def enqueue_deal_alert(self, *, text: str, deal_id: int, disputed: bool) -> None:
        payload = json.dumps(
            {
                "text": text,
                "markup": "deal_disputed" if disputed else "deal_readonly",
                "deal_id": deal_id,
            },
            ensure_ascii=False,
        )
        await self._enqueue(event_type="deal_alert", payload=payload)

    async def enqueue_withdrawal_alert(self, *, text: str, request_id: int) -> None:
        payload = json.dumps(
            {
                "text": text,
                "markup": "withdrawal",
                "request_id": request_id,
            },
            ensure_ascii=False,
        )
        await self._enqueue(event_type="withdrawal_alert", payload=payload)

    async def _enqueue(self, *, event_type: str, payload: str) -> None:
        async with self.session_factory() as session:
            repository = AdminEventRepository(session)
            await repository.create_pending(event_type=event_type, payload=payload)
            await session.commit()

    async def deliver_pending(self, bot: Bot, *, limit: int = 20) -> int:
        async with self.session_factory() as session:
            repository = AdminEventRepository(session)
            events = await repository.list_pending(limit=limit)
            delivered = 0

            for event in events:
                sent_count, last_error = await self._deliver_event(bot, event.payload)
                if sent_count > 0 or not self.moderator_ids:
                    await repository.mark_delivered(event)
                    delivered += 1
                else:
                    await repository.mark_retry(event, error=last_error)
                await session.commit()

            return delivered

    async def _deliver_event(self, bot: Bot, payload_json: str) -> tuple[int, str | None]:
        payload = json.loads(payload_json)
        text = str(payload.get("text") or "")
        markup = self._build_reply_markup(payload)

        sent_count = 0
        last_error: str | None = None
        for moderator_id in self.moderator_ids:
            try:
                await bot.send_message(moderator_id, text, parse_mode="HTML", reply_markup=markup)
                sent_count += 1
            except AiogramError as error:
                last_error = str(error)
                logger.warning("Failed to deliver admin event to moderator %s: %s", moderator_id, error)

        return sent_count, last_error

    def _build_reply_markup(self, payload: dict[str, object]):
        markup = str(payload.get("markup") or "home")
        if markup == "deal_disputed":
            return build_admin_deal_keyboard(int(payload.get("deal_id") or 0))
        if markup == "deal_readonly":
            return build_admin_deal_readonly_keyboard(int(payload.get("deal_id") or 0))
        if markup == "withdrawal":
            return build_withdrawals_list_keyboard([int(payload.get("request_id") or 0)])
        return build_admin_home_keyboard()