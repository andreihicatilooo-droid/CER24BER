"""HTTP-клиент NicePay.

Создаёт платежи, парсит webhook-уведомления и верифицирует подписи.
"""

from __future__ import annotations

import hashlib
import hmac
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

from cerber_bot.texts import NICEPAY_TEXT


JsonDict = dict[str, object]


class NicePayError(RuntimeError):
    pass


class NicePayConfigurationError(NicePayError):
    pass


class NicePayRequestError(NicePayError):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(slots=True, frozen=True)
class NicePayCreatedPayment:
    payment_id: str
    amount_minor: int
    currency: str
    link: str
    expires_at: datetime | None


@dataclass(slots=True, frozen=True)
class NicePayWebhookNotification:
    result: str
    payment_id: str
    merchant_id: str
    order_id: str
    amount_minor: int
    amount_currency: str
    profit_minor: int | None
    profit_currency: str | None
    method: str | None
    signature: str


class NicePayClient:
    def __init__(
        self,
        *,
        base_url: str,
        http_client: httpx.AsyncClient,
        merchant_id: str | None,
        secret: str | None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.http_client = http_client
        self.merchant_id = merchant_id.strip() if merchant_id else None
        self.secret = secret.strip() if secret else None

    @property
    def is_configured(self) -> bool:
        return bool(self.merchant_id and self.secret)

    def ensure_configured(self) -> None:
        if not self.merchant_id or not self.secret:
            raise NicePayConfigurationError(NICEPAY_TEXT.MISSING_CREDENTIALS)

    async def create_payment(
        self,
        *,
        order_id: str,
        account: str,
        amount_minor: int,
        currency: str,
        description: str | None = None,
        method: str | None = None,
        success_url: str | None = None,
        fail_url: str | None = None,
    ) -> NicePayCreatedPayment:
        self.ensure_configured()

        base_payload = {
            "merchant_id": self.merchant_id or "",
            "secret": self.secret or "",
            "order_id": order_id,
            "amount": amount_minor,
            "currency": currency,
        }
        if description:
            base_payload["description"] = description
        if method:
            base_payload["method"] = method
        if success_url:
            base_payload["success_url"] = success_url
        if fail_url:
            base_payload["fail_url"] = fail_url

        last_error: NicePayRequestError | None = None
        for customer_field in ("account", "customer"):
            payload = dict(base_payload)
            payload[customer_field] = account
            try:
                return await self._create_payment_with_payload(payload)
            except NicePayRequestError as error:
                last_error = error
                if customer_field == "customer" or not self._should_try_fallback(error):
                    raise

        if last_error is not None:
            raise last_error
        raise NicePayRequestError(NICEPAY_TEXT.CREATE_PAYMENT_FAILED)

    def parse_webhook(self, parameters: Mapping[str, object]) -> NicePayWebhookNotification:
        self.ensure_configured()
        normalized = {str(key): str(value) for key, value in parameters.items()}

        signature = normalized.get("hash")
        if not signature:
            raise NicePayRequestError(NICEPAY_TEXT.CALLBACK_HASH_REQUIRED)
        if not self.verify_signature(parameters=normalized, provided_signature=signature, secret=self.secret or ""):
            raise NicePayRequestError(NICEPAY_TEXT.INVALID_HASH)

        return NicePayWebhookNotification(
            result=self._required_string(normalized, "result"),
            payment_id=self._required_string(normalized, "payment_id"),
            merchant_id=self._required_string(normalized, "merchant_id"),
            order_id=self._required_string(normalized, "order_id"),
            amount_minor=self._required_int(normalized, "amount"),
            amount_currency=self._required_string(normalized, "amount_currency"),
            profit_minor=self._optional_int(normalized.get("profit")),
            profit_currency=self._optional_string(normalized.get("profit_currency")),
            method=self._optional_string(normalized.get("method")),
            signature=signature,
        )

    @staticmethod
    def verify_signature(*, parameters: Mapping[str, object], provided_signature: str, secret: str) -> bool:
        values = [
            str(value)
            for key, value in sorted(parameters.items(), key=lambda item: item[0])
            if key != "hash"
        ]
        values.append(secret)
        digest = hashlib.sha256("{np}".join(values).encode("utf-8")).hexdigest()
        return hmac.compare_digest(digest, provided_signature)

    async def _create_payment_with_payload(self, payload: JsonDict) -> NicePayCreatedPayment:
        body = await self._request_json("POST", "/public/api/payment", json_body=payload)
        response = self._mapping(body, "NicePay response must be an object")
        status = self._optional_string(response.get("status"))
        data = self._mapping(response.get("data"), "NicePay response field 'data' must be an object")

        if status != "success":
            raise NicePayRequestError(
                self._optional_string(data.get("message")) or NICEPAY_TEXT.PAYMENT_NOT_CREATED,
            )

        return NicePayCreatedPayment(
            payment_id=self._required_string(data, "payment_id"),
            amount_minor=self._required_int(data, "amount"),
            currency=self._required_string(data, "currency"),
            link=self._required_string(data, "link"),
            expires_at=self._optional_unix_datetime(data.get("expired")),
        )

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        json_body: Mapping[str, object] | None = None,
    ) -> object:
        response = await self.http_client.request(
            method,
            f"{self.base_url}{path}",
            headers={"Accept": "application/json"},
            json=json_body,
        )

        try:
            payload = response.json()
        except ValueError:
            payload = None

        if response.is_error:
            raise self._request_error(response.status_code, payload, response.text)

        return payload

    @staticmethod
    def _should_try_fallback(error: NicePayRequestError) -> bool:
        if error.status_code is None:
            return True
        return 400 <= error.status_code < 500 and error.status_code not in {401, 403, 429}

    @staticmethod
    def _request_error(status_code: int, payload: object, fallback_text: str) -> NicePayRequestError:
        if isinstance(payload, Mapping):
            data = payload.get("data") if isinstance(payload.get("data"), Mapping) else payload
            message = NicePayClient._optional_string(data.get("message") if isinstance(data, Mapping) else None)
            return NicePayRequestError(message or f"NicePay request failed with status {status_code}", status_code=status_code)
        text = fallback_text.strip() or f"NicePay request failed with status {status_code}"
        return NicePayRequestError(text, status_code=status_code)

    @staticmethod
    def _mapping(value: object, message: str) -> JsonDict:
        if not isinstance(value, Mapping):
            raise NicePayRequestError(message)
        return dict(value)

    @staticmethod
    def _required_string(mapping: Mapping[str, object], key: str) -> str:
        value = NicePayClient._optional_string(mapping.get(key))
        if value is None:
            raise NicePayRequestError(f"NicePay payload field '{key}' is required.")
        return value

    @staticmethod
    def _required_int(mapping: Mapping[str, object], key: str) -> int:
        value = NicePayClient._optional_int(mapping.get(key))
        if value is None:
            raise NicePayRequestError(f"NicePay payload field '{key}' is required.")
        return value

    @staticmethod
    def _optional_string(value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _optional_int(value: object) -> int | None:
        if value is None:
            return None
        try:
            return int(str(value))
        except (TypeError, ValueError) as error:
            raise NicePayRequestError(f"Expected integer value, got {value!r}.") from error

    @staticmethod
    def _optional_unix_datetime(value: object) -> datetime | None:
        unix_timestamp = NicePayClient._optional_int(value)
        if unix_timestamp is None:
            return None
        return datetime.fromtimestamp(unix_timestamp, tz=timezone.utc)