# Тест удалён — провайдерный слой удалён.
from cerber_bot.integrations.schemas import Product
from cerber_bot.services.catalog import CatalogService


class StubProvider(CatalogProvider):
    def __init__(self, name: str, products: list[Product]) -> None:
        self.name = name
        self.products = products
        self.calls = 0

    async def fetch_products(self) -> list[Product]:
        self.calls += 1
        return self.products


@pytest.mark.asyncio
async def test_catalog_service_merges_and_caches_results() -> None:
    service = CatalogService(
        providers=[
            StubProvider(
                "alpha",
                [
                    Product(
                        external_id="1",
                        provider="alpha",
                        title="Alpha Item",
                        price=Decimal("100.00"),
                    )
                ],
            ),
            StubProvider(
                "beta",
                [
                    Product(
                        external_id="2",
                        provider="beta",
                        title="Beta Item",
                        price=Decimal("200.00"),
                    )
                ],
            ),
        ],
        cache_ttl_seconds=60,
    )

    first_snapshot = await service.get_catalog()
    second_snapshot = await service.get_catalog()

    assert len(first_snapshot.products) == 2
    assert second_snapshot is first_snapshot
    assert service.providers[0].calls == 1
    assert service.providers[1].calls == 1