"""Агрегатор каталогов из нескольких провайдеров.

Опрашивает все подключённые CatalogProvider и объединяет результаты
в единый CatalogSnapshot с кэшированием.
"""

import asyncio
import logging
from time import monotonic

from cerber_bot.integrations.base import CatalogProvider
from cerber_bot.integrations.schemas import CatalogSnapshot, ProviderResult, utcnow


logger = logging.getLogger(__name__)


class CatalogService:
    def __init__(self, providers: list[CatalogProvider], cache_ttl_seconds: int = 120) -> None:
        self.providers = providers
        self.cache_ttl_seconds = cache_ttl_seconds
        self._cached_snapshot: CatalogSnapshot | None = None
        self._cache_until = 0.0

    async def get_catalog(self, force_refresh: bool = False) -> CatalogSnapshot:
        current_time = monotonic()
        if not force_refresh and self._cached_snapshot is not None and current_time < self._cache_until:
            return self._cached_snapshot

        provider_results = await asyncio.gather(
            *(self._collect_provider(provider) for provider in self.providers),
        )

        products = []
        errors: dict[str, str] = {}
        for result in provider_results:
            products.extend(result.products)
            if result.error is not None:
                errors[result.provider_name] = result.error

        products.sort(key=lambda item: ((item.category or "").lower(), item.title.lower(), item.provider.lower()))

        snapshot = CatalogSnapshot(
            products=tuple(products),
            provider_count=len(self.providers),
            collected_at=utcnow(),
            errors=errors,
        )
        self._cached_snapshot = snapshot
        self._cache_until = current_time + self.cache_ttl_seconds
        return snapshot

    async def _collect_provider(self, provider: CatalogProvider) -> ProviderResult:
        try:
            return ProviderResult(provider_name=provider.name, products=tuple(await provider.fetch_products()))
        except Exception as error:
            logger.exception("Catalog provider %s failed", provider.name)
            return ProviderResult(provider_name=provider.name, products=(), error=str(error))