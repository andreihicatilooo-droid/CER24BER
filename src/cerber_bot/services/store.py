"""Сервис витрины магазина.

Отвечает за кэшированный каталог GiftAPI, навигацию по категориям и товарам,
поиск, управление кошельком, покупку SKU и историю заказов пользователя.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal
from time import monotonic
from typing import TypeVar
from uuid import uuid4

from aiogram.types import User as TelegramUserObject
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from cerber_bot.db.models import TelegramUser, UserOrder, WalletTransaction
from cerber_bot.db.repositories.orders import UserOrderRepository
from cerber_bot.db.repositories.users import UserRepository
from cerber_bot.db.repositories.wallet import WalletTransactionRepository
from cerber_bot.integrations.giftapi import GiftApiError, GiftApiClient, GiftCategory, GiftPricelistItem, GiftProductDetail, GiftProductSummary
from cerber_bot.services.exchange import ExchangeRateError, ExchangeRateService, WalletQuote
from cerber_bot.services.giftapi import GiftApiOrderDraft, GiftApiService
from cerber_bot.texts import COMMON_TEXT, STORE_SERVICE_TEXT


logger = logging.getLogger(__name__)

DEFAULT_WALLET_CURRENCY = "USD"
SUPPORTED_AUTO_FIELDS = {"quantity"}
ItemT = TypeVar("ItemT")


class StoreServiceError(RuntimeError):
    pass


class SearchQueryError(StoreServiceError):
    pass


class InsufficientBalanceError(StoreServiceError):
    def __init__(self, available: Decimal, required: Decimal, currency: str) -> None:
        self.available = available
        self.required = required
        self.currency = currency
        super().__init__(STORE_SERVICE_TEXT.insufficient_funds(format_money(available, currency), format_money(required, currency)))


class ProductUnavailableError(StoreServiceError):
    pass


@dataclass(slots=True, frozen=True)
class PageInfo:
    page: int
    total_pages: int
    per_page: int
    total_items: int

    @property
    def has_previous(self) -> bool:
        return self.page > 1

    @property
    def has_next(self) -> bool:
        return self.page < self.total_pages


@dataclass(slots=True, frozen=True)
class StoreCategoryCard:
    category_id: int
    name: str
    product_count: int


@dataclass(slots=True, frozen=True)
class StoreProductCard:
    product_id: str
    name: str
    product_type: str
    denomination_type: str | None
    category_id: int | None
    category_name: str | None
    summary: str
    min_price: Decimal | None
    max_price: Decimal | None
    currency: str | None
    total_stock: int
    sku_count: int
    buyable_sku_count: int
    searchable_text: str


@dataclass(slots=True, frozen=True)
class StoreProductOffer:
    sku_id: str
    name: str
    price: Decimal | None
    currency: str
    stock: int
    max_per_order: int | None
    buyable: bool
    reason_unavailable: str | None
    attributes: dict[str, object]
    required_fields: tuple[object, ...] = field(default_factory=tuple)


@dataclass(slots=True, frozen=True)
class StoreProductView:
    product_id: str
    name: str
    product_type: str
    denomination_type: str | None
    category_name: str | None
    description: str
    summary: str
    required_fields: tuple[object, ...]
    offers: tuple[StoreProductOffer, ...]
    image: str | None


@dataclass(slots=True, frozen=True)
class WalletTransactionView:
    transaction_id: int
    transaction_type: str
    amount: Decimal
    currency: str
    description: str
    reference: str | None
    created_at: object


@dataclass(slots=True, frozen=True)
class WalletSnapshot:
    balance: Decimal
    held_balance: Decimal
    total_balance: Decimal
    currency: str
    balance_quote: WalletQuote
    held_quote: WalletQuote
    total_quote: WalletQuote
    recent_transactions: tuple[WalletTransactionView, ...]
    order_count: int


@dataclass(slots=True, frozen=True)
class StoreOrderCard:
    order_id: int
    external_id: str
    provider_order_id: str | None
    product_name: str
    sku_name: str
    status: str
    total_amount: Decimal
    currency: str
    created_at: object


@dataclass(slots=True, frozen=True)
class StoreOrderView:
    order_id: int
    external_id: str
    provider_order_id: str | None
    provider: str
    product_name: str
    sku_name: str
    status: str
    total_amount: Decimal
    currency: str
    created_at: object
    delivery_payload: str | None
    error_message: str | None


@dataclass(slots=True, frozen=True)
class StoreDashboard:
    category_count: int
    product_count: int
    balance: Decimal
    held_balance: Decimal
    total_balance: Decimal
    currency: str
    balance_quote: WalletQuote
    held_quote: WalletQuote
    total_quote: WalletQuote
    order_count: int


@dataclass(slots=True)
class CatalogSnapshot:
    categories: tuple[StoreCategoryCard, ...]
    products: tuple[StoreProductCard, ...]
    products_by_id: dict[str, StoreProductCard]


@dataclass(slots=True, frozen=True)
class PurchaseResult:
    order: StoreOrderView
    charged_amount: Decimal
    charged_currency: str
    balance_after: Decimal
    currency: str


class StoreService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        gift_api_service: GiftApiService,
        gift_api_client: GiftApiClient,
        exchange_rate_service: ExchangeRateService,
        cache_ttl_seconds: int = 120,
        wallet_currency: str = DEFAULT_WALLET_CURRENCY,
    ) -> None:
        self.session_factory = session_factory
        self.gift_api_service = gift_api_service
        self.gift_api_client = gift_api_client
        self.exchange_rate_service = exchange_rate_service
        self.cache_ttl_seconds = cache_ttl_seconds
        self.wallet_currency = wallet_currency
        self._cached_snapshot: CatalogSnapshot | None = None
        self._cache_until = 0.0
        self._cache_lock = asyncio.Lock()

    async def refresh_catalog(self) -> CatalogSnapshot:
        return await self.get_catalog_snapshot(force_refresh=True)

    async def get_catalog_snapshot(self, force_refresh: bool = False) -> CatalogSnapshot:
        current = monotonic()
        if not force_refresh and self._cached_snapshot is not None and current < self._cache_until:
            return self._cached_snapshot

        async with self._cache_lock:
            current = monotonic()
            if not force_refresh and self._cached_snapshot is not None and current < self._cache_until:
                return self._cached_snapshot

            self.gift_api_service.ensure_configured()
            categories, products, pricelist = await asyncio.gather(
                self.gift_api_client.list_categories(),
                self.gift_api_client.list_all_products(include_skus=True),
                self.gift_api_client.list_all_pricelist(),
            )
            snapshot = build_catalog_snapshot(categories, products, pricelist)
            self._cached_snapshot = snapshot
            self._cache_until = current + self.cache_ttl_seconds
            logger.info(
                "Store catalog rebuilt: %s categories, %s products",
                len(snapshot.categories),
                len(snapshot.products),
            )
            return snapshot

    async def get_dashboard(self, telegram_id: int) -> StoreDashboard:
        snapshot = await self.get_catalog_snapshot()
        wallet = await self.get_wallet_snapshot(telegram_id)
        return StoreDashboard(
            category_count=len(snapshot.categories),
            product_count=len(snapshot.products),
            balance=wallet.balance,
            held_balance=wallet.held_balance,
            total_balance=wallet.total_balance,
            currency=wallet.currency,
            balance_quote=wallet.balance_quote,
            held_quote=wallet.held_quote,
            total_quote=wallet.total_quote,
            order_count=wallet.order_count,
        )

    async def get_categories_page(self, page: int, per_page: int = 8) -> tuple[tuple[StoreCategoryCard, ...], PageInfo]:
        snapshot = await self.get_catalog_snapshot()
        return paginate_items(snapshot.categories, page=page, per_page=per_page)

    async def get_products_page(
        self,
        *,
        page: int,
        per_page: int = 6,
        category_id: int | None = None,
        search_query: str | None = None,
    ) -> tuple[tuple[StoreProductCard, ...], PageInfo]:
        snapshot = await self.get_catalog_snapshot()
        items = snapshot.products

        if category_id is not None:
            items = tuple(item for item in items if item.category_id == category_id)

        if search_query:
            normalized_query = normalize_search_query(search_query)
            tokens = normalized_query.split()
            items = tuple(item for item in items if all(token in item.searchable_text for token in tokens))

        return paginate_items(items, page=page, per_page=per_page)

    async def get_product_view(self, product_id: str) -> StoreProductView:
        snapshot = await self.get_catalog_snapshot()
        summary = snapshot.products_by_id.get(product_id)
        detail = await self.gift_api_service.get_product_detail(product_id)
        required_fields = tuple(detail.required_fields or ())

        offers: list[StoreProductOffer] = []
        for sku in detail.skus:
            reason: str | None = None
            if sku.price is None:
                reason = STORE_SERVICE_TEXT.REASON_DYNAMIC_PRICE
            elif sku.stock <= 0:
                reason = STORE_SERVICE_TEXT.REASON_OUT_OF_STOCK
            elif detail.denomination_type == "custom":
                reason = STORE_SERVICE_TEXT.REASON_CUSTOM_AMOUNT

            # Поля, которые нужно запросить у покупателя (не auto-заполняемые)
            offer_required_fields = tuple(
                f for f in required_fields
                if getattr(f, "code", None) not in SUPPORTED_AUTO_FIELDS
            )

            offers.append(
                StoreProductOffer(
                    sku_id=sku.sku_id,
                    name=sku.name,
                    price=sku.price,
                    currency=sku.currency,
                    stock=sku.stock,
                    max_per_order=sku.max_per_order,
                    buyable=reason is None,
                    reason_unavailable=reason,
                    attributes=sku.attributes,
                    required_fields=offer_required_fields,
                )
            )

        description = strip_html(detail.description or "")
        return StoreProductView(
            product_id=detail.product_id,
            name=detail.name,
            product_type=detail.product_type,
            denomination_type=detail.denomination_type,
            category_name=detail.category_name,
            description=description,
            summary=summary.summary if summary is not None else shorten_plain_text(description, 180),
            required_fields=required_fields,
            offers=tuple(offers),
            image=detail.image,
        )

    async def ensure_user(self, telegram_user: TelegramUserObject) -> TelegramUser:
        async with self.session_factory() as session:
            repository = UserRepository(session)
            user, _ = await repository.get_or_create(
                telegram_id=telegram_user.id,
                username=telegram_user.username,
                first_name=telegram_user.first_name,
                last_name=telegram_user.last_name,
                language_code=telegram_user.language_code,
                is_bot=telegram_user.is_bot,
                balance_currency=self.wallet_currency,
            )
            await session.commit()
            return user

    async def get_wallet_snapshot(self, telegram_id: int, limit: int = 6) -> WalletSnapshot:
        async with self.session_factory() as session:
            user_repository = UserRepository(session)
            wallet_repository = WalletTransactionRepository(session)
            order_repository = UserOrderRepository(session)

            user = await user_repository.get_by_telegram_id(telegram_id)
            transactions = await wallet_repository.list_recent(telegram_id, limit=limit)
            order_count = await order_repository.count_by_telegram_id(telegram_id)

            balance = Decimal("0.00") if user is None else Decimal(str(user.balance))
            held_balance = Decimal("0.00") if user is None else Decimal(str(user.held_balance))
            total_balance = balance + held_balance
            currency = self.wallet_currency if user is None else user.balance_currency
            balance_quote = await self.exchange_rate_service.quote_wallet(balance, currency)
            held_quote = await self.exchange_rate_service.quote_wallet(held_balance, currency)
            total_quote = await self.exchange_rate_service.quote_wallet(total_balance, currency)
            transaction_views = tuple(
                WalletTransactionView(
                    transaction_id=item.id,
                    transaction_type=item.transaction_type,
                    amount=Decimal(str(item.amount)),
                    currency=item.currency,
                    description=item.description,
                    reference=item.reference,
                    created_at=item.created_at,
                )
                for item in transactions
            )
            return WalletSnapshot(
                balance=balance,
                held_balance=held_balance,
                total_balance=total_balance,
                currency=currency,
                balance_quote=balance_quote,
                held_quote=held_quote,
                total_quote=total_quote,
                recent_transactions=transaction_views,
                order_count=order_count,
            )

    async def top_up_balance(self, telegram_user: TelegramUserObject, amount: Decimal) -> WalletSnapshot:
        normalized_amount = normalize_money_amount(amount)
        if normalized_amount <= Decimal("0.00"):
            raise StoreServiceError(STORE_SERVICE_TEXT.TOP_UP_AMOUNT_POSITIVE)

        async with self.session_factory() as session:
            user_repository = UserRepository(session)
            wallet_repository = WalletTransactionRepository(session)
            user, _ = await user_repository.get_or_create(
                telegram_id=telegram_user.id,
                username=telegram_user.username,
                first_name=telegram_user.first_name,
                last_name=telegram_user.last_name,
                language_code=telegram_user.language_code,
                is_bot=telegram_user.is_bot,
                balance_currency=self.wallet_currency,
            )

            user.balance += normalized_amount
            user.updated_at = user.last_seen_at
            await wallet_repository.add(
                telegram_id=telegram_user.id,
                transaction_type="top_up",
                amount=normalized_amount,
                currency=user.balance_currency,
                description=STORE_SERVICE_TEXT.top_up_description(format_money(normalized_amount, user.balance_currency)),
            )
            await session.commit()

        return await self.get_wallet_snapshot(telegram_user.id)

    async def adjust_balance(
        self,
        telegram_user: TelegramUserObject,
        amount: Decimal,
        *,
        transaction_type: str = "manual_adjustment",
        description: str | None = None,
    ) -> WalletSnapshot:
        normalized_amount = normalize_money_amount(amount)
        if normalized_amount == Decimal("0.00"):
            raise StoreServiceError(STORE_SERVICE_TEXT.BALANCE_ADJUSTMENT_NON_ZERO)

        async with self.session_factory() as session:
            user_repository = UserRepository(session)
            wallet_repository = WalletTransactionRepository(session)
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
            available_balance = Decimal(str(user.balance))
            required_amount = abs(normalized_amount)
            if normalized_amount < Decimal("0.00") and available_balance < required_amount:
                raise InsufficientBalanceError(available_balance, required_amount, wallet_currency)

            user.balance_currency = wallet_currency
            user.balance = available_balance + normalized_amount
            user.updated_at = user.last_seen_at

            amount_text = format_money(required_amount, wallet_currency)
            transaction_description = description
            if transaction_description is None:
                transaction_description = (
                    STORE_SERVICE_TEXT.manual_credit_description(amount_text)
                    if normalized_amount > Decimal("0.00")
                    else STORE_SERVICE_TEXT.manual_debit_description(amount_text)
                )

            await wallet_repository.add(
                telegram_id=telegram_user.id,
                transaction_type=transaction_type,
                amount=normalized_amount,
                currency=wallet_currency,
                description=transaction_description,
            )
            await session.commit()

        return await self.get_wallet_snapshot(telegram_user.id)

    async def get_orders_page(self, telegram_id: int, page: int, per_page: int = 6) -> tuple[tuple[StoreOrderCard, ...], PageInfo]:
        async with self.session_factory() as session:
            order_repository = UserOrderRepository(session)
            total_items = await order_repository.count_by_telegram_id(telegram_id)
            page_info = build_page_info(total_items=total_items, page=page, per_page=per_page)
            offset = (page_info.page - 1) * page_info.per_page
            orders = await order_repository.list_by_telegram_id(telegram_id, offset=offset, limit=page_info.per_page)
            order_cards = tuple(to_order_card(order) for order in orders)
            return order_cards, page_info

    async def get_order_view(self, telegram_id: int, order_id: int) -> StoreOrderView | None:
        async with self.session_factory() as session:
            order_repository = UserOrderRepository(session)
            order = await order_repository.get_for_user(order_id, telegram_id)
            if order is None:
                return None
            return to_order_view(order)

    async def purchase_offer(
        self,
        telegram_user: TelegramUserObject,
        *,
        product_id: str,
        sku_id: str,
        customer_fields: dict[str, object] | None = None,
    ) -> PurchaseResult:
        self.gift_api_service.ensure_configured(require_secret=True)
        product = await self.get_product_view(product_id)
        offer = next((item for item in product.offers if item.sku_id == sku_id), None)
        if offer is None:
            raise ProductUnavailableError(STORE_SERVICE_TEXT.SKU_NOT_FOUND)
        if not offer.buyable or offer.price is None:
            raise ProductUnavailableError(offer.reason_unavailable or STORE_SERVICE_TEXT.SKU_NOT_BUYABLE)

        await self.ensure_user(telegram_user)
        wallet = await self.get_wallet_snapshot(telegram_user.id)
        try:
            required_wallet_amount = await self.exchange_rate_service.convert(offer.price, offer.currency, wallet.currency)
        except ExchangeRateError as error:
            raise StoreServiceError(str(error)) from error
        if wallet.balance < required_wallet_amount:
            raise InsufficientBalanceError(wallet.balance, required_wallet_amount, wallet.currency)

        external_id = build_external_order_id(telegram_user.id)
        order_fields: dict[str, object] = {"quantity": 1}
        if customer_fields:
            order_fields.update(customer_fields)
        gift_order = await self.gift_api_service.create_order(
            GiftApiOrderDraft(
                external_id=external_id,
                sku_id=sku_id,
                fields=order_fields,
                metadata={
                    "telegram_id": telegram_user.id,
                    "source": "cerber_bot",
                    "product_id": product_id,
                    "sku_id": sku_id,
                },
            )
        )

        order_total_amount = normalize_money_amount(gift_order.total_amount if gift_order.total_amount > Decimal("0") else offer.price)
        order_item = next((item for item in gift_order.items if item.sku_id == sku_id), gift_order.items[0] if gift_order.items else None)
        sku_name = order_item.sku_name if order_item is not None else offer.name
        delivery_payload = json.dumps(order_item.delivery_data, ensure_ascii=False) if order_item and order_item.delivery_data else None
        error_message = order_item.error_message if order_item is not None else None

        async with self.session_factory() as session:
            user_repository = UserRepository(session)
            wallet_repository = WalletTransactionRepository(session)
            order_repository = UserOrderRepository(session)

            user = await user_repository.get_by_telegram_id(telegram_user.id, with_lock=True)
            if user is None:
                raise StoreServiceError(STORE_SERVICE_TEXT.USER_NOT_FOUND_AFTER_AUTH)

            wallet_currency = user.balance_currency or self.wallet_currency
            try:
                charged_amount = await self.exchange_rate_service.convert(order_total_amount, offer.currency, wallet_currency)
            except ExchangeRateError as error:
                raise StoreServiceError(str(error)) from error
            if user.balance < charged_amount:
                raise InsufficientBalanceError(Decimal(str(user.balance)), charged_amount, wallet_currency)

            user.balance_currency = wallet_currency
            user.balance -= charged_amount
            user.updated_at = user.last_seen_at

            await wallet_repository.add(
                telegram_id=telegram_user.id,
                transaction_type="purchase",
                amount=-charged_amount,
                currency=wallet_currency,
                description=build_purchase_description(
                    product_name=product.name,
                    order_total_amount=order_total_amount,
                    order_currency=offer.currency,
                    charged_amount=charged_amount,
                    wallet_currency=wallet_currency,
                ),
                reference=gift_order.order_id,
            )
            created_order = await order_repository.create(
                telegram_id=telegram_user.id,
                external_id=gift_order.external_id,
                provider_order_id=gift_order.order_id,
                provider="giftapi",
                product_id=product.product_id,
                product_name=product.name,
                sku_id=offer.sku_id,
                sku_name=sku_name,
                status=gift_order.status,
                total_amount=order_total_amount,
                currency=offer.currency,
                delivery_payload=delivery_payload,
                error_message=error_message,
            )
            await session.commit()

            return PurchaseResult(
                order=to_order_view(created_order),
                charged_amount=charged_amount,
                charged_currency=wallet_currency,
                balance_after=Decimal(str(user.balance)),
                currency=user.balance_currency,
            )


def build_catalog_snapshot(
    categories: tuple[GiftCategory, ...],
    products: tuple[GiftProductSummary, ...],
    pricelist: tuple[GiftPricelistItem, ...],
) -> CatalogSnapshot:
    prices_by_sku = {item.sku_id: item for item in pricelist}
    category_counts: Counter[int] = Counter()
    product_cards: list[StoreProductCard] = []

    for product in products:
        pricing_rows = [prices_by_sku[sku.sku_id] for sku in product.skus if sku.sku_id in prices_by_sku]
        fixed_prices = [item.price for item in pricing_rows if item.price is not None]
        min_price = min(fixed_prices) if fixed_prices else None
        max_price = max(fixed_prices) if fixed_prices else None
        currency = next((item.currency for item in pricing_rows if item.currency), None)
        total_stock = sum(max(item.stock, 0) for item in pricing_rows)
        buyable_sku_count = sum(1 for item in pricing_rows if item.price is not None and item.stock > 0)
        if product.category_id is not None:
            category_counts[product.category_id] += 1

        summary_parts = [strip_html(product.description or "")]
        if product.category_name:
            summary_parts.append(product.category_name)
        summary = shorten_plain_text(" ".join(part for part in summary_parts if part), 180)

        searchable_parts = [
            product.name,
            product.category_name or "",
            product.product_type,
            product.denomination_type or "",
            strip_html(product.description or ""),
        ]
        product_cards.append(
            StoreProductCard(
                product_id=product.product_id,
                name=product.name,
                product_type=product.product_type,
                denomination_type=product.denomination_type,
                category_id=product.category_id,
                category_name=product.category_name,
                summary=summary,
                min_price=min_price,
                max_price=max_price,
                currency=currency,
                total_stock=total_stock,
                sku_count=len(product.skus),
                buyable_sku_count=buyable_sku_count,
                searchable_text=normalize_text(" ".join(searchable_parts)),
            )
        )

    category_cards = tuple(
        sorted(
            (
                StoreCategoryCard(
                    category_id=category.category_id,
                    name=category.name,
                    product_count=category_counts.get(category.category_id, 0),
                )
                for category in categories
                if category_counts.get(category.category_id, 0) > 0
            ),
            key=lambda item: (-item.product_count, item.name.lower()),
        )
    )
    sorted_products = tuple(
        sorted(
            product_cards,
            key=lambda item: (
                (item.category_name or "").lower(),
                item.name.lower(),
            ),
        )
    )
    return CatalogSnapshot(
        categories=category_cards,
        products=sorted_products,
        products_by_id={item.product_id: item for item in sorted_products},
    )


def paginate_items(items: tuple[ItemT, ...], *, page: int, per_page: int) -> tuple[tuple[ItemT, ...], PageInfo]:
    page_info = build_page_info(total_items=len(items), page=page, per_page=per_page)
    start = (page_info.page - 1) * page_info.per_page
    end = start + page_info.per_page
    return items[start:end], page_info


def build_page_info(*, total_items: int, page: int, per_page: int) -> PageInfo:
    normalized_per_page = max(1, per_page)
    total_pages = max(1, math.ceil(total_items / normalized_per_page)) if total_items else 1
    normalized_page = min(max(1, page), total_pages)
    return PageInfo(
        page=normalized_page,
        total_pages=total_pages,
        per_page=normalized_per_page,
        total_items=total_items,
    )


def build_external_order_id(telegram_id: int) -> str:
    return f"CERBER-{telegram_id}-{uuid4().hex[:10].upper()}"


def normalize_search_query(value: str) -> str:
    normalized = normalize_text(value)
    if len(normalized) < 2:
        raise SearchQueryError(STORE_SERVICE_TEXT.SEARCH_QUERY_TOO_SHORT)
    return normalized


def normalize_text(value: str) -> str:
    return " ".join(value.lower().split())


def normalize_money_amount(amount: Decimal) -> Decimal:
    return amount.quantize(Decimal("0.01"))


def strip_html(value: str) -> str:
    import re

    return " ".join(re.sub(r"<[^>]+>", " ", value).split())


def shorten_plain_text(value: str, limit: int) -> str:
    normalized = " ".join(value.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 1].rstrip() + "…"


def format_money(amount: Decimal | None, currency: str) -> str:
    if amount is None:
        return f"{COMMON_TEXT.NOT_AVAILABLE} {currency}"
    normalized = normalize_money_amount(amount)
    text = format(normalized, "f").rstrip("0").rstrip(".")
    return f"{text} {currency}"


def build_purchase_description(
    *,
    product_name: str,
    order_total_amount: Decimal,
    order_currency: str,
    charged_amount: Decimal,
    wallet_currency: str,
) -> str:
    product_label = STORE_SERVICE_TEXT.purchase_label(product_name)
    if order_currency == wallet_currency:
        return product_label
    return (
        f"{product_label} "
        f"({format_money(order_total_amount, order_currency)} -> {format_money(charged_amount, wallet_currency)})"
    )


def to_order_card(order: UserOrder) -> StoreOrderCard:
    return StoreOrderCard(
        order_id=order.id,
        external_id=order.external_id,
        provider_order_id=order.provider_order_id,
        product_name=order.product_name,
        sku_name=order.sku_name,
        status=order.status,
        total_amount=Decimal(str(order.total_amount)),
        currency=order.currency,
        created_at=order.created_at,
    )


def to_order_view(order: UserOrder) -> StoreOrderView:
    return StoreOrderView(
        order_id=order.id,
        external_id=order.external_id,
        provider_order_id=order.provider_order_id,
        provider=order.provider,
        product_name=order.product_name,
        sku_name=order.sku_name,
        status=order.status,
        total_amount=Decimal(str(order.total_amount)),
        currency=order.currency,
        created_at=order.created_at,
        delivery_payload=order.delivery_payload,
        error_message=order.error_message,
    )