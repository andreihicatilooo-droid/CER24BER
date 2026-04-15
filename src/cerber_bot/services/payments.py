"""Сервис платежей NicePay.

Создаёт ссылки на оплату, обрабатывает callback-уведомления, конвертирует
валюту через ExchangeRateService и зачисляет средства на баланс пользователя.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Mapping
from uuid import uuid4

from aiogram.types import User as TelegramUserObject
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from cerber_bot.db.repositories.payments import WalletPaymentRepository
from cerber_bot.db.repositories.users import UserRepository
from cerber_bot.db.repositories.wallet import WalletTransactionRepository
from cerber_bot.integrations.nicepay import NicePayClient, NicePayError
from cerber_bot.services.exchange import ExchangeRateError, ExchangeRateService
from cerber_bot.services.store import format_money
from cerber_bot.texts import PAYMENT_SERVICE_TEXT


PAYMENT_PROVIDER_NAME = "nicepay"
NICEPAY_LIMITS: dict[str, tuple[Decimal, Decimal]] = {
    "USD": (Decimal("10.00"), Decimal("990.00")),
    "EUR": (Decimal("10.00"), Decimal("850.00")),
    "RUB": (Decimal("200.00"), Decimal("85000.00")),
    "UAH": (Decimal("100.00"), Decimal("35000.00")),
    "KZT": (Decimal("1000.00"), Decimal("410000.00")),
}


class PaymentFlowError(RuntimeError):
    pass


class PaymentConfigurationError(PaymentFlowError):
    pass


@dataclass(slots=True, frozen=True)
class PaymentLink:
    title: str
    description: str
    payload: str
    payment_id: str
    payment_url: str
    currency: str
    amount: Decimal
    estimated_wallet_amount: Decimal
    wallet_currency: str
    amount_minor_units: int
    expires_at: object | None


@dataclass(slots=True, frozen=True)
class PaymentCallbackResult:
    result: str
    telegram_id: int
    payload: str
    payment_id: str
    amount: Decimal
    currency: str
    credited_amount: Decimal | None
    credited_currency: str | None
    method: str | None
    balance_after: Decimal | None


@dataclass(slots=True, frozen=True)
class PaymentCompletion:
    telegram_id: int
    amount: Decimal
    currency: str
    credited_amount: Decimal | None
    credited_currency: str | None
    balance_after: Decimal
    payload: str
    payment_id: str


class PaymentService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        nicepay_client: NicePayClient,
        exchange_rate_service: ExchangeRateService,
        wallet_currency: str,
        payment_currency: str,
        title: str,
        description: str,
        min_amount: Decimal,
        max_amount: Decimal,
        success_url: str | None,
        fail_url: str | None,
        method: str | None,
    ) -> None:
        self.session_factory = session_factory
        self.nicepay_client = nicepay_client
        self.exchange_rate_service = exchange_rate_service
        self.wallet_currency = wallet_currency
        self.payment_currency = payment_currency
        self.title = title
        self.description = description
        self.min_amount = normalize_amount(min_amount)
        self.max_amount = normalize_amount(max_amount)
        self.success_url = success_url.strip() if success_url else None
        self.fail_url = fail_url.strip() if fail_url else None
        self.method = method.strip() if method else None

    @property
    def is_configured(self) -> bool:
        return self.nicepay_client.is_configured

    def ensure_configured(self) -> None:
        self.nicepay_client.ensure_configured()
        if self.payment_currency not in NICEPAY_LIMITS:
            raise PaymentConfigurationError(
                PAYMENT_SERVICE_TEXT.unsupported_currency(self.payment_currency, ', '.join(sorted(NICEPAY_LIMITS)))
            )

    async def create_top_up_link(self, telegram_user: TelegramUserObject, amount: Decimal) -> PaymentLink:
        self.ensure_configured()
        normalized_amount = normalize_amount(amount)
        min_amount, max_amount = self._effective_limits()
        if normalized_amount < min_amount:
            raise PaymentFlowError(PAYMENT_SERVICE_TEXT.min_top_up(format_money(min_amount, self.payment_currency)))
        if normalized_amount > max_amount:
            raise PaymentFlowError(PAYMENT_SERVICE_TEXT.max_top_up(format_money(max_amount, self.payment_currency)))

        payload = build_payment_payload(telegram_user.id)
        description = build_payment_description(self.description, normalized_amount, self.payment_currency)
        amount_minor_units = amount_to_minor_units(normalized_amount)

        async with self.session_factory() as session:
            user_repository = UserRepository(session)
            payment_repository = WalletPaymentRepository(session)
            user, _ = await user_repository.get_or_create(
                telegram_id=telegram_user.id,
                username=telegram_user.username,
                first_name=telegram_user.first_name,
                last_name=telegram_user.last_name,
                language_code=telegram_user.language_code,
                is_bot=telegram_user.is_bot,
                balance_currency=self.wallet_currency,
            )
            wallet_currency = user.balance_currency or self.wallet_currency
            if not user.balance_currency:
                user.balance_currency = wallet_currency
            try:
                estimated_wallet_amount = await self.exchange_rate_service.convert(
                    normalized_amount,
                    self.payment_currency,
                    wallet_currency,
                )
            except ExchangeRateError as error:
                raise PaymentFlowError(str(error)) from error

            try:
                created_payment = await self.nicepay_client.create_payment(
                    order_id=payload,
                    account=build_customer_account(telegram_user),
                    amount_minor=amount_minor_units,
                    currency=self.payment_currency,
                    description=description,
                    method=self.method,
                    success_url=self.success_url,
                    fail_url=self.fail_url,
                )
            except NicePayError as error:
                raise PaymentFlowError(str(error)) from error

            payment = await payment_repository.create_pending(
                telegram_id=telegram_user.id,
                payload=payload,
                provider=PAYMENT_PROVIDER_NAME,
                amount=normalized_amount,
                currency=self.payment_currency,
                title=self.title,
                description=description,
            )
            payment.provider_payment_charge_id = created_payment.payment_id
            await session.commit()

        return PaymentLink(
            title=self.title,
            description=description,
            payload=payload,
            payment_id=created_payment.payment_id,
            payment_url=created_payment.link,
            currency=self.payment_currency,
            amount=normalized_amount,
            estimated_wallet_amount=estimated_wallet_amount,
            wallet_currency=wallet_currency,
            amount_minor_units=amount_minor_units,
            expires_at=created_payment.expires_at,
        )

    async def process_callback(self, parameters: Mapping[str, object]) -> PaymentCallbackResult:
        self.ensure_configured()
        try:
            notification = self.nicepay_client.parse_webhook(parameters)
        except NicePayError as error:
            raise PaymentFlowError(str(error)) from error

        if notification.merchant_id != (self.nicepay_client.merchant_id or ""):
            raise PaymentFlowError(PAYMENT_SERVICE_TEXT.FOREIGN_MERCHANT)

        async with self.session_factory() as session:
            user_repository = UserRepository(session)
            wallet_repository = WalletTransactionRepository(session)
            payment_repository = WalletPaymentRepository(session)

            payment = await payment_repository.get_by_payload(notification.order_id)
            if payment is None:
                raise PaymentFlowError(PAYMENT_SERVICE_TEXT.PAYMENT_NOT_FOUND)
            if payment.provider != PAYMENT_PROVIDER_NAME:
                raise PaymentFlowError(PAYMENT_SERVICE_TEXT.WRONG_PROVIDER)
            if payment.currency != notification.amount_currency or self.payment_currency != notification.amount_currency:
                raise PaymentFlowError(PAYMENT_SERVICE_TEXT.CURRENCY_MISMATCH)
            payment_amount = Decimal(str(payment.amount))
            if amount_to_minor_units(payment_amount) != notification.amount_minor:
                raise PaymentFlowError(PAYMENT_SERVICE_TEXT.AMOUNT_MISMATCH)
            if payment.provider_payment_charge_id and payment.provider_payment_charge_id != notification.payment_id:
                raise PaymentFlowError(PAYMENT_SERVICE_TEXT.PAYMENT_ID_MISMATCH)

            if notification.result == "error":
                if payment.status != "error":
                    await payment_repository.mark_failed(
                        payment,
                        provider_reference=notification.method,
                        provider_payment_id=notification.payment_id,
                    )
                    await session.commit()
                return PaymentCallbackResult(
                    result="error",
                    telegram_id=payment.telegram_id,
                    payload=payment.payload,
                    payment_id=notification.payment_id,
                    amount=payment_amount,
                    currency=payment.currency,
                    credited_amount=None,
                    credited_currency=None,
                    method=notification.method,
                    balance_after=None,
                )
            if notification.result != "success":
                raise PaymentFlowError(PAYMENT_SERVICE_TEXT.unknown_status(notification.result))

            user, _ = await user_repository.get_or_create(
                telegram_id=payment.telegram_id,
                username=None,
                first_name=None,
                last_name=None,
                language_code=None,
                is_bot=False,
                balance_currency=self.wallet_currency,
            )
            # Блокируем строку пользователя, чтобы сериализовать конкурентные webhook-вызовы.
            # После получения блокировки перечитываем платёж — если дублирующий вебхук
            # уже успел зачислить средства и снять блокировку, статус будет "paid".
            user = await user_repository.get_by_telegram_id(payment.telegram_id, with_lock=True)
            await session.refresh(payment)
            wallet_currency = user.balance_currency or self.wallet_currency

            if payment.status == "paid":
                credited_transaction = await wallet_repository.get_by_reference(notification.payment_id)
                await session.commit()
                completion = PaymentCompletion(
                    telegram_id=payment.telegram_id,
                    amount=payment_amount,
                    currency=payment.currency,
                    credited_amount=(Decimal(str(credited_transaction.amount)) if credited_transaction is not None else None),
                    credited_currency=(credited_transaction.currency if credited_transaction is not None else wallet_currency),
                    balance_after=Decimal(str(user.balance)),
                    payload=payment.payload,
                    payment_id=notification.payment_id,
                )
                return to_callback_result(completion, method=notification.method)

            try:
                credited_amount = await self.exchange_rate_service.convert(
                    payment_amount,
                    payment.currency,
                    wallet_currency,
                )
            except ExchangeRateError as error:
                raise PaymentFlowError(str(error)) from error

            user.balance_currency = wallet_currency
            user.balance += credited_amount
            await wallet_repository.add(
                telegram_id=payment.telegram_id,
                transaction_type="top_up",
                amount=credited_amount,
                currency=wallet_currency,
                description=build_wallet_credit_description(
                    payment_amount=payment_amount,
                    payment_currency=payment.currency,
                    credited_amount=credited_amount,
                    wallet_currency=wallet_currency,
                ),
                reference=notification.payment_id,
            )
            await payment_repository.mark_paid(
                payment,
                provider_reference=notification.method,
                provider_payment_id=notification.payment_id,
            )
            await session.commit()

            completion = PaymentCompletion(
                telegram_id=payment.telegram_id,
                amount=payment_amount,
                currency=payment.currency,
                credited_amount=credited_amount,
                credited_currency=wallet_currency,
                balance_after=Decimal(str(user.balance)),
                payload=payment.payload,
                payment_id=notification.payment_id,
            )
            return to_callback_result(completion, method=notification.method)

    def _effective_limits(self) -> tuple[Decimal, Decimal]:
        provider_min, provider_max = NICEPAY_LIMITS[self.payment_currency]
        min_amount = max(self.min_amount, provider_min)
        max_amount = min(self.max_amount, provider_max)
        return min_amount, max_amount


def build_payment_payload(telegram_id: int) -> str:
    return f"w{telegram_id}_{uuid4().hex[:20]}"


def build_customer_account(telegram_user: TelegramUserObject) -> str:
    username = (telegram_user.username or "").strip().lstrip("@")
    if username:
        return username[:50]
    return f"tg_{telegram_user.id}"[:50]


def build_payment_description(base_description: str, amount: Decimal, currency: str) -> str:
    suffix = PAYMENT_SERVICE_TEXT.description_suffix(format_money(amount, currency))
    normalized = " ".join(base_description.split())
    if len(normalized) + len(suffix) <= 150:
        return f"{normalized}{suffix}"
    trimmed = normalized[: max(0, 150 - len(suffix))].rstrip()
    return f"{trimmed}{suffix}" if trimmed else suffix.strip()


def build_wallet_credit_description(
    *,
    payment_amount: Decimal,
    payment_currency: str,
    credited_amount: Decimal,
    wallet_currency: str,
) -> str:
    paid_text = format_money(payment_amount, payment_currency)
    credited_text = format_money(credited_amount, wallet_currency)
    if payment_currency == wallet_currency:
        return PAYMENT_SERVICE_TEXT.credit_description_direct(paid_text)
    return PAYMENT_SERVICE_TEXT.credit_description_converted(paid_text, credited_text)


def normalize_amount(amount: Decimal) -> Decimal:
    return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def amount_to_minor_units(amount: Decimal) -> int:
    normalized = normalize_amount(amount)
    return int((normalized * 100).to_integral_value(rounding=ROUND_HALF_UP))


def to_callback_result(completion: PaymentCompletion, *, method: str | None) -> PaymentCallbackResult:
    return PaymentCallbackResult(
        result="success",
        telegram_id=completion.telegram_id,
        payload=completion.payload,
        payment_id=completion.payment_id,
        amount=completion.amount,
        currency=completion.currency,
        credited_amount=completion.credited_amount,
        credited_currency=completion.credited_currency,
        method=method,
        balance_after=completion.balance_after,
    )