"""FastAPI-маршрут для webhook-уведомлений NicePay.

Принимает GET/POST на /webhooks/nicepay, проверяет подпись через payment_service,
обрабатывает платёж и уведомляет пользователя через Telegram.
"""

from __future__ import annotations

import logging
from html import escape

from aiogram import Bot
from aiogram.exceptions import AiogramError
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from cerber_bot.keyboards.storefront import build_wallet_keyboard
from cerber_bot.services.payments import PaymentCallbackResult, PaymentFlowError
from cerber_bot.services.store import format_money
from cerber_bot.texts import PAYMENT_TEXT
from cerber_bot.web.deps import get_container

logger = logging.getLogger(__name__)

router = APIRouter(tags=["webhooks"])


async def _extract_parameters(request: Request) -> dict[str, object]:
    """Извлечь параметры из GET-строки или тела POST (JSON / form)."""
    if request.method == "GET":
        return dict(request.query_params)

    content_type = request.headers.get("content-type", "").lower()
    if "application/json" in content_type:
        payload = await request.json()
        if not isinstance(payload, dict):
            raise PaymentFlowError(PAYMENT_TEXT.CALLBACK_JSON_OBJECT_REQUIRED)
        return payload

    form = await request.form()
    return dict(form)


async def _notify_user(bot: Bot | None, result: PaymentCallbackResult) -> None:
    """Отправить Telegram-сообщение пользователю о результате платежа."""
    if bot is None:
        logger.warning("NicePay webhook: bot не задан, уведомление не отправлено (telegram_id=%s)", result.telegram_id)
        return
    try:
        await bot.send_message(
            result.telegram_id,
            _render_payment_result(result),
            reply_markup=build_wallet_keyboard(),
        )
    except AiogramError as error:
        logger.warning("NicePay webhook: не удалось отправить уведомление telegram_id=%s: %s", result.telegram_id, error)


def _render_payment_result(result: PaymentCallbackResult) -> str:
    if result.result == "success":
        lines = [
            PAYMENT_TEXT.SUCCESS_TITLE,
            PAYMENT_TEXT.SUCCESS_AMOUNT.format(amount=escape(format_money(result.amount, result.currency))),
        ]
        if result.credited_amount is not None and result.credited_currency is not None:
            lines.append(PAYMENT_TEXT.SUCCESS_CREDITED.format(
                amount=escape(format_money(result.credited_amount, result.credited_currency))
            ))
        if result.balance_after is not None:
            balance_currency = result.credited_currency or result.currency
            lines.append(PAYMENT_TEXT.SUCCESS_BALANCE.format(
                amount=escape(format_money(result.balance_after, balance_currency))
            ))
        if result.method:
            lines.append(PAYMENT_TEXT.METHOD.format(method=escape(result.method)))
        lines.append(PAYMENT_TEXT.SUCCESS_HINT)
        return "\n".join(lines)

    lines = [
        PAYMENT_TEXT.ERROR_TITLE,
        PAYMENT_TEXT.ERROR_AMOUNT.format(amount=escape(format_money(result.amount, result.currency))),
    ]
    if result.method:
        lines.append(PAYMENT_TEXT.METHOD.format(method=escape(result.method)))
    lines.append(PAYMENT_TEXT.ERROR_HINT)
    return "\n".join(lines)


async def _handle_nicepay(request: Request) -> JSONResponse:
    container = get_container(request)
    bot: Bot | None = getattr(request.app.state, "bot", None)

    if not container.payment_service.is_configured:
        logger.warning("NicePay webhook получен, но платёжный сервис не настроен")
        return JSONResponse({"error": {"message": "Payment service not configured"}}, status_code=503)

    try:
        parameters = await _extract_parameters(request)
        result = await container.payment_service.process_callback(parameters)
    except PaymentFlowError as error:
        logger.warning("NicePay webhook отклонён: %s", error)
        return JSONResponse({"error": {"message": str(error)}}, status_code=400)

    await _notify_user(bot, result)
    return JSONResponse({"result": {"message": PAYMENT_TEXT.CALLBACK_SUCCESS_RESPONSE}})


@router.get("/webhooks/nicepay")
async def nicepay_webhook_get(request: Request) -> JSONResponse:
    return await _handle_nicepay(request)


@router.post("/webhooks/nicepay")
async def nicepay_webhook_post(request: Request) -> JSONResponse:
    return await _handle_nicepay(request)
