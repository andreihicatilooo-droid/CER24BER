"""HTTP-клиент Rukassa.

Создаёт платёжные ссылки и верифицирует webhook-уведомления от Rukassa.
Документация: https://lk.rukassa.io/api/v1

Подпись webhook (Signature-заголовок):
    SHA-256( f"{id}|{createdDateTime}|{amount}".encode() + token.encode() )
"""

from __future__ import annotations

import hashlib
import hmac
from collections.abc import Mapping
from dataclasses import dataclass

import httpx

from cerber_bot.texts import RUKASSA_TEXT


JsonDict = dict[str, object]

RUKASSA_PAID_STATUS = "paid"


class RukassaError(RuntimeError):
    pass


class RukassaConfigurationError(RukassaError):
    pass


class RukassaRequestError(RukassaError):
    def __init__(self, message: str, *, status_code: int | None = None, api_error_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.api_error_code = api_error_code


class RukassaFrozenError(RukassaRequestError):
    """Магазин заморожен или не активирован в Rukassa (код ошибки 300)."""


@dataclass(slots=True, frozen=True)
class RukassaCreatedPayment:
    payment_id: int
    payment_url: str


@dataclass(slots=True, frozen=True)
class RukassaWebhookNotification:
    id: int
    order_id: str
    amount: str
    in_amount: str
    created_at: str
    status: str
    payment_method: str | None
    data: str | None
    signature: str


class RukassaClient:
    """Асинхронный клиент Rukassa API."""

    def __init__(
        self,
        *,
        base_url: str,
        http_client: httpx.AsyncClient,
        shop_id: int | None,
        token: str | None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.http_client = http_client
        self.shop_id = shop_id
        self.token = token.strip() if token else None

    @property
    def is_configured(self) -> bool:
        return bool(self.shop_id and self.token)

    def ensure_configured(self) -> None:
        if not self.shop_id or not self.token:
            raise RukassaConfigurationError(
                "Rukassa не настроен: необходимы RUKASSA_SHOP_ID и RUKASSA_TOKEN."
            )

    async def create_payment(
        self,
        *,
        order_id: str,
        amount_rub: str,
        method: str | None = None,
        success_url: str | None = None,
        fail_url: str | None = None,
        user_code: str | None = None,
    ) -> RukassaCreatedPayment:
        """Создать платёжную ссылку через Rukassa.

        Args:
            order_id:    Уникальный идентификатор заказа (строка).
            amount_rub:  Сумма в рублях (строка, например "500.00").
            method:      Метод оплаты (например "card", "sbp"). Опционально.
            success_url: URL перенаправления после успешной оплаты.
            fail_url:    URL перенаправления при неудаче.
            user_code:   Идентификатор пользователя у мерчанта. Опционально.

        Returns:
            RukassaCreatedPayment с payment_id и payment_url.
        """
        self.ensure_configured()

        payload: dict[str, str] = {
            "shop_id": str(self.shop_id),
            "token": self.token or "",
            "order_id": order_id,
            "amount": amount_rub,
        }
        if method:
            payload["method"] = method
        if success_url:
            payload["success_url"] = success_url
        if fail_url:
            payload["fail_url"] = fail_url
        if user_code:
            payload["user_code"] = user_code

        try:
            response = await self.http_client.post(
                f"{self.base_url}/create",
                data=payload,
            )
            response.raise_for_status()
            body: JsonDict = response.json()
        except httpx.HTTPStatusError as error:
            raise RukassaRequestError(
                f"Rukassa HTTP {error.response.status_code}: {error.response.text}",
                status_code=error.response.status_code,
            ) from error
        except httpx.RequestError as error:
            raise RukassaRequestError(f"Rukassa сетевая ошибка: {error}") from error

        if "error" in body:
            api_code = body.get("error")
            try:
                api_code_int = int(api_code)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                api_code_int = None
            msg = self._build_api_error_message(body)
            if api_code_int == 300:
                raise RukassaFrozenError(msg, api_error_code=api_code_int)
            raise RukassaRequestError(msg, api_error_code=api_code_int)

        payment_id = body.get("id")
        payment_url = body.get("url")
        if not payment_id or not payment_url:
            raise RukassaRequestError(
                f"Rukassa вернул неожиданный ответ: {body}"
            )

        return RukassaCreatedPayment(
            payment_id=int(payment_id),
            payment_url=str(payment_url),
        )

    @staticmethod
    def _build_api_error_message(body: Mapping[str, object]) -> str:
        code = str(body.get("error", "")).strip()
        message = str(body.get("message", "")).strip()
        base_message = RUKASSA_TEXT.api_error(code, message)
        if code == "100":
            return f"{base_message}. {RUKASSA_TEXT.API_ERROR_100_HINT}"
        if code == "300":
            return f"{base_message}. {RUKASSA_TEXT.API_ERROR_300_HINT}"
        return base_message

    def parse_webhook(
        self,
        form_data: Mapping[str, str],
        *,
        signature_header: str,
    ) -> RukassaWebhookNotification:
        """Распарсить и верифицировать webhook-уведомление от Rukassa.

        Args:
            form_data:         Поля формы из тела POST-запроса.
            signature_header:  Значение заголовка Signature.

        Raises:
            RukassaConfigurationError: Клиент не настроен.
            RukassaRequestError:       Подпись не совпадает.
        """
        self.ensure_configured()

        payment_id = str(form_data.get("id", ""))
        created_at = str(form_data.get("createdDateTime", ""))
        amount = str(form_data.get("amount", ""))

        if not self.verify_signature(
            payment_id=payment_id,
            created_at=created_at,
            amount=amount,
            token=self.token or "",
            provided_signature=signature_header,
        ):
            raise RukassaRequestError("Неверная подпись Rukassa webhook.")

        return RukassaWebhookNotification(
            id=int(payment_id) if payment_id.isdigit() else 0,
            order_id=str(form_data.get("order_id", "")),
            amount=amount,
            in_amount=str(form_data.get("in_amount", "")),
            created_at=created_at,
            status=str(form_data.get("status", "")),
            payment_method=form_data.get("payment_method") or None,
            data=form_data.get("data") or None,
            signature=signature_header,
        )

    @staticmethod
    def verify_signature(
        *,
        payment_id: str,
        created_at: str,
        amount: str,
        token: str,
        provided_signature: str,
    ) -> bool:
        """Верифицировать подпись Rukassa.

        Алгоритм: SHA-256( "{id}|{createdDateTime}|{amount}" + token )
        """
        raw = f"{payment_id}|{created_at}|{amount}".encode("utf-8") + token.encode("utf-8")
        digest = hashlib.sha256(raw).hexdigest()
        return hmac.compare_digest(digest, provided_signature)
