"""Сервис платежей (NicePay / Rukassa).

Создаёт ссылки на оплату, обрабатывает callback-уведомления, конвертирует
валюту через ExchangeRateService и зачисляет средства на баланс пользователя.
Поддерживает два провайдера: NicePay и Rukassa.
Если настроен RUKASSA_SHOP_ID + RUKASSA_TOKEN, используется Rukassa; иначе — NicePay.
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
from cerber_bot.integrations.rukassa import RukassaClient, RukassaError, RukassaFrozenError, RUKASSA_PAID_STATUS
from cerber_bot.services.exchange import ExchangeRateError, ExchangeRateService
from cerber_bot.services.store import format_money
from cerber_bot.texts import PAYMENT_SERVICE_TEXT, RUKASSA_TEXT


PAYMENT_PROVIDER_NAME = "nicepay"
RUKASSA_PROVIDER_NAME = "rukassa"
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


@dataclass(slots=True, frozen=True)
class PaymentH2HDetails:
    payment_id: str
    order_id: str
    currency: str
    amount: Decimal
    amount_minor: int
    status: int
    method: str | None
    details: dict[str, str]
    expire: str | None
    estimated_wallet_amount: Decimal
    wallet_currency: str


class PaymentService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        nicepay_client: NicePayClient,
        rukassa_client: RukassaClient | None = None,
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
        self.rukassa_client = rukassa_client
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
    def _use_rukassa(self) -> bool:
        """True, если Rukassa настроена и должна использоваться как основной провайдер."""
        return self.rukassa_client is not None and self.rukassa_client.is_configured

    @property
    def is_configured(self) -> bool:
        if self._use_rukassa:
            return True
        return self.nicepay_client.is_configured

    def ensure_configured(self) -> None:
        if self._use_rukassa:
            if self.payment_currency != "RUB":
                raise PaymentConfigurationError(RUKASSA_TEXT.ONLY_RUB_SUPPORTED)
            return
        self.nicepay_client.ensure_configured()
        if self.payment_currency not in NICEPAY_LIMITS:
            raise PaymentConfigurationError(
                PAYMENT_SERVICE_TEXT.unsupported_currency(self.payment_currency, ', '.join(sorted(NICEPAY_LIMITS)))
            )

    async def create_top_up_link(self, telegram_user: TelegramUserObject, amount: Decimal, *, force_provider: str | None = None) -> PaymentLink:
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

        if self._use_rukassa and force_provider != "nicepay":
            try:
                return await self._create_rukassa_top_up_link(
                    telegram_user=telegram_user,
                    normalized_amount=normalized_amount,
                    payload=payload,
                    description=description,
                )
            except RukassaFrozenError:
                # Магазин заморожен — пробуем NicePay как резервный провайдер
                if not self.nicepay_client.is_configured:
                    raise PaymentFlowError(RUKASSA_TEXT.FROZEN_FALLBACK_UNAVAILABLE) from None
                # Продолжаем выполнение ниже — создаём NicePay-платёж

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

    async def _create_rukassa_top_up_link(
        self,
        *,
        telegram_user: TelegramUserObject,
        normalized_amount: Decimal,
        payload: str,
        description: str,
    ) -> PaymentLink:
        """Создать ссылку на оплату через Rukassa."""
        assert self.rukassa_client is not None

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

            amount_rub = str(normalized_amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
            try:
                created_payment = await self.rukassa_client.create_payment(
                    order_id=payload,
                    amount_rub=amount_rub,
                    success_url=self.success_url,
                    fail_url=self.fail_url,
                    user_code=str(telegram_user.id),
                )
            except RukassaError as error:
                raise PaymentFlowError(str(error)) from error

            payment = await payment_repository.create_pending(
                telegram_id=telegram_user.id,
                payload=payload,
                provider=RUKASSA_PROVIDER_NAME,
                amount=normalized_amount,
                currency=self.payment_currency,
                title=self.title,
                description=description,
            )
            payment.provider_payment_charge_id = str(created_payment.payment_id)
            await session.commit()

        return PaymentLink(
            title=self.title,
            description=description,
            payload=payload,
            payment_id=str(created_payment.payment_id),
            payment_url=created_payment.payment_url,
            currency=self.payment_currency,
            amount=normalized_amount,
            estimated_wallet_amount=estimated_wallet_amount,
            wallet_currency=wallet_currency,
            amount_minor_units=0,
            expires_at=None,
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

    @property
    def is_rukassa_mode(self) -> bool:
        """True, если Rukassa настроена и используется как провайдер платежей."""
        return self._use_rukassa

    @property
    def is_nicepay_link_configured(self) -> bool:
        """True, если NicePay настроен в режиме ссылки (не H2H)."""
        return self.nicepay_client.is_configured and not bool(self.method)

    @property
    def is_h2h_mode(self) -> bool:
        return bool(self.method) and self.nicepay_client.is_configured and not self._use_rukassa

    async def process_rukassa_webhook(
        self,
        form_data: Mapping[str, str],
        *,
        signature_header: str,
    ) -> PaymentCallbackResult:
        """Обработать webhook-уведомление от Rukassa.

        Args:
            form_data:        Поля формы из тела POST-запроса.
            signature_header: Значение заголовка Signature.

        Returns:
            PaymentCallbackResult с результатом обработки.

        Raises:
            PaymentFlowError: При любой ошибке обработки.
        """
        if self.rukassa_client is None:
            raise PaymentFlowError("Rukassa не настроена.")
        try:
            notification = self.rukassa_client.parse_webhook(form_data, signature_header=signature_header)
        except RukassaError as error:
            raise PaymentFlowError(str(error)) from error

        async with self.session_factory() as session:
            user_repository = UserRepository(session)
            wallet_repository = WalletTransactionRepository(session)
            payment_repository = WalletPaymentRepository(session)

            payment = await payment_repository.get_by_payload(notification.order_id)
            if payment is None:
                raise PaymentFlowError(PAYMENT_SERVICE_TEXT.PAYMENT_NOT_FOUND)
            if payment.provider != RUKASSA_PROVIDER_NAME:
                raise PaymentFlowError(RUKASSA_TEXT.WRONG_PROVIDER)

            payment_amount = Decimal(str(payment.amount))
            try:
                webhook_amount = Decimal(notification.amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                expected_amount = payment_amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            except Exception:
                raise PaymentFlowError(RUKASSA_TEXT.AMOUNT_MISMATCH)
            if webhook_amount != expected_amount:
                raise PaymentFlowError(RUKASSA_TEXT.AMOUNT_MISMATCH)

            provider_payment_id = str(notification.id)
            payment_method = notification.payment_method

            if notification.status != RUKASSA_PAID_STATUS:
                if payment.status != "error":
                    await payment_repository.mark_failed(
                        payment,
                        provider_reference=payment_method,
                        provider_payment_id=provider_payment_id,
                    )
                    await session.commit()
                return PaymentCallbackResult(
                    result="error",
                    telegram_id=payment.telegram_id,
                    payload=payment.payload,
                    payment_id=provider_payment_id,
                    amount=payment_amount,
                    currency=payment.currency,
                    credited_amount=None,
                    credited_currency=None,
                    method=payment_method,
                    balance_after=None,
                )

            user = await user_repository.get_by_telegram_id(payment.telegram_id, with_lock=True)
            await session.refresh(payment)
            if user is None:
                raise PaymentFlowError(PAYMENT_SERVICE_TEXT.PAYMENT_NOT_FOUND)
            wallet_currency = user.balance_currency or self.wallet_currency

            if payment.status == "paid":
                credited_transaction = await wallet_repository.get_by_reference(provider_payment_id)
                await session.commit()
                completion = PaymentCompletion(
                    telegram_id=payment.telegram_id,
                    amount=payment_amount,
                    currency=payment.currency,
                    credited_amount=(Decimal(str(credited_transaction.amount)) if credited_transaction is not None else None),
                    credited_currency=(credited_transaction.currency if credited_transaction is not None else wallet_currency),
                    balance_after=Decimal(str(user.balance)),
                    payload=payment.payload,
                    payment_id=provider_payment_id,
                )
                return to_callback_result(completion, method=payment_method)

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
                description=RUKASSA_TEXT.credit_description_direct(
                    format_money(payment_amount, payment.currency)
                ) if payment.currency == wallet_currency else RUKASSA_TEXT.credit_description_converted(
                    format_money(payment_amount, payment.currency),
                    format_money(credited_amount, wallet_currency),
                ),
                reference=provider_payment_id,
            )
            await payment_repository.mark_paid(
                payment,
                provider_reference=payment_method,
                provider_payment_id=provider_payment_id,
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
                payment_id=provider_payment_id,
            )
            return to_callback_result(completion, method=payment_method)

    async def create_h2h_payment(
        self,
        telegram_user: TelegramUserObject,
        amount: Decimal,
        *,
        method: str | None = None,
    ) -> PaymentH2HDetails:
        self.ensure_configured()
        effective_method = method or self.method
        if not effective_method:
            raise PaymentConfigurationError(PAYMENT_SERVICE_TEXT.H2H_METHOD_REQUIRED)
        normalized_amount = normalize_amount(amount)
        min_amount, max_amount = self._effective_limits()
        if normalized_amount < min_amount:
            raise PaymentFlowError(PAYMENT_SERVICE_TEXT.min_top_up(format_money(min_amount, self.payment_currency)))
        if normalized_amount > max_amount:
            raise PaymentFlowError(PAYMENT_SERVICE_TEXT.max_top_up(format_money(max_amount, self.payment_currency)))

        payload = build_payment_payload(telegram_user.id)
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

            description = build_payment_description(self.description, normalized_amount, self.payment_currency)
            try:
                h2h_payment = await self.nicepay_client.h2h_one_request_payment(
                    order_id=payload,
                    customer=build_customer_account(telegram_user),
                    amount_minor=amount_minor_units,
                    currency=self.payment_currency,
                    method=effective_method,
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
            payment.provider_payment_charge_id = h2h_payment.payment_id
            await session.commit()

        return PaymentH2HDetails(
            payment_id=h2h_payment.payment_id,
            order_id=payload,
            currency=self.payment_currency,
            amount=normalized_amount,
            amount_minor=amount_minor_units,
            status=h2h_payment.status,
            method=h2h_payment.method or effective_method,
            details=h2h_payment.details,
            expire=h2h_payment.expire,
            estimated_wallet_amount=estimated_wallet_amount,
            wallet_currency=wallet_currency,
        )

    async def confirm_h2h_payment(self, *, payment_id: str) -> None:
        try:
            await self.nicepay_client.h2h_confirm_paid(payment_id=payment_id)
        except NicePayError as error:
            raise PaymentFlowError(str(error)) from error

    async def upload_h2h_proof(self, *, payment_id: str, file_bytes: bytes, filename: str, content_type: str) -> None:
        try:
            await self.nicepay_client.h2h_upload_proof(
                payment_id=payment_id,
                file_bytes=file_bytes,
                filename=filename,
                content_type=content_type,
            )
        except NicePayError as error:
            raise PaymentFlowError(str(error)) from error

    def _effective_limits(self) -> tuple[Decimal, Decimal]:
        if self._use_rukassa:
            return self.min_amount, self.max_amount
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