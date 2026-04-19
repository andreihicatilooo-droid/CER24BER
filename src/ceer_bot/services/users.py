"""Сервис пользователей CEER — адаптер над CERBER UserService.

Не дублирует модели и репозитории. Переиспользует
cerber_bot.db.models, cerber_bot.db.repositories.users,
cerber_bot.db.repositories.wallet напрямую.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from aiogram.types import User as TelegramUserObject
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from cerber_bot.db.models import TelegramUser, WalletTransaction, utcnow
from cerber_bot.db.repositories.users import UserRepository
from cerber_bot.db.repositories.wallet import WalletTransactionRepository


class CeerUserServiceError(RuntimeError):
    """Базовое исключение сервиса пользователей CEER."""


class InsufficientBalanceError(CeerUserServiceError):
    """Недостаточно средств для операции."""

    def __init__(self, required: Decimal, available: Decimal) -> None:
        self.required = required
        self.available = available
        super().__init__(f"Нужно {required}, доступно {available}")


@dataclass(slots=True, frozen=True)
class UserProfile:
    telegram_id: int
    username: str | None
    first_name: str | None
    balance: Decimal
    currency: str


class CeerUserService:
    """Оркестрирует регистрацию, профиль и баланс пользователей CEER.

    Баланс хранится исключительно в таблице CERBER telegram_users.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        wallet_currency: str = "USD",
    ) -> None:
        self.session_factory = session_factory
        self.wallet_currency = wallet_currency

    async def register_or_update(self, telegram_user: TelegramUserObject) -> tuple[TelegramUser, bool]:
        """Регистрирует нового или обновляет существующего пользователя."""
        async with self.session_factory() as session:
            repo = UserRepository(session)
            user, created = await repo.get_or_create(
                telegram_id=telegram_user.id,
                username=telegram_user.username,
                first_name=telegram_user.first_name,
                last_name=telegram_user.last_name,
                language_code=telegram_user.language_code,
                is_bot=telegram_user.is_bot,
                balance_currency=self.wallet_currency,
            )
            await session.commit()
            return user, created

    async def get_profile(self, telegram_id: int) -> UserProfile | None:
        """Возвращает профиль пользователя или None если не найден."""
        async with self.session_factory() as session:
            repo = UserRepository(session)
            user = await repo.get_by_telegram_id(telegram_id)
            if user is None:
                return None
            return UserProfile(
                telegram_id=user.telegram_id,
                username=user.username,
                first_name=user.first_name,
                balance=user.balance,
                currency=user.balance_currency,
            )

    async def debit(
        self,
        telegram_id: int,
        amount: Decimal,
        description: str,
        reference: str | None = None,
    ) -> Decimal:
        """Списывает amount с баланса пользователя.

        Возвращает новый баланс. Поднимает InsufficientBalanceError если
        средств недостаточно. Операция атомарна внутри одной сессии.
        """
        async with self.session_factory() as session:
            user_repo = UserRepository(session)
            user = await user_repo.get_by_telegram_id(telegram_id, with_lock=True)
            if user is None:
                raise CeerUserServiceError(f"Пользователь {telegram_id} не найден")
            if user.balance < amount:
                raise InsufficientBalanceError(required=amount, available=user.balance)

            user.balance -= amount
            user.updated_at = utcnow()

            wallet_repo = WalletTransactionRepository(session)
            await wallet_repo.add(
                telegram_id=telegram_id,
                transaction_type="game_debit",
                amount=-amount,
                currency=user.balance_currency,
                description=description,
                reference=reference,
            )
            await session.commit()
            return user.balance

    async def credit(
        self,
        telegram_id: int,
        amount: Decimal,
        description: str,
        reference: str | None = None,
    ) -> Decimal:
        """Зачисляет amount на баланс пользователя.

        Возвращает новый баланс.
        """
        async with self.session_factory() as session:
            user_repo = UserRepository(session)
            user = await user_repo.get_by_telegram_id(telegram_id, with_lock=True)
            if user is None:
                raise CeerUserServiceError(f"Пользователь {telegram_id} не найден")

            user.balance += amount
            user.updated_at = utcnow()

            wallet_repo = WalletTransactionRepository(session)
            await wallet_repo.add(
                telegram_id=telegram_id,
                transaction_type="game_credit",
                amount=amount,
                currency=user.balance_currency,
                description=description,
                reference=reference,
            )
            await session.commit()
            return user.balance
