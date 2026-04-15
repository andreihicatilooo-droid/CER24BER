"""Сервис пользователей.

Регистрация нового пользователя и чтение профиля из БД.
"""

from decimal import Decimal

from aiogram.types import User as TelegramUserObject
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from cerber_bot.db.models import TelegramUser, utcnow
from cerber_bot.db.repositories.users import UserRepository
from cerber_bot.db.repositories.wallet import WalletTransactionRepository


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

    async def find_user(self, identifier: str) -> TelegramUser | None:
        """Найти пользователя по Telegram ID или @username."""
        async with self.session_factory() as session:
            repository = UserRepository(session)
            return await repository.find_by_identifier(identifier)

    async def adjust_balance(
        self,
        telegram_id: int,
        *,
        delta: Decimal,
        admin_id: int,
    ) -> tuple[Decimal, TelegramUser]:
        """Изменить баланс пользователя на delta (может быть отрицательным).

        Возвращает (старый_баланс, обновлённый_пользователь).
        Raises ValueError если баланс уйдёт в минус.
        """
        async with self.session_factory() as session:
            user_repo = UserRepository(session)
            wallet_repo = WalletTransactionRepository(session)

            user = await user_repo.get_by_telegram_id(telegram_id)
            if user is None:
                raise ValueError("Пользователь не найден.")

            old_balance = Decimal(str(user.balance))
            new_balance = old_balance + delta
            if new_balance < Decimal("0.00"):
                raise ValueError("Баланс не может стать отрицательным.")

            currency = user.balance_currency or self.default_balance_currency
            user.balance = new_balance
            user.updated_at = utcnow()

            transaction_type = "admin_topup" if delta >= 0 else "admin_deduct"
            await wallet_repo.add(
                telegram_id=telegram_id,
                transaction_type=transaction_type,
                amount=delta,
                currency=currency,
                description=f"Корректировка администратором {admin_id}",
                reference=f"admin:{admin_id}",
            )
            await session.commit()
            return old_balance, user