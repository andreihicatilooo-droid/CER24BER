"""Бизнес-сервис GiftAPI.

Обёртка над GiftApiClient с проверкой конфигурации,
парсингом JSON-заказов и форматированием данных для хэндлеров.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass

from cerber_bot.integrations.giftapi import (
    GiftApiClient,
    GiftApiConfigurationError,
    GiftApiError,
    GiftBalanceTransaction,
    GiftCategory,
    GiftCursorMeta,
    GiftEsimStatus,
    GiftOrder,
    GiftPartner,
    GiftProductDetail,
    GiftProductSummary,
)
from cerber_bot.texts import GIFTAPI_SERVICE_TEXT


@dataclass(slots=True, frozen=True)
class GiftApiOverview:
    partner: GiftPartner
    recent_transactions: tuple[GiftBalanceTransaction, ...]


@dataclass(slots=True, frozen=True)
class GiftApiOrderDraft:
    external_id: str
    sku_id: str
    fields: dict[str, object]
    metadata: dict[str, object] | None = None


class GiftApiService:
    def __init__(self, client: GiftApiClient) -> None:
        self.client = client

    @property
    def is_configured(self) -> bool:
        return self.client.is_configured

    def configuration_message(self, require_secret: bool = False) -> str:
        missing = ["GIFTAPI_BASE_URL", "GIFTAPI_TOKEN"]
        if require_secret:
            missing.append("GIFTAPI_SECRET")
        return GIFTAPI_SERVICE_TEXT.configuration_message(missing)

    def ensure_configured(self, require_secret: bool = False) -> None:
        self.client.ensure_configured(require_secret=require_secret)

    async def get_overview(self) -> GiftApiOverview:
        self.ensure_configured()
        partner = await self.client.get_partner_profile()
        transactions, _ = await self.client.get_balance_history(per_page=5)
        return GiftApiOverview(partner=partner, recent_transactions=transactions)

    async def get_categories(self) -> tuple[GiftCategory, ...]:
        self.ensure_configured()
        return await self.client.list_categories()

    async def get_products(self) -> tuple[tuple[GiftProductSummary, ...], GiftCursorMeta]:
        self.ensure_configured()
        return await self.client.list_products(include_skus=True, per_page=12)

    async def get_product_detail(self, product_uuid: str) -> GiftProductDetail:
        self.ensure_configured()
        return await self.client.get_product_detail(product_uuid)

    async def get_orders(self) -> tuple[tuple[GiftOrder, ...], GiftCursorMeta]:
        self.ensure_configured()
        return await self.client.list_orders(per_page=8)

    async def get_order(self, order_uuid: str) -> GiftOrder:
        self.ensure_configured()
        return await self.client.get_order(order_uuid)

    async def create_order(self, draft: GiftApiOrderDraft) -> GiftOrder:
        self.ensure_configured(require_secret=True)
        return await self.client.create_order(
            external_id=draft.external_id,
            sku_id=draft.sku_id,
            fields=draft.fields,
            metadata=draft.metadata,
        )

    async def get_esim_status(self, iccid: str) -> GiftEsimStatus:
        self.ensure_configured()
        return await self.client.get_esim_status(iccid)

    def parse_order_payload(self, raw_text: str) -> GiftApiOrderDraft:
        try:
            payload = json.loads(raw_text)
        except json.JSONDecodeError as error:
            raise ValueError(GIFTAPI_SERVICE_TEXT.INVALID_ORDER_JSON) from error

        if not isinstance(payload, Mapping):
            raise ValueError(GIFTAPI_SERVICE_TEXT.ORDER_JSON_OBJECT)

        external_id = self._required_string(payload.get("external_id"), "external_id")
        item = payload.get("item")
        if not isinstance(item, Mapping):
            raise ValueError(GIFTAPI_SERVICE_TEXT.ORDER_ITEM_OBJECT)

        sku_id = self._required_string(item.get("sku_id"), "item.sku_id")
        fields = item.get("fields")
        if not isinstance(fields, Mapping):
            raise ValueError(GIFTAPI_SERVICE_TEXT.ORDER_FIELDS_OBJECT)

        metadata = payload.get("metadata")
        if metadata is not None and not isinstance(metadata, Mapping):
            raise ValueError(GIFTAPI_SERVICE_TEXT.ORDER_METADATA_OBJECT)

        return GiftApiOrderDraft(
            external_id=external_id,
            sku_id=sku_id,
            fields=dict(fields),
            metadata=dict(metadata) if isinstance(metadata, Mapping) else None,
        )

    @staticmethod
    def _required_string(value: object, field_name: str) -> str:
        text = str(value).strip() if value is not None else ""
        if not text:
            raise ValueError(GIFTAPI_SERVICE_TEXT.required_field(field_name))
        return text


__all__ = [
    "GiftApiError",
    "GiftApiConfigurationError",
    "GiftApiOrderDraft",
    "GiftApiOverview",
    "GiftApiService",
]