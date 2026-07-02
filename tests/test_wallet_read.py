from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from cerber_bot.db.repositories.users import UserRepository
from cerber_bot.db.session import create_engine, create_session_factory, init_database
from cerber_bot.integrations.cerber_core import CerberCoreClient
from cerber_bot.services.ledger import LedgerService
from cerber_bot.services.wallet_read import WalletReadService
from tests.test_cerber_core_client import SECRET_KEY_B64, encrypt_payload


class StubExchangeRateService:
    async def convert(self, amount: Decimal, from_currency: str, to_currency: str) -> Decimal:
        source = from_currency.upper()
        target = to_currency.upper()
        value = Decimal(str(amount))
        if source == target:
            return value
        if source == "USDT" and target == "USD":
            return value
        if source == "USD" and target == "USDT":
            return value
        if source == "USDT" and target == "RUB":
            return value * Decimal("90")
        if source == "RUB" and target == "USDT":
            return value / Decimal("90")
        return value

    async def quote_wallet(self, amount: Decimal, currency: str):
        from cerber_bot.services.exchange import WalletQuote

        converted = await self.convert(amount, currency, "USDT")
        rub = await self.convert(amount, currency, "RUB")
        return WalletQuote(
            base_amount=Decimal(str(amount)),
            base_currency=currency.upper(),
            usdt_amount=converted,
            rub_amount=rub,
            usdt_rub_rate=Decimal("90"),
            source="stub",
        )


@pytest.mark.asyncio
async def test_wallet_read_core_mode_uses_core_balance_and_escrow_held(tmp_path: Path) -> None:
    db_path = tmp_path / "wallet-read-core.db"
    engine = create_engine(f"sqlite+aiosqlite:///{db_path.as_posix()}")
    session_factory = create_session_factory(engine)
    await init_database(engine)

    async with session_factory() as session:
        user_repo = UserRepository(session)
        buyer, _ = await user_repo.get_or_create(
            telegram_id=1001,
            username="buyer",
            first_name="Buyer",
            last_name=None,
            language_code="ru",
            is_bot=False,
            balance_currency="USD",
        )
        seller, _ = await user_repo.get_or_create(
            telegram_id=1002,
            username="seller",
            first_name="Seller",
            last_name=None,
            language_code="ru",
            is_bot=False,
            balance_currency="USD",
        )
        from cerber_bot.db.repositories.deals import EscrowDealRepository

        deal_repo = EscrowDealRepository(session)
        await deal_repo.create(
            buyer_telegram_id=buyer.telegram_id,
            seller_telegram_id=seller.telegram_id,
            status="active",
            amount=Decimal("25.00"),
            currency="USD",
            terms="Test escrow terms long enough",
        )
        await session.commit()

    captured: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request.url.path)
        if request.url.path == "/api/v1/user/add":
            return httpx.Response(status_code=200, json={"data": encrypt_payload({"user_hash": "abc"})})
        if request.url.path == "/api/v1/balance":
            return httpx.Response(
                status_code=200,
                json={
                    "data": encrypt_payload(
                        {
                            "balance_usdt": 100.0,
                            "balance_rub": 9000.0,
                            "rate_usdt_rub": 90.0,
                        }
                    )
                },
            )
        if request.url.path == "/api/v1/balance/history":
            return httpx.Response(status_code=200, json={"data": encrypt_payload([])})
        raise AssertionError(f"Unexpected path: {request.url.path}")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        core_client = CerberCoreClient(
            base_url="https://core.example",
            http_client=http_client,
            api_key="api-key-1",
            secret_key=SECRET_KEY_B64,
        )
        ledger = LedgerService.from_client(core_client)
        wallet_read = WalletReadService(
            session_factory=session_factory,
            exchange_rate_service=StubExchangeRateService(),
            wallet_currency="USD",
            ledger_service=ledger,
        )
        snapshot = await wallet_read.get_snapshot(1001, limit=5)

    assert "/api/v1/user/add" in captured
    assert "/api/v1/balance" in captured
    assert "/api/v1/balance/history" in captured
    assert snapshot.balance == pytest.approx(Decimal("100"))
    assert snapshot.held_balance == pytest.approx(Decimal("25"))
    assert snapshot.total_balance == pytest.approx(Decimal("125"))
    assert snapshot.currency == "USD"


@pytest.mark.asyncio
async def test_wallet_read_local_mode_uses_user_balance(tmp_path: Path) -> None:
    db_path = tmp_path / "wallet-read-local.db"
    engine = create_engine(f"sqlite+aiosqlite:///{db_path.as_posix()}")
    session_factory = create_session_factory(engine)
    await init_database(engine)

    async with session_factory() as session:
        user_repo = UserRepository(session)
        user, _ = await user_repo.get_or_create(
            telegram_id=2002,
            username="local",
            first_name="Local",
            last_name=None,
            language_code="ru",
            is_bot=False,
            balance_currency="USD",
        )
        user.balance = Decimal("50.00")
        user.held_balance = Decimal("10.00")
        await session.commit()

    wallet_read = WalletReadService(
        session_factory=session_factory,
        exchange_rate_service=StubExchangeRateService(),
        wallet_currency="USD",
        ledger_service=None,
    )
    snapshot = await wallet_read.get_snapshot(2002)

    assert snapshot.balance == pytest.approx(Decimal("50"))
    assert snapshot.held_balance == pytest.approx(Decimal("10"))
    assert snapshot.total_balance == pytest.approx(Decimal("60"))
