"""FastAPI-маршрут для webhook-уведомлений GetMyTG."""

from __future__ import annotations

import logging
from html import escape
from typing import Literal

from aiogram import Bot
from aiogram.exceptions import AiogramError
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, TypeAdapter, ValidationError

from cerber_bot.integrations.getmytg import GetMyTGClient
from cerber_bot.services.store import format_money
from cerber_bot.services.tgaccounts import TgAccountWebhookResult
from cerber_bot.texts import TG_ACCOUNTS_TEXT
from cerber_bot.web.deps import get_container

logger = logging.getLogger(__name__)


class WebhookPurchasePayload(BaseModel):
    id: int
    country_code: str
    phone_number: str | None = None


class WebhookVerificationPayload(BaseModel):
    code: str
    password: str | None = None


class WebhookErrorPayload(BaseModel):
    message: str


class WebhookSuccessData(BaseModel):
    purchase: WebhookPurchasePayload
    verification: WebhookVerificationPayload


class WebhookFailedData(BaseModel):
    purchase: WebhookPurchasePayload
    error: WebhookErrorPayload


class WebhookSuccessPayload(BaseModel):
    result: Literal["success"]
    timestamp: str
    data: WebhookSuccessData


class WebhookFailedPayload(BaseModel):
    result: Literal["failed"]
    timestamp: str
    data: WebhookFailedData


WebhookPayload = WebhookSuccessPayload | WebhookFailedPayload
WEBHOOK_PAYLOAD_ADAPTER = TypeAdapter(WebhookPayload)
DEFAULT_WEBHOOK_PATH = "/webhooks/getmytg"


def build_router(webhook_path: str | None = None) -> APIRouter:
    router = APIRouter(tags=["webhooks"])
    normalized_path = _normalize_webhook_path(webhook_path)

    @router.post(normalized_path)
    async def getmytg_webhook(request: Request) -> JSONResponse:
        container = get_container(request)
        secret = (container.settings.getmytg_webhook_secret or "").strip()
        if secret and not _verify_webhook_signature(request, secret):
            logger.warning("GetMyTG webhook отклонён: неверная подпись URL")
            return JSONResponse({"error": {"message": "Invalid signature"}}, status_code=403)

        try:
            payload = WEBHOOK_PAYLOAD_ADAPTER.validate_python(await request.json())
        except ValueError:
            logger.warning("GetMyTG webhook отклонён: тело не является JSON-объектом")
            return JSONResponse({"error": {"message": "Invalid JSON"}}, status_code=400)
        except ValidationError as error:
            logger.warning("GetMyTG webhook отклонён: %s", error)
            return JSONResponse({"error": {"message": "Invalid payload"}}, status_code=400)

        if container.tgaccounts_service is None:
            logger.warning("GetMyTG webhook получен, но TgAccountService не инициализирован")
            return JSONResponse({"error": {"message": "TgAccountService not configured"}}, status_code=503)

        if payload.result == "success":
            result = await container.tgaccounts_service.process_webhook(
                getmytg_purchase_id=payload.data.purchase.id,
                result_type=payload.result,
                country_code=payload.data.purchase.country_code,
                phone_number=payload.data.purchase.phone_number,
                verification_code=payload.data.verification.code,
                verification_password=payload.data.verification.password,
            )
        else:
            result = await container.tgaccounts_service.process_webhook(
                getmytg_purchase_id=payload.data.purchase.id,
                result_type=payload.result,
                country_code=payload.data.purchase.country_code,
                phone_number=payload.data.purchase.phone_number,
                error_message=payload.data.error.message,
            )

        if result.purchase is None:
            logger.warning("GetMyTG webhook: покупка getmytg_id=%s не найдена", payload.data.purchase.id)
            return JSONResponse({"result": {"message": "ignored"}})

        await _notify_user(getattr(request.app.state, "bot", None), result)
        return JSONResponse({"result": {"message": "ok"}})

    return router


def _normalize_webhook_path(path: str | None) -> str:
    normalized = (path or DEFAULT_WEBHOOK_PATH).strip() or DEFAULT_WEBHOOK_PATH
    return normalized if normalized.startswith("/") else f"/{normalized}"


def _verify_webhook_signature(request: Request, secret: str) -> bool:
    provided_signature = request.query_params.get(GetMyTGClient.WEBHOOK_SIGNATURE_QUERY_PARAM, "")
    if not provided_signature:
        return False
    return GetMyTGClient.verify_webhook_signature(
        path=request.url.path,
        provided_signature=provided_signature,
        secret=secret,
    )


async def _notify_user(bot: Bot | None, result: TgAccountWebhookResult) -> None:
    if not result.should_notify or result.purchase is None:
        return
    if bot is None:
        logger.warning(
            "GetMyTG webhook: bot не задан, уведомление не отправлено (telegram_id=%s)",
            result.purchase.telegram_id,
        )
        return
    try:
        await bot.send_message(
            result.purchase.telegram_id,
            _render_notification(result),
            parse_mode="HTML",
        )
    except AiogramError as error:
        logger.warning(
            "GetMyTG webhook: не удалось отправить уведомление telegram_id=%s: %s",
            result.purchase.telegram_id,
            error,
        )


def _render_notification(result: TgAccountWebhookResult) -> str:
    purchase = result.purchase
    if purchase is None:
        raise ValueError("Purchase is required to render GetMyTG webhook notification.")

    lines = [
        TG_ACCOUNTS_TEXT.PURCHASE_TITLE.format(purchase_id=purchase.id),
        TG_ACCOUNTS_TEXT.PURCHASE_COUNTRY.format(country=escape(purchase.country_code.upper())),
        TG_ACCOUNTS_TEXT.PURCHASE_PHONE.format(phone=escape(purchase.phone_number or "не получен")),
        TG_ACCOUNTS_TEXT.PURCHASE_AMOUNT.format(
            amount=escape(format_money(purchase.amount, purchase.currency))
        ),
    ]
    if result.result_type == "success":
        lines.insert(0, TG_ACCOUNTS_TEXT.WEBHOOK_SUCCESS_TITLE)
        if purchase.verification_code:
            lines.append(TG_ACCOUNTS_TEXT.PURCHASE_CODE.format(code=escape(purchase.verification_code)))
        if purchase.verification_password:
            lines.append(
                TG_ACCOUNTS_TEXT.PURCHASE_PASSWORD.format(
                    password=escape(purchase.verification_password)
                )
            )
        lines.extend(["", TG_ACCOUNTS_TEXT.WEBHOOK_SUCCESS_HINT])
        return "\n".join(lines)

    lines.insert(0, TG_ACCOUNTS_TEXT.WEBHOOK_FAILED_TITLE)
    reason = result.error_message or TG_ACCOUNTS_TEXT.WEBHOOK_FAILED_REASON_UNKNOWN
    lines.append(TG_ACCOUNTS_TEXT.WEBHOOK_FAILED_REASON.format(reason=escape(reason)))
    lines.extend(["", TG_ACCOUNTS_TEXT.WEBHOOK_FAILED_HINT])
    return "\n".join(lines)
