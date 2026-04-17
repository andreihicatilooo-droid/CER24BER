from decimal import Decimal
from pathlib import Path

import pytest
from aiogram.types import User

from cerber_bot.db.repositories.orders import UserOrderRepository
from cerber_bot.db.session import create_engine, create_session_factory, init_database
from cerber_bot.integrations.giftapi import (
    GiftCategory,
    GiftOrder,
    GiftOrderItem,
    GiftPricelistItem,
    GiftProductDetail,
    GiftProductSummary,
    GiftRequiredField,
    GiftSkuBasic,
    GiftSkuDetail,
)
from cerber_bot.services.exchange import WalletQuote
from cerber_bot.services.store import InsufficientBalanceError, StoreService, StoreServiceError


class StubGiftApiClient:
    def __init__(self) -> None:
        self.locale = "ru"

    async def list_categories(self) -> tuple[GiftCategory, ...]:
        return (
            GiftCategory(category_id=1, name="Gift Cards"),
            GiftCategory(category_id=2, name="Gaming"),
        )

    async def list_all_products(self, **_: object) -> tuple[GiftProductSummary, ...]:
        return (
            GiftProductSummary(
                product_id="product-apple-1",
                name="Apple Gift Card 10",
                product_type="voucher",
                denomination_type="fixed",
                category_id=1,
                category_name="Gift Cards",
                description="Apple value card",
                image=None,
                skus=(GiftSkuBasic(sku_id="sku-apple-10", name="$10 Apple", attributes={}),),
            ),
            GiftProductSummary(
                product_id="product-apple-2",
                name="Apple Gift Card 20",
                product_type="voucher",
                denomination_type="fixed",
                category_id=1,
                category_name="Gift Cards",
                description="Apple premium card",
                image=None,
                skus=(GiftSkuBasic(sku_id="sku-apple-20", name="$20 Apple", attributes={}),),
            ),
            GiftProductSummary(
                product_id="product-steam-1",
                name="Steam Wallet 50",
                product_type="voucher",
                denomination_type="fixed",
                category_id=2,
                category_name="Gaming",
                description="Steam wallet voucher",
                image=None,
                skus=(GiftSkuBasic(sku_id="sku-steam-50", name="$50 Steam", attributes={}),),
            ),
        )

    async def list_all_pricelist(self, **_: object) -> tuple[GiftPricelistItem, ...]:
        return (
            GiftPricelistItem(
                sku_id="sku-apple-10",
                denomination_type="fixed",
                price=Decimal("10.00"),
                currency="USD",
                stock=10,
                max_per_order=1,
            ),
            GiftPricelistItem(
                sku_id="sku-apple-20",
                denomination_type="fixed",
                price=Decimal("20.00"),
                currency="USD",
                stock=7,
                max_per_order=1,
            ),
            GiftPricelistItem(
                sku_id="sku-steam-50",
                denomination_type="fixed",
                price=Decimal("50.00"),
                currency="USD",
                stock=3,
                max_per_order=1,
            ),
        )


class StubGiftApiService:
    def ensure_configured(self, require_secret: bool = False) -> None:
        return None

    async def get_product_detail(self, product_uuid: str) -> GiftProductDetail:
        if product_uuid != "product-apple-1":
            raise AssertionError(f"Unexpected product request: {product_uuid}")
        return GiftProductDetail(
            product_id="product-apple-1",
            name="Apple Gift Card 10",
            product_type="voucher",
            denomination_type="fixed",
            category_name="Gift Cards",
            description="Apple value card",
            image=None,
            required_fields=(
                GiftRequiredField(
                    code="quantity",
                    field_type="integer",
                    name="Quantity",
                    description=None,
                    required=True,
                ),
            ),
            skus=(
                GiftSkuDetail(
                    sku_id="sku-apple-10",
                    name="$10 Apple",
                    price=Decimal("10.00"),
                    currency="USD",
                    stock=10,
                    max_per_order=1,
                    attributes={},
                ),
            ),
        )

    async def create_order(self, draft) -> GiftOrder:
        assert draft.sku_id == "sku-apple-10"
        assert draft.fields == {"quantity": 1}
        return GiftOrder(
            order_id="giftapi-order-1",
            external_id=draft.external_id,
            status="completed",
            total_amount=Decimal("10.00"),
            currency="USD",
            created_at=None,
            items=(
                GiftOrderItem(
                    sku_id="sku-apple-10",
                    sku_name="$10 Apple",
                    quantity=1,
                    price=Decimal("10.00"),
                    currency="USD",
                    status="completed",
                    delivery_data=({"pin": "CODE-123"},),
                    customer_data=None,
                    error_message=None,
                ),
            ),
        )


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


@pytest.mark.asyncio
async def test_store_service_supports_search_and_pagination(tmp_path: Path) -> None:
    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'store.db').as_posix()}"
    engine = create_engine(database_url)
    session_factory = create_session_factory(engine)
    await init_database(engine)

    service = StoreService(
        session_factory=session_factory,
        gift_api_service=StubGiftApiService(),
        gift_api_client=StubGiftApiClient(),
        exchange_rate_service=StubExchangeRateService(),
        cache_ttl_seconds=60,
    )

    categories, categories_page = await service.get_categories_page(page=1, per_page=1)
    products, products_page = await service.get_products_page(page=1, per_page=2)
    search_results, search_page = await service.get_products_page(page=1, per_page=5, search_query="apple")

    assert len(categories) == 1
    assert categories_page.total_pages == 2
    assert len(products) == 2
    assert products_page.total_pages == 2
    assert len(search_results) == 2
    assert search_page.total_pages == 1

    await engine.dispose()


@pytest.mark.asyncio
async def test_store_service_top_up_and_purchase_updates_wallet_and_orders(tmp_path: Path) -> None:
    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'wallet.db').as_posix()}"
    engine = create_engine(database_url)
    session_factory = create_session_factory(engine)
    await init_database(engine)

    service = StoreService(
        session_factory=session_factory,
        gift_api_service=StubGiftApiService(),
        gift_api_client=StubGiftApiClient(),
        exchange_rate_service=StubExchangeRateService(),
        cache_ttl_seconds=60,
    )
    telegram_user = User(
        id=123456789,
        is_bot=False,
        first_name="Ivan",
        last_name="Petrov",
        username="cerber_client",
        language_code="ru",
    )

    wallet_after_top_up = await service.top_up_balance(telegram_user, Decimal("25.00"))
    purchase = await service.purchase_offer(
        telegram_user,
        product_id="product-apple-1",
        sku_id="sku-apple-10",
    )
    wallet_after_purchase = await service.get_wallet_snapshot(telegram_user.id)
    orders, orders_page = await service.get_orders_page(telegram_user.id, page=1, per_page=5)

    assert wallet_after_top_up.balance == Decimal("25.00")
    assert purchase.balance_after == Decimal("15.00")
    assert wallet_after_purchase.balance == Decimal("15.00")
    assert len(wallet_after_purchase.recent_transactions) == 2
    assert orders_page.total_items == 1
    assert len(orders) == 1
    assert orders[0].product_name == "Apple Gift Card 10"

    await engine.dispose()


@pytest.mark.asyncio
async def test_store_service_manual_balance_adjustment_updates_wallet(tmp_path: Path) -> None:
    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'manual-balance.db').as_posix()}"
    engine = create_engine(database_url)
    session_factory = create_session_factory(engine)
    await init_database(engine)

    service = StoreService(
        session_factory=session_factory,
        gift_api_service=StubGiftApiService(),
        gift_api_client=StubGiftApiClient(),
        exchange_rate_service=StubExchangeRateService(),
        cache_ttl_seconds=60,
    )
    telegram_user = User(
        id=987654321,
        is_bot=False,
        first_name="Dev",
        last_name="User",
        username="XRAYOG",
        language_code="ru",
    )

    wallet_after_credit = await service.adjust_balance(telegram_user, Decimal("40.00"), transaction_type="manual_credit")
    wallet_after_debit = await service.adjust_balance(telegram_user, Decimal("-15.50"), transaction_type="manual_debit")

    assert wallet_after_credit.balance == Decimal("40.00")
    assert wallet_after_debit.balance == Decimal("24.50")
    assert wallet_after_debit.recent_transactions[0].transaction_type == "manual_debit"
    assert wallet_after_debit.recent_transactions[0].amount == Decimal("-15.50")
    assert wallet_after_debit.recent_transactions[1].transaction_type == "manual_credit"

    with pytest.raises(InsufficientBalanceError):
        await service.adjust_balance(telegram_user, Decimal("-50.00"), transaction_type="manual_debit")

    with pytest.raises(StoreServiceError):
        await service.adjust_balance(telegram_user, Decimal("0.00"), transaction_type="manual_credit")

    await engine.dispose()


@pytest.mark.asyncio
async def test_order_repository_top_product_ids(tmp_path: Path) -> None:
    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'top-products.db').as_posix()}"
    engine = create_engine(database_url)
    session_factory = create_session_factory(engine)
    await init_database(engine)

    async with session_factory() as session:
        repo = UserOrderRepository(session)
        from cerber_bot.db.models import UserOrder, utcnow

        def make_order(product_id: str, provider: str, status: str) -> UserOrder:
            import uuid
            now = utcnow()
            return UserOrder(
                telegram_id=1,
                external_id=str(uuid.uuid4()),
                provider_order_id=None,
                provider=provider,
                product_id=product_id,
                product_name=f"Product {product_id}",
                sku_id="sku-1",
                sku_name="SKU 1",
                status=status,
                total_amount=Decimal("10.00"),
                currency="RUB",
                delivery_payload=None,
                error_message=None,
                created_at=now,
                updated_at=now,
            )

        # product-A — 3 completed, product-B — 1 completed, product-C — 2 completed
        # product-D — 5 покупок, но статус error — не должен попасть
        for _ in range(3):
            session.add(make_order("product-A", "giftapi", "completed"))
        session.add(make_order("product-B", "giftapi", "completed"))
        for _ in range(2):
            session.add(make_order("product-C", "giftapi", "completed"))
        for _ in range(5):
            session.add(make_order("product-D", "giftapi", "error"))
        # product-E — completed, но другой провайдер
        session.add(make_order("product-E", "demo", "completed"))
        await session.commit()

        # Без фильтра провайдера: A(3), C(2), B(1), E(1)
        top_all = await repo.top_product_ids(limit=10)
        assert top_all[0] == "product-A"
        assert top_all[1] == "product-C"
        assert "product-D" not in top_all

        # С фильтром по giftapi: E не попадает
        top_giftapi = await repo.top_product_ids(limit=10, provider="giftapi")
        assert "product-E" not in top_giftapi
        assert top_giftapi[0] == "product-A"

        # limit=1
        top_one = await repo.top_product_ids(limit=1)
        assert len(top_one) == 1
        assert top_one[0] == "product-A"

    await engine.dispose()


@pytest.mark.asyncio
async def test_order_repository_top_product_ids(tmp_path: Path) -> None:
    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'top-products.db').as_posix()}"
    engine = create_engine(database_url)
    session_factory = create_session_factory(engine)
    await init_database(engine)

    async with session_factory() as session:
        repo = UserOrderRepository(session)
        from cerber_bot.db.models import UserOrder, utcnow

        def make_order(product_id: str, provider: str, status: str) -> UserOrder:
            import uuid
            now = utcnow()
            return UserOrder(
                telegram_id=1,
                external_id=str(uuid.uuid4()),
                provider_order_id=None,
                provider=provider,
                product_id=product_id,
                product_name=f"Product {product_id}",
                sku_id="sku-1",
                sku_name="SKU 1",
                status=status,
                total_amount=Decimal("10.00"),
                currency="RUB",
                delivery_payload=None,
                error_message=None,
                created_at=now,
                updated_at=now,
            )

        # product-A — 3 completed, product-B — 1 completed, product-C — 2 completed
        # product-D — 5 покупок, но статус error — не должен попасть
        for _ in range(3):
            session.add(make_order("product-A", "giftapi", "completed"))
        session.add(make_order("product-B", "giftapi", "completed"))
        for _ in range(2):
            session.add(make_order("product-C", "giftapi", "completed"))
        for _ in range(5):
            session.add(make_order("product-D", "giftapi", "error"))
        # product-E — completed, но другой провайдер
        session.add(make_order("product-E", "demo", "completed"))
        await session.commit()

        # Без фильтра провайдера: A(3), C(2), B(1), E(1)
        top_all = await repo.top_product_ids(limit=10)
        assert top_all[0] == "product-A"
        assert top_all[1] == "product-C"
        assert "product-D" not in top_all

        # С фильтром по giftapi: E не попадает
        top_giftapi = await repo.top_product_ids(limit=10, provider="giftapi")
        assert "product-E" not in top_giftapi
        assert top_giftapi[0] == "product-A"

        # limit=1
        top_one = await repo.top_product_ids(limit=1)
        assert len(top_one) == 1
        assert top_one[0] == "product-A"

    await engine.dispose()

@pytest.mark.asyncio
async def test_store_service_get_featured_products(tmp_path: Path) -> None:
    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'featured.db').as_posix()}"
    engine = create_engine(database_url)
    session_factory = create_session_factory(engine)
    await init_database(engine)

    service = StoreService(
        session_factory=session_factory,
        gift_api_service=StubGiftApiService(),
        gift_api_client=StubGiftApiClient(),
        exchange_rate_service=StubExchangeRateService(),
        cache_ttl_seconds=60,
    )

    # Пустая БД — пустой результат
    featured_empty = await service.get_featured_products()
    assert featured_empty == ()

    # steam-1 — 3 покупки, apple-1 — 1, unknown-999 — 5 (нет в каталоге -> не попадает)
    async with session_factory() as session:
        from cerber_bot.db.models import UserOrder, utcnow
        import uuid

        def _order(product_id: str, provider: str = "giftapi") -> UserOrder:
            now = utcnow()
            return UserOrder(
                telegram_id=1,
                external_id=str(uuid.uuid4()),
                provider_order_id=None,
                provider=provider,
                product_id=product_id,
                product_name=product_id,
                sku_id="sku-1",
                sku_name="SKU",
                status="completed",
                total_amount=Decimal("10.00"),
                currency="USD",
                delivery_payload=None,
                error_message=None,
                created_at=now,
                updated_at=now,
            )

        for _ in range(3):
            session.add(_order("product-steam-1"))
        session.add(_order("product-apple-1"))
        for _ in range(2):
            session.add(_order("product-unknown-999"))
        await session.commit()

    service._cached_snapshot = None
    featured = await service.get_featured_products(limit=10)
    product_ids = [p.product_id for p in featured]

    assert product_ids[0] == "product-steam-1"
    assert product_ids[1] == "product-apple-1"
    assert "product-unknown-999" not in product_ids

    featured_one = await service.get_featured_products(limit=1)
    assert len(featured_one) == 1
    assert featured_one[0].product_id == "product-steam-1"

    await engine.dispose()
