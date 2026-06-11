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
from cerber_bot.integrations.cerber_core import CerberCoreTopupSession
from cerber_bot.services.exchange import WalletQuote
from cerber_bot.services.payments import PaymentService
from cerber_bot.services.ledger.types import LedgerSnapshot


class StubLedgerService:
    def __init__(self, *, balance_usdt: Decimal | None = None) -> None:
        self.balance_usdt = balance_usdt or Decimal("0")
        self.balance_reads: list[int] = []

    async def get_balance(self, telegram_id: int) -> LedgerSnapshot:
        self.balance_reads.append(telegram_id)
        return LedgerSnapshot(
            available_usdt=self.balance_usdt,
            balance_rub=self.balance_usdt * Decimal("90"),
            rate_usdt_rub=Decimal("90"),
        )

    async def ensure_user(self, telegram_id: int) -> None:
        return None


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


class StubCerberCoreClient:
    def __init__(self) -> None:
        self.created_sessions: list[tuple[int, Decimal, str]] = []
        self.confirmed_sessions: list[str] = []
        self.session_id = "11111111-1111-1111-1111-111111111111"

    async def create_topup_session(self, *, telegram_id: int, amount_usdt: Decimal, method_code: str) -> CerberCoreTopupSession:
        self.created_sessions.append((telegram_id, amount_usdt, method_code))
        return CerberCoreTopupSession(
            id=self.session_id,
            service_id="svc-1",
            user_hash="hash-1",
            method_id="method-1",
            amount_usdt=amount_usdt,
            amount_rub=amount_usdt * Decimal("90.00"),
            rate=Decimal("90.00"),
            status="pending",
            payment_url="",
            requisites={},
            created_at="2026-05-17T00:00:00Z",
            updated_at="2026-05-17T00:00:00Z",
        )

    async def confirm_topup(self, session_id: str) -> CerberCoreTopupSession:
        self.confirmed_sessions.append(session_id)
        return CerberCoreTopupSession(
            id=session_id,
            service_id="svc-1",
            user_hash="hash-1",
            method_id="method-1",
            amount_usdt=Decimal("25.00"),
            amount_rub=Decimal("2250.00"),
            rate=Decimal("90.00"),
            status="confirmed",
            payment_url="",
            requisites={},
            created_at="2026-05-17T00:00:00Z",
            updated_at="2026-05-17T00:00:01Z",
        )


def build_payment_service(session_factory, *, cerber_core_client=None, ledger_service=None) -> PaymentService:
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
        cerber_core_client=cerber_core_client,
        cerber_core_topup_method_code="card_ru",
        ledger_service=ledger_service,
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


@pytest.mark.asyncio
async def test_payment_service_uses_cerber_core_session_payload_and_confirms_it(tmp_path: Path) -> None:
    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'payments-core.db').as_posix()}"
    engine = create_engine(database_url)
    session_factory = create_session_factory(engine)
    await init_database(engine)

    core_client = StubCerberCoreClient()
    ledger = StubLedgerService(balance_usdt=Decimal("25.00"))
    service = build_payment_service(
        session_factory,
        cerber_core_client=core_client,
        ledger_service=ledger,
    )
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

    assert payment_link.payload == core_client.session_id
    assert service.nicepay_client.created_payments[0][0] == core_client.session_id
    assert core_client.created_sessions == [(telegram_user.id, Decimal("25.00"), "card_ru")]
    assert core_client.confirmed_sessions == [core_client.session_id]
    assert callback_result.balance_after == Decimal("25.00")

    async with session_factory() as session:
        user = await UserRepository(session).get_by_telegram_id(telegram_user.id)
        transactions = await WalletTransactionRepository(session).list_recent(telegram_user.id, limit=10)

    assert user is not None
    assert Decimal(str(user.balance)) == Decimal("0.00")
    assert len(transactions) == 0

    await engine.dispose()
