from collections.abc import Iterable, Mapping

import httpx

from cerber_bot.integrations.base import ProviderError
from cerber_bot.integrations.http import BaseHttpCatalogProvider
from cerber_bot.integrations.schemas import Product
from cerber_bot.texts import CATALOG_PROVIDER_TEXT


class WarehouseCatalogProvider(BaseHttpCatalogProvider):
    def __init__(self, base_url: str, http_client: httpx.AsyncClient, token: str | None = None) -> None:
        super().__init__(name="warehouse", base_url=base_url, http_client=http_client, token=token)

    async def fetch_products(self) -> list[Product]:
        payload = await self.get_json("/inventory")
        rows = self.extract_rows(payload)
        products = []

        for row in rows:
            products.append(
                Product(
                    external_id=str(row.get("sku") or row.get("id") or row.get("offer_id")),
                    provider=self.name,
                    title=str(row.get("title") or row.get("name") or CATALOG_PROVIDER_TEXT.UNTITLED_PRODUCT),
                    description=str(row.get("details") or row.get("description") or ""),
                    price=self.to_decimal(row.get("cost") or row.get("price") or 0),
                    currency=str(row.get("currency") or "RUB"),
                    in_stock=self.to_int(row.get("qty") or row.get("stock")),
                    category=self.optional_string(row.get("group") or row.get("category")),
                    url=self.optional_string(row.get("product_url") or row.get("url")),
                    photo_url=self.optional_string(row.get("photo") or row.get("image")),
                )
            )

        return products

    def extract_rows(self, payload: object) -> Iterable[Mapping[str, object]]:
        body = self.ensure_mapping(payload, "Warehouse provider payload must be an object")
        items = body.get("items") or body.get("results") or []
        if not isinstance(items, list):
            raise ProviderError("Warehouse provider field items/results must be an array")
        return [self.ensure_mapping(item, "Warehouse provider item must be an object") for item in items]

    @staticmethod
    def optional_string(value: object | None) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None