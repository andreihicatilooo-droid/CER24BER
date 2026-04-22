from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from cerber_bot.db.repositories.tgaccounts import TgAccountRepository
from cerber_bot.db.repositories.users import UserRepository
from cerber_bot.db.repositories.wallet import WalletTransactionRepository
from cerber_bot.db.session import create_engine, create_session_factory, init_database
from cerber_bot.integrations.getmytg import GetMyTGError
from cerber_bot.services.tgaccounts import TgAccountService, TgAccountServiceError


class StubGetMyTGClient:
    def __init__(self, *, fail_create: bool = False) -> None:
        self.is_configured = True
        self.fail_create = fail_create

    async def list_countries(self, *, auth: bool = False, sort=None, page=None, page_size=None, country_codes=None):
        return {"items": []}

    async def get_country(self, country_code: str):
        return {
            "data": {
                "country_code": country_code.upper(),
                "emoji": "🇷🇺",
                "display_name": {"ru": "Россия", "en": "Russia"},
                "price": {"amount": "5.00", "currency_code": "USD"},
                "available": True,
            }
        }

    async def create_purchase(self, country_code: str):
        if self.fail_create:
            raise GetMyTGError("create failed")
        return {
            "data": {
                "purchase": {
                    "id": 321,
                    "country_code": country_code.upper(),
                    "phone_number": "+79990001122",
                    "status": "PENDING",
                    "price": {"amount": "5.00", "currency_code": "USD"},
                    "purchase_type": "SINGLE",
                }
            }
        }

    async def request_code(self, purchase_id: int, callback_url: str | None = None):
        return {"data": {"purchase": {"id": purchase_id, "status": "SUCCESS"}}}

    async def refund_purchase(self, purchase_id: int):
        return {"data": {"purchase": {"id": purchase_id, "status": "REFUND"}}}


@pytest.mark.asyncio
async def test_tgaccount_service_buy_account_deducts_balance_and_saves_purchase(tmp_path: Path) -> None:
    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'tgaccounts-service.db').as_posix()}"
    engine = create_engine(database_url)
    session_factory = create_session_factory(engine)
    await init_database(engine)

    async with session_factory() as session:
        users = UserRepository(session)
        user, _ = await users.get_or_create(
            telegram_id=1001,
            username="buyer",
            first_name="Buyer",
            last_name=None,
            language_code="ru",
            is_bot=False,
            balance_currency="USD",
        )
        user.balance = Decimal("20.00")
        await session.commit()

    service = TgAccountService(StubGetMyTGClient(), session_factory)
    purchase = await service.buy_account(1001, "ru")

    assert purchase.getmytg_purchase_id == 321
    assert purchase.country_code == "RU"
    assert str(purchase.amount) == "5.00"

    async with session_factory() as session:
        users = UserRepository(session)
        wallet = WalletTransactionRepository(session)
        tg_repo = TgAccountRepository(session)
        user = await users.get_by_telegram_id(1001)
        transactions = await wallet.list_recent(1001, limit=5)
        purchases = await tg_repo.list_by_telegram_id(1001)

    assert user is not None
    assert str(user.balance) == "15.00"
    assert any(tx.transaction_type == "tg_account_purchase" and str(tx.amount) == "-5.00" for tx in transactions)
    assert len(purchases) == 1

    await engine.dispose()


@pytest.mark.asyncio
async def test_tgaccount_service_buy_account_rolls_back_balance_on_client_error(tmp_path: Path) -> None:
    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'tgaccounts-service-rollback.db').as_posix()}"
    engine = create_engine(database_url)
    session_factory = create_session_factory(engine)
    await init_database(engine)

    async with session_factory() as session:
        users = UserRepository(session)
        user, _ = await users.get_or_create(
            telegram_id=2002,
            username="buyer2",
            first_name="Buyer2",
            last_name=None,
            language_code="ru",
            is_bot=False,
            balance_currency="USD",
        )
        user.balance = Decimal("20.00")
        await session.commit()

    service = TgAccountService(StubGetMyTGClient(fail_create=True), session_factory)

    with pytest.raises(TgAccountServiceError):
        await service.buy_account(2002, "ru")

    async with session_factory() as session:
        users = UserRepository(session)
        wallet = WalletTransactionRepository(session)
        tg_repo = TgAccountRepository(session)
        user = await users.get_by_telegram_id(2002)
        transactions = await wallet.list_recent(2002, limit=5)
        purchases = await tg_repo.list_by_telegram_id(2002)

    assert user is not None
    assert str(user.balance) == "20.00"
    assert len([tx for tx in transactions if tx.transaction_type == "tg_account_purchase"]) == 0
    assert purchases == []

    await engine.dispose()
