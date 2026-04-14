from decimal import Decimal
from pathlib import Path

import pytest
from aiogram.types import User

from cerber_bot.db.repositories.users import UserRepository
from cerber_bot.db.session import create_engine, create_session_factory, init_database
from cerber_bot.services.deals import DealService
from cerber_bot.services.exchange import WalletQuote


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


def build_user(*, telegram_id: int, username: str, first_name: str) -> User:
    return User(
        id=telegram_id,
        is_bot=False,
        first_name=first_name,
        last_name=None,
        username=username,
        language_code="ru",
    )


async def seed_user(session_factory, telegram_user: User, *, balance: Decimal) -> None:
    async with session_factory() as session:
        repository = UserRepository(session)
        user, _ = await repository.get_or_create(
            telegram_id=telegram_user.id,
            username=telegram_user.username,
            first_name=telegram_user.first_name,
            last_name=telegram_user.last_name,
            language_code=telegram_user.language_code,
            is_bot=telegram_user.is_bot,
            balance_currency="USD",
        )
        user.balance = balance
        user.balance_currency = "USD"
        await session.commit()


def build_deal_service(session_factory) -> DealService:
    return DealService(
        session_factory=session_factory,
        exchange_rate_service=StubExchangeRateService(),
        wallet_currency="USD",
        moderator_ids=(900001,),
        withdrawal_min_amount_usdt=Decimal("10.00"),
        withdrawal_networks=("TRC20", "BEP20"),
    )


@pytest.mark.asyncio
async def test_deal_service_locks_funds_and_releases_to_seller_on_success(tmp_path: Path) -> None:
    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'deals-success.db').as_posix()}"
    engine = create_engine(database_url)
    session_factory = create_session_factory(engine)
    await init_database(engine)

    service = build_deal_service(session_factory)
    buyer = build_user(telegram_id=101, username="buyer_one", first_name="Buyer")
    seller = build_user(telegram_id=202, username="seller_one", first_name="Seller")
    await seed_user(session_factory, buyer, balance=Decimal("50.00"))
    await seed_user(session_factory, seller, balance=Decimal("0.00"))

    created = await service.create_deal_request(
        buyer,
        seller_identifier="@seller_one",
        amount=Decimal("20.00"),
        terms="Передать цифровой товар и инструкцию к использованию.",
    )
    accepted = await service.accept_deal(seller.id, created.deal.deal_id)
    relay = await service.record_chat_message(
        seller.id,
        deal_id=created.deal.deal_id,
        content_type="text",
        body="Данные готовы к передаче.",
    )
    completed = await service.confirm_success(buyer.id, created.deal.deal_id)
    dashboard = await service.get_dashboard(buyer.id)

    assert created.deal.status == "pending_acceptance"
    assert accepted.deal.status == "active"
    assert relay.recipient_id == buyer.id
    assert completed.deal.status == "completed"
    assert dashboard.statistics.completed_deals == 1
    assert dashboard.statistics.total_volume == Decimal("20.00")

    async with session_factory() as session:
        repository = UserRepository(session)
        buyer_row = await repository.get_by_telegram_id(buyer.id)
        seller_row = await repository.get_by_telegram_id(seller.id)

    assert buyer_row is not None
    assert seller_row is not None
    assert Decimal(str(buyer_row.balance)) == Decimal("30.00")
    assert Decimal(str(buyer_row.held_balance)) == Decimal("0.00")
    assert Decimal(str(seller_row.balance)) == Decimal("20.00")

    await engine.dispose()


@pytest.mark.asyncio
async def test_deal_service_supports_dispute_and_moderator_refund(tmp_path: Path) -> None:
    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'deals-dispute.db').as_posix()}"
    engine = create_engine(database_url)
    session_factory = create_session_factory(engine)
    await init_database(engine)

    service = build_deal_service(session_factory)
    buyer = build_user(telegram_id=303, username="buyer_two", first_name="Buyer")
    seller = build_user(telegram_id=404, username="seller_two", first_name="Seller")
    await seed_user(session_factory, buyer, balance=Decimal("40.00"))
    await seed_user(session_factory, seller, balance=Decimal("0.00"))

    created = await service.create_deal_request(
        buyer,
        seller_identifier="seller_two",
        amount=Decimal("15.00"),
        terms="Передача аккаунта после подтверждения сделки.",
    )
    await service.accept_deal(seller.id, created.deal.deal_id)
    disputed = await service.open_dispute(buyer.id, created.deal.deal_id)
    resolved = await service.resolve_dispute(900001, created.deal.deal_id, "refund")

    assert disputed.deal.status == "disputed"
    assert resolved.status == "refunded"
    assert resolved.resolution == "refund_buyer"

    async with session_factory() as session:
        repository = UserRepository(session)
        buyer_row = await repository.get_by_telegram_id(buyer.id)
        seller_row = await repository.get_by_telegram_id(seller.id)

    assert buyer_row is not None
    assert seller_row is not None
    assert Decimal(str(buyer_row.balance)) == Decimal("40.00")
    assert Decimal(str(buyer_row.held_balance)) == Decimal("0.00")
    assert Decimal(str(seller_row.balance)) == Decimal("0.00")

    await engine.dispose()


@pytest.mark.asyncio
async def test_deal_service_creates_and_approves_withdrawal_request(tmp_path: Path) -> None:
    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'deals-withdrawal.db').as_posix()}"
    engine = create_engine(database_url)
    session_factory = create_session_factory(engine)
    await init_database(engine)

    service = build_deal_service(session_factory)
    user = build_user(telegram_id=505, username="withdraw_user", first_name="Withdraw")
    await seed_user(session_factory, user, balance=Decimal("100.00"))

    created = await service.create_withdrawal_request(
        user,
        amount_usdt=Decimal("25.00"),
        network="TRC20",
        address="TQ123456789012345678901234567890",
    )
    approved = await service.moderate_withdrawal_request(900001, created.request.request_id, "approve")
    dashboard = await service.get_dashboard(user.id)

    assert created.request.status == "requested"
    assert approved.request.status == "approved"
    assert dashboard.statistics.pending_withdrawals == 0

    async with session_factory() as session:
        repository = UserRepository(session)
        user_row = await repository.get_by_telegram_id(user.id)

    assert user_row is not None
    assert Decimal(str(user_row.balance)) == Decimal("75.00")
    assert Decimal(str(user_row.held_balance)) == Decimal("0.00")

    await engine.dispose()