"""HTTP-клиент GiftAPI.

Обеспечивает доступ к каталогу, заказам, балансу и eSIM-статусу.
Подписывает POST-запросы через HMAC-SHA256.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation

import httpx

from cerber_bot.texts import GIFTAPI_CLIENT_TEXT


JsonDict = dict[str, object]


class GiftApiError(RuntimeError):
    pass


class GiftApiConfigurationError(GiftApiError):
    pass


class GiftApiRequestError(GiftApiError):
    def __init__(
        self,
        error: str,
        message: str | None = None,
        hint: str | None = None,
        status_code: int | None = None,
    ) -> None:
        super().__init__(error)
        self.error = error
        self.message = message
        self.hint = hint
        self.status_code = status_code

    def __str__(self) -> str:
        parts = [self.error]
        if self.message and self.message != self.error:
            parts.append(self.message)
        if self.hint:
            parts.append(GIFTAPI_CLIENT_TEXT.HINT.format(hint=self.hint))
        return ". ".join(parts)


@dataclass(slots=True, frozen=True)
class GiftCursorMeta:
    next_cursor: str | None = None
    prev_cursor: str | None = None
    per_page: int | None = None


@dataclass(slots=True, frozen=True)
class GiftBalance:
    balance: Decimal
    currency: str
    reserved_amount: Decimal
    available_balance: Decimal
    allow_overdraft: bool
    overdraft_limit: Decimal
    is_overdrafted: bool


@dataclass(slots=True, frozen=True)
class GiftPartner:
    uuid: str
    name: str
    email: str
    currency: str
    is_active: bool
    balance: GiftBalance | None = None


@dataclass(slots=True, frozen=True)
class GiftBalanceTransaction:
    transaction_type: str
    amount: Decimal
    balance_after: Decimal
    currency: str
    created_at: datetime | None
    order_id: str | None = None
    payment_method: str | None = None
    fee_amount: Decimal | None = None


@dataclass(slots=True, frozen=True)
class GiftCategory:
    category_id: int
    name: str
    parent_id: int | None = None
    attributes: tuple[JsonDict, ...] = ()


@dataclass(slots=True, frozen=True)
class GiftRequiredField:
    code: str
    field_type: str
    name: str
    description: str | None
    required: bool
    validation: JsonDict = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class GiftSkuBasic:
    sku_id: str
    name: str
    image: str | None = None
    attributes: JsonDict = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class GiftSkuDetail:
    sku_id: str
    name: str
    price: Decimal | None
    currency: str
    stock: int
    max_per_order: int | None
    image: str | None = None
    markup_percent: Decimal | None = None
    markup_fixed: Decimal | None = None
    attributes: JsonDict = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class GiftProductSummary:
    product_id: str
    name: str
    product_type: str
    denomination_type: str | None
    category_id: int | None
    category_name: str | None
    description: str | None
    image: str | None
    attributes: JsonDict = field(default_factory=dict)
    required_fields: tuple[GiftRequiredField, ...] = ()
    skus: tuple[GiftSkuBasic, ...] = ()


@dataclass(slots=True, frozen=True)
class GiftProductDetail:
    product_id: str
    name: str
    product_type: str
    denomination_type: str | None
    category_name: str | None
    description: str | None
    image: str | None
    attributes: JsonDict = field(default_factory=dict)
    skus: tuple[GiftSkuDetail, ...] = ()
    required_fields: tuple[GiftRequiredField, ...] = ()


@dataclass(slots=True, frozen=True)
class GiftPricelistItem:
    sku_id: str
    denomination_type: str
    price: Decimal | None
    currency: str
    stock: int
    max_per_order: int | None = None
    markup_percent: Decimal | None = None
    markup_fixed: Decimal | None = None


@dataclass(slots=True, frozen=True)
class GiftOrderItem:
    sku_id: str
    sku_name: str
    quantity: int
    price: Decimal | None
    currency: str
    status: str
    delivery_data: tuple[JsonDict, ...] = ()
    customer_data: JsonDict | None = None
    error_message: str | None = None


@dataclass(slots=True, frozen=True)
class GiftOrder:
    order_id: str
    external_id: str
    status: str
    total_amount: Decimal
    currency: str
    created_at: datetime | None
    items: tuple[GiftOrderItem, ...] = ()
    metadata: JsonDict | None = None


@dataclass(slots=True, frozen=True)
class GiftEsimPackage:
    package_id: str | None
    name: str | None
    data_total: Decimal | None
    data_remaining: Decimal | None
    data_unit: str | None
    activated_at: datetime | None
    expires_at: datetime | None
    status: str | None


@dataclass(slots=True, frozen=True)
class GiftCoverage:
    country_name: str | None
    country_code: str | None
    network_name: str | None


@dataclass(slots=True, frozen=True)
class GiftEsimStatus:
    esim_id: str | None
    iccid: str
    status: str
    qr_code: str | None
    universal_link: str | None
    can_renew: bool
    last_bundle: str | None
    total_gb: Decimal | None
    remaining_gb: Decimal | None
    unit: str | None
    active_packages: tuple[GiftEsimPackage, ...] = ()
    coverage: tuple[GiftCoverage, ...] = ()


class GiftApiClient:
    def __init__(
        self,
        base_url: str,
        http_client: httpx.AsyncClient,
        token: str | None = None,
        secret: str | None = None,
        locale: str = "ru",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.http_client = http_client
        self.token = token.strip() if token else None
        self.secret = secret.strip() if secret else None
        self.locale = locale if locale in {"ru", "en"} else "ru"

    @property
    def is_configured(self) -> bool:
        return bool(self.base_url and self.token)

    def ensure_configured(self, require_secret: bool = False) -> None:
        if not self.base_url:
            raise GiftApiConfigurationError(GIFTAPI_CLIENT_TEXT.MISSING_BASE_URL)
        if not self.token:
            raise GiftApiConfigurationError(GIFTAPI_CLIENT_TEXT.MISSING_TOKEN)
        if require_secret and not self.secret:
            raise GiftApiConfigurationError(GIFTAPI_CLIENT_TEXT.MISSING_SECRET)

    async def get_partner_profile(self) -> GiftPartner:
        payload = await self._request_json("GET", "/me")
        data = self._data_mapping(payload)
        return self._parse_partner(self._mapping(data.get("partner"), "GiftAPI partner payload must be an object"))

    async def get_balance(self) -> GiftBalance:
        payload = await self._request_json("GET", "/balance")
        return self._parse_balance(self._data_mapping(payload))

    async def get_balance_history(
        self,
        *,
        cursor: str | None = None,
        per_page: int = 10,
    ) -> tuple[tuple[GiftBalanceTransaction, ...], GiftCursorMeta]:
        params: JsonDict = {"per_page": min(max(per_page, 1), 100)}
        if cursor:
            params["cursor"] = cursor

        payload = await self._request_json("GET", "/balance/history", params=params)
        rows = self._data_list(payload)
        transactions = tuple(self._parse_balance_transaction(self._mapping(item, "Balance history item must be an object")) for item in rows)
        return transactions, self._parse_cursor_meta(self._mapping(payload, "GiftAPI balance payload must be an object").get("meta"))

    async def list_categories(self, *, locale: str | None = None) -> tuple[GiftCategory, ...]:
        payload = await self._request_json("GET", "/catalog/categories", params=self._locale_params(locale))
        rows = self._data_list(payload)
        return tuple(self._parse_category(self._mapping(item, "Category payload must be an object")) for item in rows)

    async def list_products(
        self,
        *,
        locale: str | None = None,
        cursor: str | None = None,
        per_page: int = 50,
        category_id: int | None = None,
        product_type: str | None = None,
        include_skus: bool = True,
    ) -> tuple[tuple[GiftProductSummary, ...], GiftCursorMeta]:
        params = self._locale_params(locale)
        params["per_page"] = min(max(per_page, 1), 200)
        params["include_skus"] = include_skus
        if cursor:
            params["cursor"] = cursor
        if category_id is not None:
            params["category_id"] = category_id
        if product_type:
            params["type"] = product_type

        payload = await self._request_json("GET", "/catalog/products", params=params)
        rows = self._data_list(payload)
        products = tuple(self._parse_product_summary(self._mapping(item, "Product payload must be an object")) for item in rows)
        return products, self._parse_cursor_meta(self._mapping(payload, "GiftAPI products payload must be an object").get("meta"))

    async def list_all_products(
        self,
        *,
        locale: str | None = None,
        per_page: int = 200,
        include_skus: bool = True,
        max_pages: int = 20,
    ) -> tuple[GiftProductSummary, ...]:
        products: list[GiftProductSummary] = []
        cursor: str | None = None

        for _ in range(max_pages):
            batch, meta = await self.list_products(
                locale=locale,
                cursor=cursor,
                per_page=per_page,
                include_skus=include_skus,
            )
            products.extend(batch)
            if meta.next_cursor is None:
                break
            cursor = meta.next_cursor

        return tuple(products)

    async def get_product_detail(self, product_uuid: str, *, locale: str | None = None) -> GiftProductDetail:
        payload = await self._request_json(
            "GET",
            f"/catalog/products/{product_uuid}",
            params=self._locale_params(locale),
        )
        return self._parse_product_detail(self._data_mapping(payload))

    async def list_pricelist(
        self,
        *,
        locale: str | None = None,
        cursor: str | None = None,
        per_page: int = 100,
        category_id: int | None = None,
        product_type: str | None = None,
    ) -> tuple[tuple[GiftPricelistItem, ...], GiftCursorMeta]:
        params = self._locale_params(locale)
        params["per_page"] = min(max(per_page, 1), 200)
        if cursor:
            params["cursor"] = cursor
        if category_id is not None:
            params["category_id"] = category_id
        if product_type:
            params["type"] = product_type

        payload = await self._request_json("GET", "/catalog/pricelist", params=params)
        rows = self._data_list(payload)
        pricelist = tuple(self._parse_pricelist_item(self._mapping(item, "Pricelist item must be an object")) for item in rows)
        return pricelist, self._parse_cursor_meta(self._mapping(payload, "GiftAPI pricelist payload must be an object").get("meta"))

    async def list_all_pricelist(
        self,
        *,
        locale: str | None = None,
        per_page: int = 200,
        max_pages: int = 20,
    ) -> tuple[GiftPricelistItem, ...]:
        items: list[GiftPricelistItem] = []
        cursor: str | None = None

        for _ in range(max_pages):
            batch, meta = await self.list_pricelist(locale=locale, cursor=cursor, per_page=per_page)
            items.extend(batch)
            if meta.next_cursor is None:
                break
            cursor = meta.next_cursor

        return tuple(items)

    async def list_orders(
        self,
        *,
        cursor: str | None = None,
        per_page: int = 10,
        status: str | None = None,
        external_id: str | None = None,
    ) -> tuple[tuple[GiftOrder, ...], GiftCursorMeta]:
        params: JsonDict = {"per_page": min(max(per_page, 1), 100)}
        if cursor:
            params["cursor"] = cursor
        if status:
            params["status"] = status
        if external_id:
            params["external_id"] = external_id

        payload = await self._request_json("GET", "/orders", params=params)
        rows = self._data_list(payload)
        orders = tuple(self._parse_order(self._mapping(item, "Order payload must be an object")) for item in rows)
        return orders, self._parse_cursor_meta(self._mapping(payload, "GiftAPI orders payload must be an object").get("meta"))

    async def get_order(self, order_uuid: str) -> GiftOrder:
        payload = await self._request_json("GET", f"/orders/{order_uuid}")
        return self._parse_order(self._data_mapping(payload))

    async def create_order(
        self,
        *,
        external_id: str,
        sku_id: str,
        fields: Mapping[str, object],
        metadata: Mapping[str, object] | None = None,
    ) -> GiftOrder:
        self.ensure_configured(require_secret=True)
        timestamp = str(int(time.time()))
        headers = {
            "X-Timestamp": timestamp,
            "X-Signature": self.build_order_signature(
                timestamp=timestamp,
                sku_id=sku_id,
                external_id=external_id,
                secret=self.secret or "",
            ),
        }
        payload = await self._request_json(
            "POST",
            "/orders",
            json_body={
                "external_id": external_id,
                "item": {"sku_id": sku_id, "fields": dict(fields)},
                "metadata": dict(metadata) if metadata is not None else None,
            },
            extra_headers=headers,
        )
        return self._parse_order(self._mapping(self._mapping(payload, "GiftAPI create order payload must be an object").get("data"), "GiftAPI order payload must be an object"))

    async def get_esim_status(self, iccid: str) -> GiftEsimStatus:
        payload = await self._request_json("GET", f"/services/esim/{iccid}/status")
        return self._parse_esim_status(self._data_mapping(payload))

    @staticmethod
    def build_order_signature(timestamp: str, sku_id: str, external_id: str, secret: str) -> str:
        message = f"{timestamp}{sku_id}{external_id}"
        return hmac.new(secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).hexdigest()

    @staticmethod
    def verify_webhook_signature(
        *,
        timestamp: str,
        event: str,
        idempotency_key: str,
        provided_signature: str,
        secret: str,
    ) -> bool:
        message = f"{timestamp}{event}{idempotency_key}"
        expected = hmac.new(secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, provided_signature)

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, object] | None = None,
        json_body: Mapping[str, object] | None = None,
        extra_headers: Mapping[str, str] | None = None,
    ) -> object:
        self.ensure_configured(require_secret=extra_headers is not None and "X-Signature" in extra_headers)

        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.token}",
        }
        if extra_headers:
            headers.update(extra_headers)

        response = await self.http_client.request(
            method,
            f"{self.base_url}{path}",
            headers=headers,
            params=params,
            json=json_body,
        )

        try:
            payload = response.json()
        except ValueError:
            payload = None

        if response.is_error:
            raise self._request_error(response.status_code, payload, response.text)

        if isinstance(payload, Mapping) and payload.get("success") is False:
            raise self._request_error(response.status_code, payload, response.text)

        return payload

    @staticmethod
    def _request_error(status_code: int, payload: object, fallback_text: str) -> GiftApiRequestError:
        if isinstance(payload, Mapping):
            error = str(payload.get("error") or payload.get("message") or f"GiftAPI request failed with status {status_code}")
            message = GiftApiClient._optional_string(payload.get("message"))
            hint = GiftApiClient._optional_string(payload.get("hint"))
            return GiftApiRequestError(error=error, message=message, hint=hint, status_code=status_code)
        text = fallback_text.strip() or f"GiftAPI request failed with status {status_code}"
        return GiftApiRequestError(error=text, status_code=status_code)

    def _locale_params(self, locale: str | None) -> JsonDict:
        return {"locale": locale or self.locale}

    @staticmethod
    def _data_mapping(payload: object) -> JsonDict:
        body = GiftApiClient._mapping(payload, "GiftAPI response must be an object")
        return GiftApiClient._mapping(body.get("data"), "GiftAPI response field 'data' must be an object")

    @staticmethod
    def _data_list(payload: object) -> list[object]:
        body = GiftApiClient._mapping(payload, "GiftAPI response must be an object")
        data = body.get("data")
        if not isinstance(data, list):
            raise GiftApiRequestError("GiftAPI response field 'data' must be an array")
        return data

    @staticmethod
    def _parse_cursor_meta(meta: object) -> GiftCursorMeta:
        if meta is None:
            return GiftCursorMeta()
        body = GiftApiClient._mapping(meta, "GiftAPI cursor meta must be an object")
        return GiftCursorMeta(
            next_cursor=GiftApiClient._optional_string(body.get("next_cursor")),
            prev_cursor=GiftApiClient._optional_string(body.get("prev_cursor")),
            per_page=GiftApiClient._optional_int(body.get("per_page")),
        )

    @staticmethod
    def _parse_balance(data: Mapping[str, object]) -> GiftBalance:
        return GiftBalance(
            balance=GiftApiClient._decimal(data.get("balance"), "balance"),
            currency=GiftApiClient._string(data.get("currency"), "currency"),
            reserved_amount=GiftApiClient._decimal(data.get("reserved_amount"), "reserved_amount"),
            available_balance=GiftApiClient._decimal(data.get("available_balance"), "available_balance"),
            allow_overdraft=GiftApiClient._boolean(data.get("allow_overdraft")),
            overdraft_limit=GiftApiClient._decimal(data.get("overdraft_limit"), "overdraft_limit"),
            is_overdrafted=GiftApiClient._boolean(data.get("is_overdrafted")),
        )

    @staticmethod
    def _parse_partner(data: Mapping[str, object]) -> GiftPartner:
        balance_payload = data.get("balance")
        balance = GiftApiClient._parse_balance(GiftApiClient._mapping(balance_payload, "GiftAPI balance must be an object")) if isinstance(balance_payload, Mapping) else None
        return GiftPartner(
            uuid=GiftApiClient._string(data.get("uuid"), "partner.uuid"),
            name=GiftApiClient._string(data.get("name"), "partner.name"),
            email=GiftApiClient._string(data.get("email"), "partner.email"),
            currency=GiftApiClient._string(data.get("currency"), "partner.currency"),
            is_active=GiftApiClient._boolean(data.get("is_active")),
            balance=balance,
        )

    @staticmethod
    def _parse_balance_transaction(data: Mapping[str, object]) -> GiftBalanceTransaction:
        return GiftBalanceTransaction(
            transaction_type=GiftApiClient._string(data.get("type"), "transaction.type"),
            amount=GiftApiClient._decimal(data.get("amount"), "transaction.amount"),
            balance_after=GiftApiClient._decimal(data.get("balance_after"), "transaction.balance_after"),
            currency=GiftApiClient._string(data.get("currency"), "transaction.currency"),
            created_at=GiftApiClient._datetime(data.get("created_at")),
            order_id=GiftApiClient._optional_string(data.get("order_id")),
            payment_method=GiftApiClient._optional_string(data.get("payment_method")),
            fee_amount=GiftApiClient._optional_decimal(data.get("fee_amount")),
        )

    @staticmethod
    def _parse_category(data: Mapping[str, object]) -> GiftCategory:
        attributes = data.get("attributes")
        items = tuple(dict(GiftApiClient._mapping(item, "Category attribute must be an object")) for item in attributes) if isinstance(attributes, list) else ()
        return GiftCategory(
            category_id=GiftApiClient._int(data.get("id"), "category.id"),
            name=GiftApiClient._string(data.get("name"), "category.name"),
            parent_id=GiftApiClient._optional_int(data.get("parent_id")),
            attributes=items,
        )

    @staticmethod
    def _parse_required_field(data: Mapping[str, object]) -> GiftRequiredField:
        validation = data.get("validation")
        return GiftRequiredField(
            code=GiftApiClient._string(data.get("code"), "field.code"),
            field_type=GiftApiClient._string(data.get("type"), "field.type"),
            name=GiftApiClient._string(data.get("name"), "field.name"),
            description=GiftApiClient._optional_string(data.get("description")),
            required=GiftApiClient._boolean(data.get("required")),
            validation=dict(GiftApiClient._mapping(validation, "Field validation must be an object")) if isinstance(validation, Mapping) else {},
        )

    @staticmethod
    def _parse_sku_basic(data: Mapping[str, object]) -> GiftSkuBasic:
        attributes = data.get("attributes")
        return GiftSkuBasic(
            sku_id=GiftApiClient._string(data.get("id"), "sku.id"),
            name=GiftApiClient._string(data.get("name"), "sku.name"),
            image=GiftApiClient._optional_string(data.get("image")),
            attributes=dict(GiftApiClient._mapping(attributes, "SKU attributes must be an object")) if isinstance(attributes, Mapping) else {},
        )

    @staticmethod
    def _parse_sku_detail(data: Mapping[str, object]) -> GiftSkuDetail:
        attributes = data.get("attributes")
        return GiftSkuDetail(
            sku_id=GiftApiClient._string(data.get("id"), "sku.id"),
            name=GiftApiClient._string(data.get("name"), "sku.name"),
            price=GiftApiClient._optional_decimal(data.get("price")),
            currency=GiftApiClient._string(data.get("currency") or "USD", "sku.currency"),
            stock=GiftApiClient._int(data.get("stock") or 0, "sku.stock"),
            max_per_order=GiftApiClient._optional_int(data.get("max_per_order")),
            image=GiftApiClient._optional_string(data.get("image")),
            markup_percent=GiftApiClient._optional_decimal(data.get("markup_percent")),
            markup_fixed=GiftApiClient._optional_decimal(data.get("markup_fixed")),
            attributes=dict(GiftApiClient._mapping(attributes, "SKU attributes must be an object")) if isinstance(attributes, Mapping) else {},
        )

    @staticmethod
    def _parse_product_summary(data: Mapping[str, object]) -> GiftProductSummary:
        category = GiftApiClient._category_fields(data.get("category"))
        fields = data.get("fields")
        skus = data.get("skus")
        attributes = data.get("attributes")
        return GiftProductSummary(
            product_id=GiftApiClient._string(data.get("id"), "product.id"),
            name=GiftApiClient._string(data.get("name"), "product.name"),
            product_type=GiftApiClient._string(data.get("type"), "product.type"),
            denomination_type=GiftApiClient._optional_string(data.get("denomination_type")),
            category_id=category[0],
            category_name=category[1],
            description=GiftApiClient._optional_string(data.get("description")),
            image=GiftApiClient._optional_string(data.get("image")),
            attributes=dict(GiftApiClient._mapping(attributes, "Product attributes must be an object")) if isinstance(attributes, Mapping) else {},
            required_fields=tuple(
                GiftApiClient._parse_required_field(GiftApiClient._mapping(item, "Product field must be an object"))
                for item in fields
            ) if isinstance(fields, list) else (),
            skus=tuple(
                GiftApiClient._parse_sku_basic(GiftApiClient._mapping(item, "Product SKU must be an object"))
                for item in skus
            ) if isinstance(skus, list) else (),
        )

    @staticmethod
    def _parse_product_detail(data: Mapping[str, object]) -> GiftProductDetail:
        category = GiftApiClient._category_fields(data.get("category"))
        skus = data.get("skus")
        fields = data.get("fields")
        attributes = data.get("attributes")
        return GiftProductDetail(
            product_id=GiftApiClient._string(data.get("id"), "product.id"),
            name=GiftApiClient._string(data.get("name"), "product.name"),
            product_type=GiftApiClient._string(data.get("type"), "product.type"),
            denomination_type=GiftApiClient._optional_string(data.get("denomination_type")),
            category_name=category[1],
            description=GiftApiClient._optional_string(data.get("description")),
            image=GiftApiClient._optional_string(data.get("image")),
            attributes=dict(GiftApiClient._mapping(attributes, "Product attributes must be an object")) if isinstance(attributes, Mapping) else {},
            skus=tuple(
                GiftApiClient._parse_sku_detail(GiftApiClient._mapping(item, "Product detail SKU must be an object"))
                for item in skus
            ) if isinstance(skus, list) else (),
            required_fields=tuple(
                GiftApiClient._parse_required_field(GiftApiClient._mapping(item, "Product field must be an object"))
                for item in fields
            ) if isinstance(fields, list) else (),
        )

    @staticmethod
    def _parse_pricelist_item(data: Mapping[str, object]) -> GiftPricelistItem:
        return GiftPricelistItem(
            sku_id=GiftApiClient._string(data.get("sku_id"), "pricelist.sku_id"),
            denomination_type=GiftApiClient._string(data.get("denomination_type"), "pricelist.denomination_type"),
            price=GiftApiClient._optional_decimal(data.get("price")),
            currency=GiftApiClient._string(data.get("currency"), "pricelist.currency"),
            stock=GiftApiClient._int(data.get("stock") or 0, "pricelist.stock"),
            max_per_order=GiftApiClient._optional_int(data.get("max_per_order")),
            markup_percent=GiftApiClient._optional_decimal(data.get("markup_percent")),
            markup_fixed=GiftApiClient._optional_decimal(data.get("markup_fixed")),
        )

    @staticmethod
    def _parse_order_item(data: Mapping[str, object]) -> GiftOrderItem:
        delivery_data = data.get("delivery_data")
        customer_data = data.get("customer_data")
        return GiftOrderItem(
            sku_id=GiftApiClient._string(data.get("sku_id"), "order_item.sku_id"),
            sku_name=GiftApiClient._string(data.get("sku_name") or data.get("sku_id"), "order_item.sku_name"),
            quantity=GiftApiClient._int(data.get("quantity") or 0, "order_item.quantity"),
            price=GiftApiClient._optional_decimal(data.get("price")),
            currency=GiftApiClient._string(data.get("currency") or "USD", "order_item.currency"),
            status=GiftApiClient._string(data.get("status"), "order_item.status"),
            delivery_data=tuple(dict(GiftApiClient._mapping(item, "Delivery data item must be an object")) for item in delivery_data) if isinstance(delivery_data, list) else (),
            customer_data=dict(GiftApiClient._mapping(customer_data, "Customer data must be an object")) if isinstance(customer_data, Mapping) else None,
            error_message=GiftApiClient._optional_string(data.get("error_message")),
        )

    @staticmethod
    def _parse_order(data: Mapping[str, object]) -> GiftOrder:
        items = data.get("items")
        metadata = data.get("metadata")
        return GiftOrder(
            order_id=GiftApiClient._string(data.get("id"), "order.id"),
            external_id=GiftApiClient._string(data.get("external_id"), "order.external_id"),
            status=GiftApiClient._string(data.get("status"), "order.status"),
            total_amount=GiftApiClient._decimal(data.get("total_amount") or 0, "order.total_amount"),
            currency=GiftApiClient._string(data.get("currency") or "USD", "order.currency"),
            created_at=GiftApiClient._datetime(data.get("created_at")),
            items=tuple(
                GiftApiClient._parse_order_item(GiftApiClient._mapping(item, "Order item must be an object"))
                for item in items
            ) if isinstance(items, list) else (),
            metadata=dict(GiftApiClient._mapping(metadata, "Order metadata must be an object")) if isinstance(metadata, Mapping) else None,
        )

    @staticmethod
    def _parse_esim_package(data: Mapping[str, object]) -> GiftEsimPackage:
        return GiftEsimPackage(
            package_id=GiftApiClient._optional_string(data.get("id")),
            name=GiftApiClient._optional_string(data.get("name")),
            data_total=GiftApiClient._optional_decimal(data.get("data_total")),
            data_remaining=GiftApiClient._optional_decimal(data.get("data_remaining")),
            data_unit=GiftApiClient._optional_string(data.get("data_unit")),
            activated_at=GiftApiClient._datetime(data.get("activated_at")),
            expires_at=GiftApiClient._datetime(data.get("expires_at")),
            status=GiftApiClient._optional_string(data.get("status")),
        )

    @staticmethod
    def _parse_coverage(data: Mapping[str, object]) -> GiftCoverage:
        return GiftCoverage(
            country_name=GiftApiClient._optional_string(data.get("country_name")),
            country_code=GiftApiClient._optional_string(data.get("country_code")),
            network_name=GiftApiClient._optional_string(data.get("network_name")),
        )

    @staticmethod
    def _parse_esim_status(data: Mapping[str, object]) -> GiftEsimStatus:
        balance = data.get("data_balance")
        active_packages = data.get("active_packages")
        coverage = data.get("coverage")
        balance_mapping = GiftApiClient._mapping(balance, "eSIM data_balance must be an object") if isinstance(balance, Mapping) else {}
        return GiftEsimStatus(
            esim_id=GiftApiClient._optional_string(data.get("esim_id")),
            iccid=GiftApiClient._string(data.get("iccid"), "esim.iccid"),
            status=GiftApiClient._string(data.get("status"), "esim.status"),
            qr_code=GiftApiClient._optional_string(data.get("qr_code")),
            universal_link=GiftApiClient._optional_string(data.get("universal_link")),
            can_renew=GiftApiClient._boolean(data.get("can_renew")),
            last_bundle=GiftApiClient._optional_string(data.get("last_bundle")),
            total_gb=GiftApiClient._optional_decimal(balance_mapping.get("total_gb")),
            remaining_gb=GiftApiClient._optional_decimal(balance_mapping.get("remaining_gb")),
            unit=GiftApiClient._optional_string(balance_mapping.get("unit")),
            active_packages=tuple(
                GiftApiClient._parse_esim_package(GiftApiClient._mapping(item, "eSIM package must be an object"))
                for item in active_packages
            ) if isinstance(active_packages, list) else (),
            coverage=tuple(
                GiftApiClient._parse_coverage(GiftApiClient._mapping(item, "Coverage item must be an object"))
                for item in coverage
            ) if isinstance(coverage, list) else (),
        )

    @staticmethod
    def _category_fields(category: object) -> tuple[int | None, str | None]:
        if not isinstance(category, Mapping):
            return None, None
        category_mapping = GiftApiClient._mapping(category, "Product category must be an object")
        category_id = GiftApiClient._optional_int(category_mapping.get("id"))
        category_name = GiftApiClient._optional_string(category_mapping.get("name"))
        return category_id, category_name

    @staticmethod
    def _mapping(value: object, message: str) -> JsonDict:
        if not isinstance(value, Mapping):
            raise GiftApiRequestError(message)
        return dict(value)

    @staticmethod
    def _string(value: object, field_name: str) -> str:
        text = GiftApiClient._optional_string(value)
        if text is None:
            raise GiftApiRequestError(f"GiftAPI field '{field_name}' must be a non-empty string")
        return text

    @staticmethod
    def _optional_string(value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _boolean(value: object) -> bool:
        if isinstance(value, bool):
            return value
        raise GiftApiRequestError("GiftAPI boolean field has invalid type")

    @staticmethod
    def _int(value: object, field_name: str) -> int:
        try:
            return int(value)
        except (TypeError, ValueError) as error:
            raise GiftApiRequestError(f"GiftAPI field '{field_name}' must be an integer") from error

    @staticmethod
    def _optional_int(value: object) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError) as error:
            raise GiftApiRequestError("GiftAPI optional integer field has invalid type") from error

    @staticmethod
    def _decimal(value: object, field_name: str) -> Decimal:
        optional_value = GiftApiClient._optional_decimal(value)
        if optional_value is None:
            raise GiftApiRequestError(f"GiftAPI field '{field_name}' must be numeric")
        return optional_value

    @staticmethod
    def _optional_decimal(value: object) -> Decimal | None:
        if value is None:
            return None
        try:
            return Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError) as error:
            raise GiftApiRequestError("GiftAPI numeric field has invalid value") from error

    @staticmethod
    def _datetime(value: object) -> datetime | None:
        text = GiftApiClient._optional_string(value)
        if text is None:
            return None
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError as error:
            raise GiftApiRequestError(f"GiftAPI date field has invalid format: {text}") from error