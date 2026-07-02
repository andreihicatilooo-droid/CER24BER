from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

from aiogram.types import User as TelegramUserObject
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from cerber_bot.db.models import TelegramUser, utcnow
from cerber_bot.db.repositories.users import UserRepository
from cerber_bot.db.repositories.wallet import WalletTransactionRepository
from cerber_bot.services.exchange import ExchangeRateError, ExchangeRateService
from cerber_bot.services.ledger import LedgerInsufficientFundsError, LedgerService


@dataclass(slots=True, frozen=True)
class BalanceAdjustResult:
    old_balance: Decimal
    new_balance: Decimal
    user: TelegramUser


@dataclass(slots=True, frozen=True)
class UserStats:
    total: int
    active_7d: int
    active_24h: int


class UserService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        default_balance_currency: str = "USD",
        ledger_service: LedgerService | None = None,
        exchange_rate_service: ExchangeRateService | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.default_balance_currency = default_balance_currency
        self.ledger_service = ledger_service
        self.exchange_rate_service = exchange_rate_service

    @property
    def is_core_first_billing(self) -> bool:
        return self.ledger_service is not None and self.exchange_rate_service is not None

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

        if self.ledger_service is not None:
            await self.ledger_service.ensure_user(telegram_user.id)

        return user, created

    async def get_profile(self, telegram_id: int) -> TelegramUser | None:
        async with self.session_factory() as session:
            repository = UserRepository(session)
            return await repository.get_by_telegram_id(telegram_id)

    async def change_display_name(self, telegram_id: int, new_name: str) -> TelegramUser:
        """Сменить отображаемое имя аккаунта. Разрешено только один раз.

        При регистрации имя берётся из Telegram; после смены фиксируется
        name_changed_at и повторная смена запрещена.
        """
        normalized = " ".join(new_name.split())
        if len(normalized) < 2 or len(normalized) > 32:
            raise ValueError("Имя должно быть от 2 до 32 символов.")

        async with self.session_factory() as session:
            repository = UserRepository(session)
            user = await repository.get_by_telegram_id(telegram_id)
            if user is None:
                raise ValueError("Пользователь не найден. Отправьте /start.")
            if user.name_changed_at is not None:
                raise ValueError("Имя уже было изменено ранее — сменить его можно только один раз.")

            user.display_name = normalized
            user.name_changed_at = utcnow()
            user.updated_at = user.name_changed_at
            await session.commit()
            return user

    async def find_user(self, identifier: str) -> TelegramUser | None:
        """Найти пользователя по Telegram ID или @username."""
        async with self.session_factory() as session:
            repository = UserRepository(session)
            return await repository.find_by_identifier(identifier)

    async def get_stats(self) -> UserStats:
        now = utcnow()
        async with self.session_factory() as session:
            repository = UserRepository(session)
            total = await repository.count_users()
            active_7d = await repository.count_active_since(now - timedelta(days=7))
            active_24h = await repository.count_active_since(now - timedelta(hours=24))
        return UserStats(total=total, active_7d=active_7d, active_24h=active_24h)

    async def adjust_balance(
        self,
        telegram_id: int,
        *,
        delta: Decimal,
        admin_id: int,
    ) -> BalanceAdjustResult:
        """Изменить баланс пользователя на delta (может быть отрицательным)."""
        if self.is_core_first_billing:
            return await self._adjust_balance_core_first(telegram_id, delta=delta, admin_id=admin_id)
        return await self._adjust_balance_local(telegram_id, delta=delta, admin_id=admin_id)

    async def _adjust_balance_local(
        self,
        telegram_id: int,
        *,
        delta: Decimal,
        admin_id: int,
    ) -> BalanceAdjustResult:
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
            return BalanceAdjustResult(old_balance=old_balance, new_balance=new_balance, user=user)

    async def _adjust_balance_core_first(
        self,
        telegram_id: int,
        *,
        delta: Decimal,
        admin_id: int,
    ) -> BalanceAdjustResult:
        assert self.ledger_service is not None
        assert self.exchange_rate_service is not None

        async with self.session_factory() as session:
            user_repo = UserRepository(session)
            user = await user_repo.get_by_telegram_id(telegram_id)
            if user is None:
                raise ValueError("Пользователь не найден.")
            currency = user.balance_currency or self.default_balance_currency

        await self.ledger_service.ensure_user(telegram_id)
        snapshot = await self.ledger_service.get_balance(telegram_id)
        old_balance = await self.exchange_rate_service.convert(snapshot.available_usdt, "USDT", currency)
        projected = old_balance + delta
        if projected < Decimal("0.00"):
            raise ValueError("Баланс не может стать отрицательным.")

        try:
            delta_usdt = await self.exchange_rate_service.convert(abs(delta), currency, "USDT")
        except ExchangeRateError as error:
            raise ValueError(str(error)) from error
        if delta < Decimal("0.00"):
            delta_usdt = -delta_usdt

        tx_type = "topup" if delta >= Decimal("0.00") else "transfer"
        try:
            updated = await self.ledger_service.adjust(
                telegram_id,
                delta_usdt=delta_usdt,
                tx_type=tx_type,
                description=f"Корректировка администратором {admin_id}",
                operation_id=f"admin:{admin_id}:{uuid4().hex[:12]}",
            )
        except LedgerInsufficientFundsError as error:
            raise ValueError("Баланс не может стать отрицательным.") from error

        new_balance = await self.exchange_rate_service.convert(updated.available_usdt, "USDT", currency)

        async with self.session_factory() as session:
            user_repo = UserRepository(session)
            user = await user_repo.get_by_telegram_id(telegram_id)
            if user is None:
                raise ValueError("Пользователь не найден.")
            user.updated_at = utcnow()
            await session.commit()

        return BalanceAdjustResult(old_balance=old_balance, new_balance=new_balance, user=user)
