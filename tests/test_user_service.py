from decimal import Decimal
from pathlib import Path

import pytest
from aiogram.types import User

from cerber_bot.db.session import create_engine, create_session_factory, init_database
from cerber_bot.services.exchange import WalletQuote
from cerber_bot.services.ledger import LedgerInsufficientFundsError
from cerber_bot.services.ledger.types import LedgerSnapshot
from cerber_bot.services.users import UserService


class StubExchangeRateService:
    async def convert(self, amount: Decimal, from_currency: str, to_currency: str) -> Decimal:
        return amount.quantize(Decimal("0.01"))

    async def quote_wallet(self, amount: Decimal, currency: str) -> WalletQuote:
        normalized = amount.quantize(Decimal("0.01"))
        return WalletQuote(
            base_amount=normalized,
            base_currency=currency,
            usdt_amount=normalized,
            rub_amount=(normalized * Decimal("90.00")).quantize(Decimal("0.01")),
            usdt_rub_rate=Decimal("90.00"),
            source="stub",
        )


class MutableStubLedgerService:
    def __init__(self, *, balance_usdt: Decimal) -> None:
        self.balance_usdt = balance_usdt
        self.adjustments: list[dict[str, object]] = []

    async def ensure_user(self, telegram_id: int) -> None:
        return None

    async def get_balance(self, telegram_id: int) -> LedgerSnapshot:
        return LedgerSnapshot(
            available_usdt=self.balance_usdt,
            balance_rub=self.balance_usdt * Decimal("90.00"),
            rate_usdt_rub=Decimal("90.00"),
        )

    async def adjust(
        self,
        telegram_id: int,
        *,
        delta_usdt: Decimal,
        tx_type: str,
        description: str,
        operation_id: str,
    ) -> LedgerSnapshot:
        if self.balance_usdt + delta_usdt < Decimal("0.00"):
            raise LedgerInsufficientFundsError("insufficient funds")
        self.adjustments.append(
            {
                "telegram_id": telegram_id,
                "delta_usdt": delta_usdt,
                "tx_type": tx_type,
                "operation_id": operation_id,
            }
        )
        self.balance_usdt += delta_usdt
        return await self.get_balance(telegram_id)


@pytest.mark.asyncio
async def test_user_service_creates_user_on_first_start(tmp_path: Path) -> None:
    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'test.db').as_posix()}"
    engine = create_engine(database_url)
    session_factory = create_session_factory(engine)
    await init_database(engine)

    service = UserService(session_factory)
    telegram_user = User(
        id=987654321,
        is_bot=False,
        first_name="Ivan",
        last_name="Petrov",
        username="cerber_user",
        language_code="ru",
    )

    profile, created = await service.register_or_update(telegram_user)
    persisted = await service.get_profile(telegram_user.id)

    assert created is True
    assert profile.telegram_id == telegram_user.id
    assert persisted is not None
    assert persisted.username == "cerber_user"
    assert str(persisted.balance) == "0.00"
    assert persisted.balance_currency == "USD"

    await engine.dispose()


@pytest.mark.asyncio
async def test_user_service_adjust_balance_updates_existing_user(tmp_path: Path) -> None:
    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'adjust-balance.db').as_posix()}"
    engine = create_engine(database_url)
    session_factory = create_session_factory(engine)
    await init_database(engine)

    service = UserService(session_factory)
    telegram_user = User(
        id=987654321,
        is_bot=False,
        first_name="Ivan",
        last_name="Petrov",
        username="cerber_user",
        language_code="ru",
    )

    await service.register_or_update(telegram_user)

    result = await service.adjust_balance(telegram_user.id, delta=Decimal("40.00"), admin_id=777)
    assert result.old_balance == Decimal("0.00")
    assert result.new_balance == Decimal("40.00")

    result = await service.adjust_balance(telegram_user.id, delta=Decimal("-15.50"), admin_id=777)
    assert result.old_balance == Decimal("40.00")
    assert result.new_balance == Decimal("24.50")

    persisted = await service.get_profile(telegram_user.id)
    assert persisted is not None
    assert persisted.balance == Decimal("24.50")

    await engine.dispose()


@pytest.mark.asyncio
async def test_user_service_adjust_balance_rejects_negative_result(tmp_path: Path) -> None:
    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'adjust-balance-negative.db').as_posix()}"
    engine = create_engine(database_url)
    session_factory = create_session_factory(engine)
    await init_database(engine)

    service = UserService(session_factory)
    telegram_user = User(
        id=987654321,
        is_bot=False,
        first_name="Ivan",
        last_name="Petrov",
        username="cerber_user",
        language_code="ru",
    )

    await service.register_or_update(telegram_user)

    with pytest.raises(ValueError, match="Баланс не может стать отрицательным"):
        await service.adjust_balance(telegram_user.id, delta=Decimal("-1.00"), admin_id=777)

    await engine.dispose()


@pytest.mark.asyncio
async def test_user_service_core_first_adjust_balance_uses_ledger(tmp_path: Path) -> None:
    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'adjust-balance-core-first.db').as_posix()}"
    engine = create_engine(database_url)
    session_factory = create_session_factory(engine)
    await init_database(engine)

    ledger = MutableStubLedgerService(balance_usdt=Decimal("10.00"))
    service = UserService(
        session_factory,
        ledger_service=ledger,
        exchange_rate_service=StubExchangeRateService(),
    )
    telegram_user = User(
        id=987654321,
        is_bot=False,
        first_name="Ivan",
        last_name="Petrov",
        username="cerber_user",
        language_code="ru",
    )
    await service.register_or_update(telegram_user)

    result = await service.adjust_balance(telegram_user.id, delta=Decimal("5.00"), admin_id=777)
    assert result.old_balance == Decimal("10.00")
    assert result.new_balance == Decimal("15.00")
    assert ledger.balance_usdt == Decimal("15.00")
    assert len(ledger.adjustments) == 1

    persisted = await service.get_profile(telegram_user.id)
    assert persisted is not None
    assert persisted.balance == Decimal("0.00")

    await engine.dispose()
