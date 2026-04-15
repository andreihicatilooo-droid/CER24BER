"""Удалён — провайдерный слой не используется в production."""
from cerber_bot.integrations.http import BaseHttpCatalogProvider
from cerber_bot.integrations.schemas import Product
from cerber_bot.texts import CATALOG_PROVIDER_TEXT


class RestCatalogProvider(BaseHttpCatalogProvider):
    def __init__(self, base_url: str, http_client: httpx.AsyncClient, token: str | None = None) -> None:
        super().__init__(name="rest-catalog", base_url=base_url, http_client=http_client, token=token)

    async def fetch_products(self) -> list[Product]:
        payload = await self.get_json("/products")
        rows = self.extract_rows(payload)
        products = []

        for row in rows:
            products.append(
                Product(
                    external_id=str(row.get("id") or row.get("sku") or row.get("external_id")),
                    provider=self.name,
                    title=str(row.get("name") or row.get("title") or CATALOG_PROVIDER_TEXT.UNTITLED_PRODUCT),
                    description=str(row.get("description") or ""),
                    price=self.to_decimal(row.get("price", 0)),
                    currency=str(row.get("currency") or "RUB"),
                    in_stock=self.to_int(row.get("stock")),
                    category=self.optional_string(row.get("category")),
                    url=self.optional_string(row.get("url")),
                    photo_url=self.optional_string(row.get("image")),
                )
            )

        return products

    def extract_rows(self, payload: object) -> Iterable[Mapping[str, object]]:
        if isinstance(payload, list):
            return [self.ensure_mapping(item, "REST provider item must be an object") for item in payload]

        body = self.ensure_mapping(payload, "REST provider payload must be an object")
        items = body.get("products") or body.get("items") or []
        if not isinstance(items, list):
            raise ProviderError("REST provider field products/items must be an array")
        return [self.ensure_mapping(item, "REST provider item must be an object") for item in items]

    @staticmethod
    def optional_string(value: object | None) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None