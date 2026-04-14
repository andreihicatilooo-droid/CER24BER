"""HTTP-сервер для callback-уведомлений NicePay.

Поднимает aiohttp endpoint, принимает GET/POST запросы, проверяет подпись,
обрабатывает платёж и уведомляет пользователя через Telegram.
"""

from __future__ import annotations

import logging
from html import escape

from aiohttp import web
from aiogram import Bot
from aiogram.exceptions import AiogramError

from cerber_bot.container import AppContainer
from cerber_bot.keyboards.storefront import build_wallet_keyboard
from cerber_bot.services.payments import PaymentCallbackResult, PaymentFlowError, format_money
from cerber_bot.texts import PAYMENT_TEXT


logger = logging.getLogger(__name__)


class NicePayWebhookServer:
    def __init__(self, *, container: AppContainer, bot: Bot) -> None:
        self.container = container
        self.bot = bot
        self._runner: web.AppRunner | None = None

    @property
    def is_enabled(self) -> bool:
        return self.container.payment_service.is_configured

    @property
    def host(self) -> str:
        return self.container.settings.nicepay_webhook_host

    @property
    def port(self) -> int:
        return self.container.settings.nicepay_webhook_port

    @property
    def path(self) -> str:
        value = self.container.settings.nicepay_webhook_path.strip() or "/webhooks/nicepay"
        return value if value.startswith("/") else f"/{value}"

    async def start(self) -> None:
        if not self.is_enabled:
            logger.info("NicePay webhook server disabled: merchant credentials are not configured.")
            return

        app = web.Application()
        app.router.add_get(self.path, self.handle_callback)
        app.router.add_post(self.path, self.handle_callback)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, host=self.host, port=self.port)
        await site.start()
        logger.info("NicePay webhook server listening on http://%s:%s%s", self.host, self.port, self.path)

    async def stop(self) -> None:
        if self._runner is None:
            return
        await self._runner.cleanup()
        self._runner = None

    async def handle_callback(self, request: web.Request) -> web.Response:
        try:
            parameters = await extract_callback_parameters(request)
            result = await self.container.payment_service.process_callback(parameters)
        except PaymentFlowError as error:
            logger.warning("NicePay callback rejected: %s", error)
            return web.json_response({"error": {"message": str(error)}}, status=400)

        await notify_user(self.bot, result)
        return web.json_response({"result": {"message": PAYMENT_TEXT.CALLBACK_SUCCESS_RESPONSE}})


async def extract_callback_parameters(request: web.Request) -> dict[str, str]:
    if request.method == "GET":
        return {key: value for key, value in request.query.items()}

    if request.content_type.lower().startswith("application/json"):
        payload = await request.json()
        if not isinstance(payload, dict):
            raise PaymentFlowError(PAYMENT_TEXT.CALLBACK_JSON_OBJECT_REQUIRED)
        return {str(key): str(value) for key, value in payload.items()}

    payload = await request.post()
    return {str(key): str(value) for key, value in payload.items()}


async def notify_user(bot: Bot, result: PaymentCallbackResult) -> None:
    try:
        await bot.send_message(
            result.telegram_id,
            render_payment_result(result),
            reply_markup=build_wallet_keyboard(),
        )
    except AiogramError as error:
        logger.warning("Failed to send NicePay result to user %s: %s", result.telegram_id, error)


def render_payment_result(result: PaymentCallbackResult) -> str:
    if result.result == "success":
        lines = [
            PAYMENT_TEXT.SUCCESS_TITLE,
            PAYMENT_TEXT.SUCCESS_AMOUNT.format(amount=escape(format_money(result.amount, result.currency))),
        ]
        if result.credited_amount is not None and result.credited_currency is not None:
            lines.append(PAYMENT_TEXT.SUCCESS_CREDITED.format(amount=escape(format_money(result.credited_amount, result.credited_currency))))
        if result.balance_after is not None:
            balance_currency = result.credited_currency or result.currency
            lines.append(PAYMENT_TEXT.SUCCESS_BALANCE.format(amount=escape(format_money(result.balance_after, balance_currency))))
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