# Тест удалён — провайдерный слой удалён.
from cerber_bot.integrations.providers.giftapi_catalog import GiftApiCatalogProvider


class StubGiftApiClient:
    locale = "ru"

    async def list_all_products(self, **_: object) -> tuple[GiftProductSummary, ...]:
        return (
            GiftProductSummary(
                product_id="product-1",
                name="Apple gift card | USA",
                product_type="voucher",
                denomination_type="fixed",
                category_id=18,
                category_name="Gift Cards",
                description="<p>Apple card</p>",
                image="",
                skus=(
                    GiftSkuBasic(
                        sku_id="sku-fixed",
                        name="$30 Apple Gift Card",
                        attributes={"denomination": "30", "denomination_currency": "USD"},
                    ),
                    GiftSkuBasic(
                        sku_id="sku-custom",
                        name="Custom Apple Gift Card",
                        attributes={},
                    ),
                ),
            ),
        )

    async def list_all_pricelist(self, **_: object) -> tuple[GiftPricelistItem, ...]:
        return (
            GiftPricelistItem(
                sku_id="sku-fixed",
                denomination_type="fixed",
                price=Decimal("29.09"),
                currency="USD",
                stock=10,
                max_per_order=1,
            ),
            GiftPricelistItem(
                sku_id="sku-custom",
                denomination_type="custom",
                price=None,
                currency="USD",
                stock=99,
                max_per_order=5,
                markup_percent=Decimal("35"),
            ),
        )


@pytest.mark.asyncio
async def test_giftapi_catalog_provider_maps_fixed_price_skus_only() -> None:
    provider = GiftApiCatalogProvider(StubGiftApiClient())

    products = await provider.fetch_products()

    assert len(products) == 1
    assert products[0].external_id == "sku-fixed"
    assert products[0].provider == "giftapi"
    assert products[0].price == Decimal("29.09")
    assert products[0].in_stock == 10
    assert products[0].category == "Gift Cards"
    assert "Номинал: 30 USD" in products[0].description