"""Контейнер зависимостей CEER Bot.

Создаёт подключение к CERBER БД, инициализирует CeerUserService.
Передаётся во все роутеры-фабрики.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aiogram import Bot

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from ceer_bot.config import Settings, load_settings
from ceer_bot.services.users import CeerUserService
from cerber_bot.db.session import create_engine, create_session_factory, ensure_database_parent, init_database


@dataclass(slots=True)
class AppContainer:
    settings: Settings
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    user_service: CeerUserService
    bot: Bot | None = None
    bot_username: str = ""

    @classmethod
    async def build(cls, settings: Settings | None = None) -> "AppContainer":
        """Собирает контейнер: движок, сессию, сервисы."""
        resolved = settings or load_settings()
        ensure_database_parent(resolved.database_url)

        engine = create_engine(resolved.database_url)
        session_factory = create_session_factory(engine)
        # Инициализируем схему БД CERBER (create_all + lightweight migrations)
        await init_database(engine)

        user_service = CeerUserService(
            session_factory=session_factory,
            wallet_currency=resolved.wallet_currency,
        )

        return cls(
            settings=resolved,
            engine=engine,
            session_factory=session_factory,
            user_service=user_service,
        )

    async def close(self) -> None:
        """Освобождает ресурсы контейнера."""
        await self.engine.dispose()
