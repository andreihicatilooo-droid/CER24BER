import logging

import httpx

from cerber_bot.config import Settings
from cerber_bot.integrations.base import CatalogProvider
from cerber_bot.integrations.giftapi import GiftApiClient
from cerber_bot.integrations.providers.demo import DemoCatalogProvider
from cerber_bot.integrations.providers.giftapi_catalog import GiftApiCatalogProvider
from cerber_bot.integrations.providers.rest_catalog import RestCatalogProvider
from cerber_bot.integrations.providers.warehouse_catalog import WarehouseCatalogProvider


logger = logging.getLogger(__name__)


def build_providers(
    settings: Settings,
    http_client: httpx.AsyncClient,
    giftapi_client: GiftApiClient | None = None,
) -> list[CatalogProvider]:
    providers: list[CatalogProvider] = []

    if settings.enable_demo_provider:
        providers.append(DemoCatalogProvider())

    if settings.enable_giftapi_provider and giftapi_client is not None and giftapi_client.is_configured:
        providers.append(GiftApiCatalogProvider(giftapi_client))

    if settings.rest_provider_url:
        providers.append(
            RestCatalogProvider(
                base_url=settings.rest_provider_url,
                http_client=http_client,
                token=settings.rest_provider_token,
            )
        )

    if settings.warehouse_provider_url:
        providers.append(
            WarehouseCatalogProvider(
                base_url=settings.warehouse_provider_url,
                http_client=http_client,
                token=settings.warehouse_provider_token,
            )
        )

    provider_names = ", ".join(provider.name for provider in providers) or "none"
    logger.info("Loaded %s catalog providers: %s", len(providers), provider_names)
    return providers