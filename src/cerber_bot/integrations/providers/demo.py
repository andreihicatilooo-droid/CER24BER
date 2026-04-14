from decimal import Decimal

from cerber_bot.integrations.base import CatalogProvider
from cerber_bot.integrations.schemas import Product
from cerber_bot.texts import DEMO_CATALOG_TEXT


class DemoCatalogProvider(CatalogProvider):
    name = "demo"

    async def fetch_products(self) -> list[Product]:
        return [
            Product(
                external_id="cerber-demo-1",
                provider=self.name,
                title=DEMO_CATALOG_TEXT.STARTER_TITLE,
                description=DEMO_CATALOG_TEXT.STARTER_DESCRIPTION,
                price=Decimal("1990.00"),
                currency="RUB",
                in_stock=12,
                category=DEMO_CATALOG_TEXT.STARTER_CATEGORY,
            ),
            Product(
                external_id="cerber-demo-2",
                provider=self.name,
                title=DEMO_CATALOG_TEXT.PREMIUM_TITLE,
                description=DEMO_CATALOG_TEXT.PREMIUM_DESCRIPTION,
                price=Decimal("5490.00"),
                currency="RUB",
                in_stock=4,
                category=DEMO_CATALOG_TEXT.PREMIUM_CATEGORY,
            ),
            Product(
                external_id="cerber-demo-3",
                provider=self.name,
                title=DEMO_CATALOG_TEXT.DIGITAL_KEY_TITLE,
                description=DEMO_CATALOG_TEXT.DIGITAL_KEY_DESCRIPTION,
                price=Decimal("890.00"),
                currency="RUB",
                in_stock=120,
                category=DEMO_CATALOG_TEXT.DIGITAL_KEY_CATEGORY,
            ),
        ]