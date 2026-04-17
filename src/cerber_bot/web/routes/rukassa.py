"""FastAPI-маршрут для webhook-уведомлений Rukassa.

Принимает POST на /webhooks/rukassa (настраивается через RUKASSA_WEBHOOK_PATH).
Подпись верифицируется через RukassaClient, результат зачисляется на баланс,
пользователь получает Telegram-уведомление.

Формат запроса: multipart/form-data или application/x-www-form-urlencoded
Заголовок: Signature = SHA-256("{id}|{createdDateTime}|{amount}" + token)
"""

from __future__ import annotations

import logging
from html import escape

from aiogram import Bot
from aiogram.exceptions import AiogramError
from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse

from cerber_bot.keyboards.storefront import build_wallet_keyboard
from cerber_bot.services.payments import PaymentCallbackResult, PaymentFlowError
from cerber_bot.services.store import format_money
from cerber_bot.texts import RUKASSA_TEXT
from cerber_bot.web.deps import get_container

logger = logging.getLogger(__name__)

router = APIRouter(tags=["webhooks"])


async def _notify_user(bot: Bot | None, result: PaymentCallbackResult) -> None:
    """Отправить Telegram-сообщение пользователю о результате платежа."""
    if bot is None:
        logger.warning(
            "Rukassa webhook: bot не задан, уведомление не отправлено (telegram_id=%s)",
            result.telegram_id,
        )
        return
    try:
        await bot.send_message(
            result.telegram_id,
            _render_payment_result(result),
            reply_markup=build_wallet_keyboard(),
        )
    except AiogramError as error:
        logger.warning(
            "Rukassa webhook: не удалось отправить уведомление telegram_id=%s: %s",
            result.telegram_id,
            error,
        )


def _render_payment_result(result: PaymentCallbackResult) -> str:
    if result.result == "success":
        lines = [
            RUKASSA_TEXT.SUCCESS_TITLE,
            RUKASSA_TEXT.SUCCESS_AMOUNT.format(amount=escape(format_money(result.amount, result.currency))),
        ]
        if result.credited_amount is not None and result.credited_currency is not None:
            lines.append(RUKASSA_TEXT.SUCCESS_CREDITED.format(
                amount=escape(format_money(result.credited_amount, result.credited_currency))
            ))
        if result.balance_after is not None:
            balance_currency = result.credited_currency or result.currency
            lines.append(RUKASSA_TEXT.SUCCESS_BALANCE.format(
                amount=escape(format_money(result.balance_after, balance_currency))
            ))
        if result.method:
            lines.append(RUKASSA_TEXT.METHOD.format(method=escape(result.method)))
        lines.append(RUKASSA_TEXT.SUCCESS_HINT)
        return "\n".join(lines)

    lines = [
        RUKASSA_TEXT.ERROR_TITLE,
        RUKASSA_TEXT.ERROR_AMOUNT.format(amount=escape(format_money(result.amount, result.currency))),
        RUKASSA_TEXT.ERROR_HINT,
    ]
    return "\n".join(lines)


@router.post("/webhooks/rukassa")
async def rukassa_webhook(request: Request) -> PlainTextResponse:
    """Обработать POST-уведомление от Rukassa."""
    container = get_container(request)
    bot: Bot | None = getattr(request.app.state, "bot", None)

    signature = request.headers.get("Signature", "")
    if not signature:
        logger.warning("Rukassa webhook: отсутствует Signature-заголовок")
        return PlainTextResponse("Missing Signature", status_code=400)

    form = await request.form()
    form_data = {str(k): str(v) for k, v in form.items()}

    try:
        result = await container.payment_service.process_rukassa_webhook(
            form_data,
            signature_header=signature,
        )
    except PaymentFlowError as error:
        logger.warning("Rukassa webhook ошибка обработки: %s | form=%s", error, form_data)
        return PlainTextResponse("Error", status_code=400)
    except Exception:
        logger.exception("Rukassa webhook: непредвиденная ошибка | form=%s", form_data)
        return PlainTextResponse("Internal error", status_code=500)

    await _notify_user(bot, result)
    return PlainTextResponse("OK", status_code=200)
