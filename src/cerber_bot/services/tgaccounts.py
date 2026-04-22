from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from cerber_bot.db.models import TgAccountPurchase, TelegramUser
from cerber_bot.db.repositories.tgaccounts import TgAccountRepository
from cerber_bot.db.repositories.users import UserRepository
from cerber_bot.db.repositories.wallet import WalletTransactionRepository
from cerber_bot.integrations.getmytg import GetMyTGClient, GetMyTGError


class TgAccountServiceError(RuntimeError):
    pass


class TgAccountNotFoundError(TgAccountServiceError):
    pass


class TgAccountInsufficientBalanceError(TgAccountServiceError):
    def __init__(self, *, available: Decimal, required: Decimal, currency: str) -> None:
        super().__init__(
            f"Недостаточно средств: доступно {available} {currency}, требуется {required} {currency}."
        )
        self.available = available
        self.required = required
        self.currency = currency


@dataclass(slots=True, frozen=True)
class TgCountryCard:
    country_code: str
    emoji: str | None
    display_name: str
    amount: Decimal
    currency: str
    available: bool
    available_count: int | None


@dataclass(slots=True, frozen=True)
class TgCatalogPage:
    items: tuple[TgCountryCard, ...]
    page: int
    total_pages: int
    total_items: int
    has_next: bool
    has_previous: bool


@dataclass(slots=True, frozen=True)
class TgCountryDetails:
    country_code: str
    emoji: str | None
    display_name: str
    amount: Decimal
    currency: str
    available: bool
    base_price: Decimal | None
    discount_percent: int | None


class TgAccountService:
    def __init__(
        self,
        client: GetMyTGClient,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self.client = client
        self.session_factory = session_factory

    @property
    def is_configured(self) -> bool:
        return self.client.is_configured

    async def get_catalog(self, *, sort: str = "name_asc", page: int = 1) -> TgCatalogPage:
        try:
            payload = await self.client.list_countries(
                auth=self.client.is_configured,
                sort=sort,
                page=page,
                page_size=20,
            )
        except GetMyTGError as error:
            raise TgAccountServiceError(str(error)) from error

        data = _unwrap_data(payload)
        items_raw = data.get("items") if isinstance(data.get("items"), list) else data
        if not isinstance(items_raw, list):
            raise TgAccountServiceError("GetMyTG вернул неожиданный формат каталога.")

        items = tuple(_parse_country_card(item) for item in items_raw if isinstance(item, dict))
        pagination = data.get("pagination") if isinstance(data, dict) else None
        page_num = _int_value(_mapping_get(pagination, "current_page"), default=page)
        total_pages = _int_value(_mapping_get(pagination, "total_pages"), default=max(1, page_num))
        total_items = _int_value(_mapping_get(pagination, "total_items"), default=len(items))
        has_next = bool(_mapping_get(pagination, "has_next")) if isinstance(pagination, dict) else page_num < total_pages
        has_previous = bool(_mapping_get(pagination, "has_previous")) if isinstance(pagination, dict) else page_num > 1

        return TgCatalogPage(
            items=items,
            page=page_num,
            total_pages=total_pages,
            total_items=total_items,
            has_next=has_next,
            has_previous=has_previous,
        )

    async def get_country_details(self, country_code: str) -> TgCountryDetails:
        try:
            payload = await self.client.get_country(country_code)
        except GetMyTGError as error:
            raise TgAccountServiceError(str(error)) from error

        data = _unwrap_data(payload)
        return _parse_country_details(data)

    async def buy_account(self, telegram_id: int, country_code: str) -> TgAccountPurchase:
        details = await self.get_country_details(country_code)

        async with self.session_factory() as session:
            user_repo = UserRepository(session)
            wallet_repo = WalletTransactionRepository(session)
            tg_repo = TgAccountRepository(session)

            user = await user_repo.get_by_telegram_id(telegram_id, with_lock=True)
            if user is None:
                raise TgAccountServiceError("Пользователь не найден.")

            user_currency = user.balance_currency or details.currency
            if user_currency != details.currency:
                raise TgAccountServiceError(
                    f"Валюта баланса {user_currency} не совпадает с валютой покупки {details.currency}."
                )

            available = Decimal(str(user.balance))
            if available < details.amount:
                raise TgAccountInsufficientBalanceError(
                    available=available,
                    required=details.amount,
                    currency=details.currency,
                )

            user.balance = available - details.amount
            await wallet_repo.add(
                telegram_id=telegram_id,
                transaction_type="tg_account_purchase",
                amount=-details.amount,
                currency=details.currency,
                description=f"Покупка Telegram-аккаунта {details.country_code}",
                reference=f"getmytg:country:{details.country_code}",
            )

            try:
                purchase_payload = await self.client.create_purchase(details.country_code)
            except GetMyTGError as error:
                await session.rollback()
                raise TgAccountServiceError(str(error)) from error

            purchase_data = _extract_purchase_payload(purchase_payload)
            purchase = await tg_repo.create(
                telegram_id=telegram_id,
                getmytg_purchase_id=_required_int(purchase_data, "id"),
                country_code=_required_str(purchase_data, "country_code", default=details.country_code),
                phone_number=_optional_str(purchase_data.get("phone_number")),
                status=_required_str(purchase_data, "status", default="PENDING"),
                amount=_extract_price_amount(purchase_data, default=details.amount),
                currency=_extract_price_currency(purchase_data, default=details.currency),
                purchase_type=_required_str(purchase_data, "purchase_type", default="SINGLE"),
                verification_code=_extract_verification_value(purchase_data, "code"),
                verification_password=_extract_verification_value(purchase_data, "password"),
            )

            await session.commit()
            return purchase

    async def request_verification(
        self,
        telegram_id: int,
        purchase_id: int,
        callback_url: str | None = None,
    ) -> TgAccountPurchase:
        async with self.session_factory() as session:
            repository = TgAccountRepository(session)
            purchase = await repository.get_by_id(purchase_id)
            if purchase is None or purchase.telegram_id != telegram_id:
                raise TgAccountNotFoundError("Покупка не найдена.")

            try:
                payload = await self.client.request_code(purchase.getmytg_purchase_id, callback_url=callback_url)
            except GetMyTGError as error:
                raise TgAccountServiceError(str(error)) from error

            purchase_payload = _extract_purchase_payload(payload)
            status = _required_str(purchase_payload, "status", default=purchase.status)
            phone_number = _optional_str(purchase_payload.get("phone_number"))

            await repository.update_status(purchase, status=status, phone_number=phone_number)
            await repository.update_verification(
                purchase,
                verification_code=_extract_verification_value(purchase_payload, "code"),
                verification_password=_extract_verification_value(purchase_payload, "password"),
            )
            await session.commit()
            return purchase

    async def get_my_purchases(self, telegram_id: int) -> tuple[TgAccountPurchase, ...]:
        async with self.session_factory() as session:
            repository = TgAccountRepository(session)
            rows = await repository.list_by_telegram_id(telegram_id)
            return tuple(rows)

    async def refund(self, telegram_id: int, purchase_id: int) -> TgAccountPurchase:
        async with self.session_factory() as session:
            user_repo = UserRepository(session)
            wallet_repo = WalletTransactionRepository(session)
            repository = TgAccountRepository(session)
            purchase = await repository.get_by_id(purchase_id)
            if purchase is None or purchase.telegram_id != telegram_id:
                raise TgAccountNotFoundError("Покупка не найдена.")

            try:
                payload = await self.client.refund_purchase(purchase.getmytg_purchase_id)
            except GetMyTGError as error:
                raise TgAccountServiceError(str(error)) from error

            purchase_payload = _extract_purchase_payload(payload)
            new_status = _required_str(purchase_payload, "status", default="REFUND")
            await repository.update_status(purchase, status=new_status)

            if new_status == "REFUND":
                user = await user_repo.get_by_telegram_id(telegram_id, with_lock=True)
                if user is None:
                    raise TgAccountServiceError("Пользователь не найден.")
                amount = Decimal(str(purchase.amount))
                user.balance += amount
                await wallet_repo.add(
                    telegram_id=telegram_id,
                    transaction_type="tg_account_refund",
                    amount=amount,
                    currency=purchase.currency,
                    description=f"Возврат за Telegram-аккаунт #{purchase.id}",
                    reference=f"getmytg:refund:{purchase.getmytg_purchase_id}",
                )

            await session.commit()
            return purchase


def _unwrap_data(payload: dict[str, object]) -> dict[str, Any]:
    data = payload.get("data")
    if isinstance(data, dict):
        return dict(data)
    return payload


def _parse_country_card(payload: dict[str, Any]) -> TgCountryCard:
    display_name = payload.get("display_name")
    if isinstance(display_name, dict):
        title = _optional_str(display_name.get("ru")) or _optional_str(display_name.get("en")) or "Unknown"
    else:
        title = _optional_str(display_name) or "Unknown"

    return TgCountryCard(
        country_code=_required_str(payload, "country_code", default=""),
        emoji=_optional_str(payload.get("emoji")),
        display_name=title,
        amount=_extract_price_amount(payload, default=Decimal("0")),
        currency=_extract_price_currency(payload, default="USD"),
        available=bool(payload.get("available")),
        available_count=_int_value(payload.get("available_count"), default=None),
    )


def _parse_country_details(payload: dict[str, Any]) -> TgCountryDetails:
    display_name = payload.get("display_name")
    if isinstance(display_name, dict):
        title = _optional_str(display_name.get("ru")) or _optional_str(display_name.get("en")) or "Unknown"
    else:
        title = _optional_str(display_name) or "Unknown"

    discount = payload.get("discount")
    base_price: Decimal | None = None
    discount_percent: int | None = None
    if isinstance(discount, dict):
        base_raw = discount.get("base_price")
        if base_raw is not None:
            base_price = _to_decimal(base_raw)
        discount_percent = _int_value(discount.get("percent"), default=None)

    return TgCountryDetails(
        country_code=_required_str(payload, "country_code", default=""),
        emoji=_optional_str(payload.get("emoji")),
        display_name=title,
        amount=_extract_price_amount(payload, default=Decimal("0")),
        currency=_extract_price_currency(payload, default="USD"),
        available=bool(payload.get("available")),
        base_price=base_price,
        discount_percent=discount_percent,
    )


def _extract_purchase_payload(payload: dict[str, object]) -> dict[str, Any]:
    data = payload.get("data")
    if isinstance(data, dict):
        purchase = data.get("purchase")
        if isinstance(purchase, dict):
            return dict(purchase)
        return dict(data)
    purchase = payload.get("purchase")
    if isinstance(purchase, dict):
        return dict(purchase)
    return dict(payload)


def _extract_price_amount(payload: dict[str, Any], *, default: Decimal) -> Decimal:
    price = payload.get("price")
    if isinstance(price, dict) and "amount" in price:
        return _to_decimal(price["amount"])
    if "amount" in payload:
        return _to_decimal(payload["amount"])
    return default


def _extract_price_currency(payload: dict[str, Any], *, default: str) -> str:
    price = payload.get("price")
    if isinstance(price, dict):
        code = _optional_str(price.get("currency_code"))
        if code:
            return code
    code = _optional_str(payload.get("currency"))
    if code:
        return code
    return default


def _extract_verification_value(payload: dict[str, Any], key: str) -> str | None:
    verification = payload.get("verification")
    if isinstance(verification, dict):
        return _optional_str(verification.get(key))
    return None


def _required_int(payload: dict[str, Any], key: str) -> int:
    if key not in payload:
        raise TgAccountServiceError(f"В ответе GetMyTG отсутствует поле {key}.")
    return _int_value(payload[key], default=None, required=True)


def _required_str(payload: dict[str, Any], key: str, *, default: str | None = None) -> str:
    value = _optional_str(payload.get(key))
    if value:
        return value
    if default is not None:
        return default
    raise TgAccountServiceError(f"В ответе GetMyTG отсутствует поле {key}.")


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _to_decimal(value: object) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as error:
        raise TgAccountServiceError(f"Некорректное денежное значение GetMyTG: {value}") from error


def _int_value(value: object, *, default: int | None, required: bool = False) -> int | None:
    if value is None:
        if required:
            raise TgAccountServiceError("Ожидалось целочисленное значение, но получен None.")
        return default
    try:
        return int(value)
    except (TypeError, ValueError) as error:
        if required:
            raise TgAccountServiceError(f"Ожидалось целочисленное значение, но получено: {value}") from error
        return default


def _mapping_get(mapping: object, key: str) -> object:
    if isinstance(mapping, dict):
        return mapping.get(key)
    return None
