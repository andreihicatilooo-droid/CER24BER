from abc import ABC, abstractmethod

from cerber_bot.integrations.schemas import Product


class ProviderError(RuntimeError):
    pass


class CatalogProvider(ABC):
    name: str

    @abstractmethod
    async def fetch_products(self) -> list[Product]:
        raise NotImplementedError