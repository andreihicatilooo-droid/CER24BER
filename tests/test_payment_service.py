from decimal import Decimal
from pathlib import Path
from datetime import datetime, timezone

import pytest
from aiogram.types import User

from cerber_bot.integrations.nicepay import NicePayCreatedPayment, NicePayWebhookNotification
from cerber_bot.db.repositories.payments import WalletPaymentRepository
from cerber_bot.db.repositories.users import UserRepository
from cerber_bot.db.repositories.wallet import WalletTransactionRepository
from cerber_bot.db.session import create_engine, create_session_factory, init_database
from cerber_bot.services.exchange import WalletQuote
from cerber_bot.services.payments import PaymentService


class StubNicePayClient:
    def __init__(self) -> None:
        self.merchant_id = "merchant-1"
        self.secret = "secret-1"
        self.created_payments: list[tuple[str, int, str, str | None]] = []

    @property
    def is_configured(self) -> bool:
        return True

    def ensure_configured(self) -> None:
        return None

    async def create_payment(
        self,
        *,
        order_id: str,
        account: str,
        amount_minor: int,
        currency: str,
        description: str | None = None,
        method: str | None = None,
        success_url: str | None = None,
        fail_url: str | None = None,
    ) -> NicePayCreatedPayment:
        self.created_payments.append((order_id, amount_minor, currency, method))
        return NicePayCreatedPayment(
            payment_id="nicepay-payment-1",
            amount_minor=amount_minor,
            currency=currency,
            link="https://nicepay.io/pay/example",
            expires_at=datetime(2026, 4, 7, 18, 0, tzinfo=timezone.utc),
        )

    def parse_webhook(self, parameters) -> NicePayWebhookNotification:
        return NicePayWebhookNotification(
            result=str(parameters["result"]),
            payment_id=str(parameters["payment_id"]),
            merchant_id=str(parameters["merchant_id"]),
            order_id=str(parameters["order_id"]),
            amount_minor=int(str(parameters["amount"])),
            amount_currency=str(parameters["amount_currency"]),
            profit_minor=None,
            profit_currency=None,
            method=str(parameters.get("method")) if parameters.get("method") else None,
            signature="valid-hash",
        )


class StubExchangeRateService:
    async def convert(self, amount: Decimal, from_currency: str, to_currency: str) -> Decimal:
        if from_currency == to_currency:
            return amount.quantize(Decimal("0.01"))
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


def build_payment_service(session_factory) -> PaymentService:
    return PaymentService(
        session_factory=session_factory,
        nicepay_client=StubNicePayClient(),
        exchange_rate_service=StubExchangeRateService(),
        wallet_currency="USD",
        payment_currency="USD",
        title="CERBER wallet top-up",
        description="Top up your wallet.",
        min_amount=Decimal("10.00"),
        max_amount=Decimal("500.00"),
        success_url="https://example.com/success",
        fail_url="https://example.com/fail",
        method="paypal_usd",
    )


def build_user() -> User:
    return User(
        id=555001,
        is_bot=False,
        first_name="Test",
        last_name="Buyer",
        username="cerber_payment_user",
        language_code="ru",
    )


@pytest.mark.asyncio
async def test_payment_service_creates_link_and_completes_success_callback(tmp_path: Path) -> None:
    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'payments.db').as_posix()}"
    engine = create_engine(database_url)
    session_factory = create_session_factory(engine)
    await init_database(engine)

    service = build_payment_service(session_factory)
    telegram_user = build_user()

    payment_link = await service.create_top_up_link(telegram_user, Decimal("25.00"))
    callback_result = await service.process_callback(
        {
            "result": "success",
            "payment_id": payment_link.payment_id,
            "merchant_id": "merchant-1",
            "order_id": payment_link.payload,
            "amount": str(payment_link.amount_minor_units),
            "amount_currency": payment_link.currency,
            "method": "paypal_usd",
            "hash": "valid-hash",
        }
    )

    assert payment_link.amount == Decimal("25.00")
    assert payment_link.estimated_wallet_amount == Decimal("25.00")
    assert payment_link.amount_minor_units == 2500
    assert callback_result.amount == Decimal("25.00")
    assert callback_result.credited_amount == Decimal("25.00")
    assert callback_result.credited_currency == "USD"
    assert callback_result.balance_after == Decimal("25.00")

    async with session_factory() as session:
        user = await UserRepository(session).get_by_telegram_id(telegram_user.id)
        transactions = await WalletTransactionRepository(session).list_recent(telegram_user.id, limit=10)
        payment = await WalletPaymentRepository(session).get_by_payload(payment_link.payload)

    assert user is not None
    assert Decimal(str(user.balance)) == Decimal("25.00")
    assert len(transactions) == 1
    assert transactions[0].transaction_type == "top_up"
    assert payment is not None
    assert payment.status == "paid"
    assert payment.provider_payment_charge_id == "nicepay-payment-1"
    assert payment.telegram_payment_charge_id == "paypal_usd"

    await engine.dispose()


@pytest.mark.asyncio
async def test_payment_service_is_idempotent_on_duplicate_success_callback(tmp_path: Path) -> None:
    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'payments-idempotent.db').as_posix()}"
    engine = create_engine(database_url)
    session_factory = create_session_factory(engine)
    await init_database(engine)

    service = build_payment_service(session_factory)
    telegram_user = build_user()
    payment_link = await service.create_top_up_link(telegram_user, Decimal("10.00"))

    callback_payload = {
        "result": "success",
        "payment_id": payment_link.payment_id,
        "merchant_id": "merchant-1",
        "order_id": payment_link.payload,
        "amount": str(payment_link.amount_minor_units),
        "amount_currency": payment_link.currency,
        "method": "paypal_usd",
        "hash": "valid-hash",
    }

    first = await service.process_callback(callback_payload)
    second = await service.process_callback(callback_payload)

    assert first.balance_after == Decimal("10.00")
    assert second.balance_after == Decimal("10.00")

    async with session_factory() as session:
        user = await UserRepository(session).get_by_telegram_id(telegram_user.id)
        transactions = await WalletTransactionRepository(session).list_recent(telegram_user.id, limit=10)

    assert user is not None
    assert Decimal(str(user.balance)) == Decimal("10.00")
    assert len(transactions) == 1

    await engine.dispose()


@pytest.mark.asyncio
async def test_payment_service_marks_error_callback_without_credit(tmp_path: Path) -> None:
    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'payments-error.db').as_posix()}"
    engine = create_engine(database_url)
    session_factory = create_session_factory(engine)
    await init_database(engine)

    service = build_payment_service(session_factory)
    telegram_user = build_user()
    payment_link = await service.create_top_up_link(telegram_user, Decimal("15.00"))

    callback_result = await service.process_callback(
        {
            "result": "error",
            "payment_id": payment_link.payment_id,
            "merchant_id": "merchant-1",
            "order_id": payment_link.payload,
            "amount": str(payment_link.amount_minor_units),
            "amount_currency": payment_link.currency,
            "method": "paypal_usd",
            "hash": "valid-hash",
        }
    )

    assert callback_result.result == "error"
    assert callback_result.balance_after is None

    async with session_factory() as session:
        user = await UserRepository(session).get_by_telegram_id(telegram_user.id)
        transactions = await WalletTransactionRepository(session).list_recent(telegram_user.id, limit=10)
        payment = await WalletPaymentRepository(session).get_by_payload(payment_link.payload)

    assert user is not None
    assert Decimal(str(user.balance)) == Decimal("0.00")
    assert len(transactions) == 0
    assert payment is not None
    assert payment.status == "error"

    await engine.dispose()
