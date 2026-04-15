"""Удалён — провайдерный слой не используется в production."""
from cerber_bot.integrations.giftapi import GiftApiClient, GiftPricelistItem, GiftProductSummary, GiftSkuBasic
from cerber_bot.integrations.schemas import Product
from cerber_bot.texts import CATALOG_PROVIDER_TEXT


HTML_TAG_RE = re.compile(r"<[^>]+>")


class GiftApiCatalogProvider(CatalogProvider):
    name = "giftapi"

    def __init__(self, client: GiftApiClient) -> None:
        self.client = client

    async def fetch_products(self) -> list[Product]:
        product_rows, price_rows = await asyncio.gather(
            self.client.list_all_products(include_skus=True, per_page=200),
            self.client.list_all_pricelist(per_page=200),
        )
        prices_by_sku = {item.sku_id: item for item in price_rows}

        products: list[Product] = []
        for product in product_rows:
            for sku in product.skus:
                price_item = prices_by_sku.get(sku.sku_id)
                if price_item is None or price_item.price is None:
                    continue
                products.append(self._to_catalog_product(product, sku, price_item))

        return products

    def _to_catalog_product(
        self,
        product: GiftProductSummary,
        sku: GiftSkuBasic,
        price_item: GiftPricelistItem,
    ) -> Product:
        title = product.name if sku.name == product.name else f"{product.name} / {sku.name}"
        description_parts = []
        if product.description:
            description_parts.append(self._strip_html(product.description))
        denomination = sku.attributes.get("denomination")
        denomination_currency = sku.attributes.get("denomination_currency")
        if denomination and denomination_currency:
            description_parts.append(CATALOG_PROVIDER_TEXT.giftapi_denomination(denomination, denomination_currency))
        if price_item.max_per_order is not None:
            description_parts.append(CATALOG_PROVIDER_TEXT.giftapi_max_per_order(price_item.max_per_order))

        return Product(
            external_id=sku.sku_id,
            provider=self.name,
            title=title,
            price=price_item.price,
            description="\n".join(part for part in description_parts if part),
            currency=price_item.currency,
            in_stock=price_item.stock,
            category=product.category_name,
            photo_url=sku.image or product.image,
        )

    @staticmethod
    def _strip_html(value: str) -> str:
        return " ".join(HTML_TAG_RE.sub(" ", value).split())