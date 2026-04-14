"""Контейнер зависимостей приложения.

Собирает все сервисы, репозитории и клиенты в единый объект AppContainer,
который передаётся в роутеры и обработчики.
"""

from dataclasses import dataclass

import httpx
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from cerber_bot.config import Settings, load_settings
from cerber_bot.db.session import create_engine, create_session_factory, ensure_database_parent, init_database
from cerber_bot.integrations.giftapi import GiftApiClient
from cerber_bot.integrations.nicepay import NicePayClient
from cerber_bot.integrations.registry import build_providers
from cerber_bot.services.catalog import CatalogService
from cerber_bot.services.deals import DealService
from cerber_bot.services.exchange import ExchangeRateService
from cerber_bot.services.giftapi import GiftApiService
from cerber_bot.services.payments import PaymentService
from cerber_bot.services.store import StoreService
from cerber_bot.services.users import UserService


@dataclass(slots=True)
class AppContainer:
    settings: Settings
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    http_client: httpx.AsyncClient
    nicepay_http_client: httpx.AsyncClient
    catalog_service: CatalogService
    exchange_rate_service: ExchangeRateService
    gift_api_service: GiftApiService
    deal_service: DealService
    payment_service: PaymentService
    store_service: StoreService

    @classmethod
    async def build(cls, settings: Settings | None = None) -> "AppContainer":
        resolved_settings = settings or load_settings()
        ensure_database_parent(resolved_settings.database_url)

        engine = create_engine(resolved_settings.database_url)
        session_factory = create_session_factory(engine)
        await init_database(engine)

        http_client = httpx.AsyncClient(
            timeout=resolved_settings.request_timeout_seconds,
            trust_env=False,
        )
        nicepay_http_client = httpx.AsyncClient(
            timeout=resolved_settings.request_timeout_seconds,
            proxy=resolved_settings.nicepay_proxy or None,
            trust_env=False,
        )
        giftapi_client = GiftApiClient(
            base_url=resolved_settings.giftapi_base_url,
            http_client=http_client,
            token=resolved_settings.giftapi_token,
            secret=resolved_settings.giftapi_secret,
            locale=resolved_settings.giftapi_locale,
        )
        gift_api_service = GiftApiService(giftapi_client)
        exchange_rate_service = ExchangeRateService(
            http_client=http_client,
            api_url=resolved_settings.exchange_rate_api_url,
            cache_ttl_seconds=resolved_settings.exchange_rate_cache_ttl,
            fallback_usdt_rub_rate=resolved_settings.fallback_usdt_rub_rate,
        )
        nicepay_client = NicePayClient(
            base_url=resolved_settings.nicepay_base_url,
            http_client=nicepay_http_client,
            merchant_id=resolved_settings.nicepay_merchant_id,
            secret=resolved_settings.nicepay_secret,
        )
        payment_service = PaymentService(
            session_factory=session_factory,
            nicepay_client=nicepay_client,
            exchange_rate_service=exchange_rate_service,
            wallet_currency=resolved_settings.wallet_currency,
            payment_currency=resolved_settings.payments_currency,
            title=resolved_settings.payments_title,
            description=resolved_settings.payments_description,
            min_amount=resolved_settings.payments_min_amount,
            max_amount=resolved_settings.payments_max_amount,
            success_url=resolved_settings.nicepay_success_url,
            fail_url=resolved_settings.nicepay_fail_url,
            method=resolved_settings.nicepay_method,
        )
        store_service = StoreService(
            session_factory=session_factory,
            gift_api_service=gift_api_service,
            gift_api_client=giftapi_client,
            exchange_rate_service=exchange_rate_service,
            cache_ttl_seconds=resolved_settings.catalog_cache_ttl,
            wallet_currency=resolved_settings.wallet_currency,
        )
        deal_service = DealService(
            session_factory=session_factory,
            exchange_rate_service=exchange_rate_service,
            wallet_currency=resolved_settings.wallet_currency,
            moderator_ids=resolved_settings.moderator_ids,
            withdrawal_min_amount_usdt=resolved_settings.withdrawal_min_amount_usdt,
            withdrawal_networks=resolved_settings.withdrawal_networks,
        )
        providers = build_providers(resolved_settings, http_client, giftapi_client=giftapi_client)
        catalog_service = CatalogService(
            providers=providers,
            cache_ttl_seconds=resolved_settings.catalog_cache_ttl,
        )

        return cls(
            settings=resolved_settings,
            engine=engine,
            session_factory=session_factory,
            http_client=http_client,
            nicepay_http_client=nicepay_http_client,
            catalog_service=catalog_service,
            exchange_rate_service=exchange_rate_service,
            gift_api_service=gift_api_service,
            deal_service=deal_service,
            payment_service=payment_service,
            store_service=store_service,
        )

    def build_user_service(self) -> UserService:
        return UserService(self.session_factory, default_balance_currency=self.settings.wallet_currency)

    async def close(self) -> None:
        await self.nicepay_http_client.aclose()
        await self.http_client.aclose()
        await self.engine.dispose()