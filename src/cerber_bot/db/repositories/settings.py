"""Репозиторий key-value настроек бота (например, привязка админ-группы)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cerber_bot.db.models import BotSetting, utcnow


class BotSettingsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, key: str) -> str | None:
        result = await self.session.execute(select(BotSetting).where(BotSetting.key == key))
        setting = result.scalar_one_or_none()
        return setting.value if setting is not None else None

    async def set(self, key: str, value: str) -> None:
        result = await self.session.execute(select(BotSetting).where(BotSetting.key == key))
        setting = result.scalar_one_or_none()
        if setting is None:
            self.session.add(BotSetting(key=key, value=value))
        else:
            setting.value = value
            setting.updated_at = utcnow()
        await self.session.flush()

    async def delete(self, key: str) -> None:
        result = await self.session.execute(select(BotSetting).where(BotSetting.key == key))
        setting = result.scalar_one_or_none()
        if setting is not None:
            await self.session.delete(setting)
            await self.session.flush()
