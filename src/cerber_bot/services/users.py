"""Сервис пользователей.

Регистрация нового пользователя и чтение профиля из БД.
"""

from aiogram.types import User as TelegramUserObject
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from cerber_bot.db.models import TelegramUser
from cerber_bot.db.repositories.users import UserRepository


class UserService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession], default_balance_currency: str = "USD") -> None:
        self.session_factory = session_factory
        self.default_balance_currency = default_balance_currency

    async def register_or_update(self, telegram_user: TelegramUserObject) -> tuple[TelegramUser, bool]:
        async with self.session_factory() as session:
            repository = UserRepository(session)
            user, created = await repository.get_or_create(
                telegram_id=telegram_user.id,
                username=telegram_user.username,
                first_name=telegram_user.first_name,
                last_name=telegram_user.last_name,
                language_code=telegram_user.language_code,
                is_bot=telegram_user.is_bot,
                balance_currency=self.default_balance_currency,
            )
            await session.commit()
            return user, created

    async def get_profile(self, telegram_id: int) -> TelegramUser | None:
        async with self.session_factory() as session:
            repository = UserRepository(session)
            return await repository.get_by_telegram_id(telegram_id)