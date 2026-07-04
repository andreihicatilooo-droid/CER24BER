"""Контейнер зависимостей приложения.

Собирает все сервисы, репозитории и клиенты в единый объект AppContainer,
который передаётся в роутеры и обработчики.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from cerber_bot.config import Settings, load_settings
from cerber_bot.db.session import create_engine, create_session_factory, ensure_database_parent, init_database
from cerber_bot.integrations.cerber_core import CerberCoreClient
from cerber_bot.integrations.giftapi import GiftApiClient
from cerber_bot.integrations.getmytg import GetMyTGClient
from cerber_bot.integrations.nbox_service import NboxService
from cerber_bot.integrations.nicepay import NicePayClient
from cerber_bot.integrations.rukassa import RukassaClient
from cerber_bot.services.deals import DealService
from cerber_bot.services.admin_events import AdminEventService
from cerber_bot.services.admin_group import AdminGroupService
from cerber_bot.services.referrals import ReferralService
from cerber_bot.services.exchange import ExchangeRateService
from cerber_bot.services.giftapi import GiftApiService
from cerber_bot.services.ledger import LedgerService
from CRP.service import ReputationService
from cerber_bot.services.payments import PaymentService
from cerber_bot.services.store import StoreService
from cerber_bot.services.tgaccounts import TgAccountService
from cerber_bot.services.users import UserService
from cerber_bot.services.wallet_read import WalletReadService


@dataclass(slots=True)
class AppContainer:
    settings: Settings
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    http_client: httpx.AsyncClient
    nicepay_http_client: httpx.AsyncClient
    exchange_rate_service: ExchangeRateService
    admin_event_service: AdminEventService
    gift_api_service: GiftApiService
    reputation_service: ReputationService
    cerber_core_client: CerberCoreClient | None
    ledger_service: LedgerService | None
    getmytg_client: GetMyTGClient | None
    tgaccounts_service: TgAccountService | None
    deal_service: DealService
    payment_service: PaymentService
    store_service: StoreService
    nbox_service: NboxService
    user_service: UserService
    referral_service: ReferralService
    admin_group_service: AdminGroupService

    @classmethod
    async def build(cls, settings: Settings | None = None) -> "AppContainer":
        resolved_settings = settings or load_settings()
        resolved_settings.validate_billing_configuration()
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
        cerber_core_client: CerberCoreClient | None = None
        if resolved_settings.is_core_first_billing or resolved_settings.cerber_core_enabled:
            cerber_core_client = CerberCoreClient(
                base_url=resolved_settings.cerber_core_base_url,
                http_client=http_client,
                api_key=resolved_settings.cerber_core_api_key,
                secret_key=resolved_settings.cerber_core_secret_key,
            )
        ledger_service: LedgerService | None = None
        if resolved_settings.is_core_first_billing:
            ledger_service = LedgerService.from_client(cerber_core_client)
        exchange_rate_service = ExchangeRateService(
            http_client=http_client,
            api_url=resolved_settings.exchange_rate_api_url,
            cache_ttl_seconds=resolved_settings.exchange_rate_cache_ttl,
            fallback_usdt_rub_rate=resolved_settings.fallback_usdt_rub_rate,
        )
        reputation_service = ReputationService(session_factory)
        wallet_read_service = WalletReadService(
            session_factory=session_factory,
            exchange_rate_service=exchange_rate_service,
            wallet_currency=resolved_settings.wallet_currency,
            ledger_service=ledger_service,
        )
        getmytg_client: GetMyTGClient | None = None
        if resolved_settings.getmytg_api_key:
            getmytg_client = GetMyTGClient(
                base_url=resolved_settings.getmytg_base_url,
                http_client=http_client,
                api_key=resolved_settings.getmytg_api_key,
            )
        tgaccounts_service = TgAccountService(
            client=getmytg_client or GetMyTGClient(
                base_url=resolved_settings.getmytg_base_url,
                http_client=http_client,
                api_key=None,
            ),
            session_factory=session_factory,
            exchange_rate_service=exchange_rate_service,
            ledger_service=ledger_service,
        )
        nicepay_client = NicePayClient(
            base_url=resolved_settings.nicepay_base_url,
            http_client=nicepay_http_client,
            merchant_id=resolved_settings.nicepay_merchant_id,
            secret=resolved_settings.nicepay_secret,
        )
        rukassa_client: RukassaClient | None = None
        if resolved_settings.rukassa_shop_id and resolved_settings.rukassa_token:
            rukassa_client = RukassaClient(
                base_url=resolved_settings.rukassa_base_url,
                http_client=http_client,
                shop_id=resolved_settings.rukassa_shop_id,
                token=resolved_settings.rukassa_token,
            )
        payment_service = PaymentService(
            session_factory=session_factory,
            nicepay_client=nicepay_client,
            rukassa_client=rukassa_client,
            exchange_rate_service=exchange_rate_service,
            wallet_currency=resolved_settings.wallet_currency,
            payment_currency=resolved_settings.payments_currency,
            title=resolved_settings.payments_title,
            description=resolved_settings.payments_description,
            min_amount=resolved_settings.payments_min_amount,
            max_amount=resolved_settings.payments_max_amount,
            success_url=resolved_settings.rukassa_success_url if rukassa_client else resolved_settings.nicepay_success_url,
            fail_url=resolved_settings.rukassa_fail_url if rukassa_client else resolved_settings.nicepay_fail_url,
            method=resolved_settings.nicepay_method,
            stars_enabled=resolved_settings.stars_enabled,
            stars_to_usd_rate=resolved_settings.stars_to_usd_rate,
            cerber_core_client=cerber_core_client,
            cerber_core_topup_method_code=resolved_settings.cerber_core_topup_method_code,
            ledger_service=ledger_service,
        )
        store_service = StoreService(
            session_factory=session_factory,
            gift_api_service=gift_api_service,
            gift_api_client=giftapi_client,
            exchange_rate_service=exchange_rate_service,
            cache_ttl_seconds=resolved_settings.catalog_cache_ttl,
            wallet_currency=resolved_settings.wallet_currency,
            wallet_read_service=wallet_read_service,
            ledger_service=ledger_service,
        )
        deal_service = DealService(
            session_factory=session_factory,
            exchange_rate_service=exchange_rate_service,
            wallet_currency=resolved_settings.wallet_currency,
            moderator_ids=resolved_settings.moderator_ids,
            withdrawal_min_amount_usdt=resolved_settings.withdrawal_min_amount_usdt,
            withdrawal_networks=resolved_settings.withdrawal_networks,
            wallet_read_service=wallet_read_service,
            ledger_service=ledger_service,
            reputation_service=reputation_service,
        )
        user_service = UserService(
            session_factory,
            default_balance_currency=resolved_settings.wallet_currency,
            ledger_service=ledger_service,
            exchange_rate_service=exchange_rate_service,
        )

        return cls(
            settings=resolved_settings,
            engine=engine,
            session_factory=session_factory,
            http_client=http_client,
            nicepay_http_client=nicepay_http_client,
            exchange_rate_service=exchange_rate_service,
            admin_event_service=AdminEventService(
                session_factory,
                moderator_ids=resolved_settings.moderator_ids,
            ),
            gift_api_service=gift_api_service,
            reputation_service=reputation_service,
            cerber_core_client=cerber_core_client,
            ledger_service=ledger_service,
            getmytg_client=getmytg_client,
            tgaccounts_service=tgaccounts_service,
            deal_service=deal_service,
            payment_service=payment_service,
            store_service=store_service,
            nbox_service=NboxService(),
            user_service=user_service,
            referral_service=ReferralService(
                session_factory,
                bot_username=resolved_settings.bot_username,
            ),
            admin_group_service=AdminGroupService(session_factory),
        )

    def build_user_service(self) -> UserService:
        return self.user_service

    async def close(self) -> None:
        await self.nicepay_http_client.aclose()
        await self.http_client.aclose()
        await self.engine.dispose()
