"""Обработчики для административного бота.

Содержит build_admin_router() — роутер с командами /start, списком диспутов,
модерацией сделок и обработкой заявок на вывод.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from html import escape

from aiogram import F, Router
from aiogram.exceptions import AiogramError
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message

from cerber_bot.container import AppContainer
from cerber_bot.keyboards.admin import (
    ADMIN_DEAL_PREFIX,
    ADMIN_DISPUTES_ACTION,
    ADMIN_HOME_ACTION,
    ADMIN_MODERATE_PREFIX,
    ADMIN_WITHDRAW_PREFIX,
    ADMIN_WITHDRAWALS_ACTION,
    build_admin_deal_keyboard,
    build_admin_home_keyboard,
    build_disputes_list_keyboard,
    build_withdrawals_list_keyboard,
)
from cerber_bot.services.deals import DealServiceError, DealView, WithdrawalRequestView
from cerber_bot.services.store import format_money
from cerber_bot.texts import ADMIN_TEXT, DEAL_HANDLER_TEXT

logger = logging.getLogger(__name__)


def _is_moderator(user_id: int, container: AppContainer) -> bool:
    return user_id in container.deal_service.moderator_ids


def _format_timestamp(value: object, *, short: bool = False) -> str:
    if not isinstance(value, datetime):
        return str(value)
    pattern = "%d.%m %H:%M UTC" if short else "%d.%m.%Y %H:%M UTC"
    return value.astimezone(timezone.utc).strftime(pattern)


def _format_deal_status(value: str) -> str:
    return DEAL_HANDLER_TEXT.deal_status_label(value)


def _render_admin_dashboard(disputes: int, withdrawals: int) -> str:
    lines = [
        ADMIN_TEXT.DASHBOARD_TITLE,
        ADMIN_TEXT.DASHBOARD_DISPUTES.format(count=disputes),
        ADMIN_TEXT.DASHBOARD_WITHDRAWALS.format(count=withdrawals),
    ]
    return "\n".join(lines)


def _render_disputes_list(deals: list[DealView]) -> str:
    lines = [ADMIN_TEXT.DISPUTES_TITLE]
    if not deals:
        lines.append(ADMIN_TEXT.DISPUTES_EMPTY)
        return "\n".join(lines)
    for deal in deals:
        lines.append("")
        lines.append(ADMIN_TEXT.DISPUTE_CARD.format(
            deal_id=deal.deal_id,
            amount=escape(format_money(deal.amount, deal.currency)),
            buyer=escape(deal.buyer.display_name),
            seller=escape(deal.seller.display_name),
            disputed_at=escape(_format_timestamp(deal.disputed_at, short=True)) if deal.disputed_at else "—",
        ))
    return "\n".join(lines)


def _render_admin_deal_view(deal: DealView) -> str:
    lines = [
        ADMIN_TEXT.DEAL_VIEW_TITLE.format(deal_id=deal.deal_id),
        ADMIN_TEXT.DEAL_VIEW_STATUS.format(status=escape(_format_deal_status(deal.status))),
        ADMIN_TEXT.DEAL_VIEW_BUYER.format(buyer=escape(deal.buyer.display_name)),
        ADMIN_TEXT.DEAL_VIEW_SELLER.format(seller=escape(deal.seller.display_name)),
        ADMIN_TEXT.DEAL_VIEW_AMOUNT.format(amount=escape(format_money(deal.amount, deal.currency))),
        ADMIN_TEXT.DEAL_VIEW_CREATED.format(created_at=escape(_format_timestamp(deal.created_at))),
    ]
    if deal.disputed_at is not None:
        lines.append(ADMIN_TEXT.DEAL_VIEW_DISPUTED.format(disputed_at=escape(_format_timestamp(deal.disputed_at))))
    lines.append("")
    lines.append(ADMIN_TEXT.DEAL_VIEW_TERMS.format(terms=escape(deal.terms)))
    lines.append("")
    lines.append(ADMIN_TEXT.DEAL_VIEW_MESSAGES_TITLE)
    if not deal.messages:
        lines.append(ADMIN_TEXT.DEAL_VIEW_NO_MESSAGES)
    else:
        for item in deal.messages[-8:]:
            lines.append(ADMIN_TEXT.DEAL_VIEW_MESSAGE_ROW.format(
                created_at=escape(_format_timestamp(item.created_at, short=True)),
                sender=escape(item.sender_display),
                body=escape(item.body),
            ))
    return "\n".join(lines)


def _render_withdrawals_list(requests: list[WithdrawalRequestView]) -> str:
    lines = [ADMIN_TEXT.WITHDRAWALS_TITLE]
    if not requests:
        lines.append(ADMIN_TEXT.WITHDRAWALS_EMPTY)
        return "\n".join(lines)
    for req in requests:
        lines.append("")
        lines.append(ADMIN_TEXT.WITHDRAWAL_CARD.format(
            request_id=req.request_id,
            amount=escape(format_money(req.amount_usdt, "USDT")),
            network=escape(req.network),
            telegram_id=req.telegram_id,
            address=escape(req.address),
        ))
    return "\n".join(lines)


def build_admin_router(container: AppContainer) -> Router:
    """Фабрика роутера для административного бота."""
    router = Router(name="admin")

    @router.message(CommandStart())
    async def handle_start(message: Message) -> None:
        if message.from_user is None or not _is_moderator(message.from_user.id, container):
            await message.answer(ADMIN_TEXT.ACCESS_DENIED)
            return

        disputes, withdrawals = await container.deal_service.get_admin_summary()
        await message.answer(
            ADMIN_TEXT.WELCOME + "\n\n" + _render_admin_dashboard(disputes, withdrawals),
            reply_markup=build_admin_home_keyboard(),
        )

    @router.callback_query(F.data == ADMIN_HOME_ACTION)
    async def handle_home(callback: CallbackQuery) -> None:
        if callback.from_user is None or not _is_moderator(callback.from_user.id, container):
            await callback.answer(ADMIN_TEXT.ACCESS_DENIED, show_alert=True)
            return

        disputes, withdrawals = await container.deal_service.get_admin_summary()
        text = _render_admin_dashboard(disputes, withdrawals)
        msg = callback.message
        if msg is not None:
            try:
                await msg.edit_text(text, reply_markup=build_admin_home_keyboard())
            except AiogramError:
                await msg.answer(text, reply_markup=build_admin_home_keyboard())
        await callback.answer()

    @router.callback_query(F.data == ADMIN_DISPUTES_ACTION)
    async def handle_disputes_list(callback: CallbackQuery) -> None:
        if callback.from_user is None or not _is_moderator(callback.from_user.id, container):
            await callback.answer(ADMIN_TEXT.ACCESS_DENIED, show_alert=True)
            return

        deals = await container.deal_service.list_disputed_deals()
        text = _render_disputes_list(deals)
        deal_ids = [d.deal_id for d in deals]
        markup = build_disputes_list_keyboard(deal_ids)
        msg = callback.message
        if msg is not None:
            try:
                await msg.edit_text(text, reply_markup=markup)
            except AiogramError:
                await msg.answer(text, reply_markup=markup)
        await callback.answer()

    @router.callback_query(F.data.startswith(ADMIN_DEAL_PREFIX))
    async def handle_deal_detail(callback: CallbackQuery) -> None:
        if callback.from_user is None or not _is_moderator(callback.from_user.id, container):
            await callback.answer(ADMIN_TEXT.ACCESS_DENIED, show_alert=True)
            return

        raw = (callback.data or "").removeprefix(ADMIN_DEAL_PREFIX)
        try:
            deal_id = int(raw)
        except ValueError:
            await callback.answer()
            return

        deal = await container.deal_service.get_deal_view_admin(deal_id)
        if deal is None:
            await callback.answer(DEAL_HANDLER_TEXT.CALLBACK_DEAL_NOT_FOUND, show_alert=True)
            return

        text = _render_admin_deal_view(deal)
        markup = build_admin_deal_keyboard(deal_id) if deal.status == "disputed" else build_admin_home_keyboard()
        msg = callback.message
        if msg is not None:
            try:
                await msg.edit_text(text, reply_markup=markup)
            except AiogramError:
                await msg.answer(text, reply_markup=markup)
        await callback.answer()

    @router.callback_query(F.data.startswith(ADMIN_MODERATE_PREFIX))
    async def handle_moderation(callback: CallbackQuery) -> None:
        if callback.from_user is None or not _is_moderator(callback.from_user.id, container):
            await callback.answer(ADMIN_TEXT.ACCESS_DENIED, show_alert=True)
            return

        raw = (callback.data or "").removeprefix(ADMIN_MODERATE_PREFIX)
        try:
            numeric_part, resolution = raw.split(":", 1)
            deal_id = int(numeric_part)
        except (ValueError, IndexError):
            await callback.answer()
            return

        try:
            result = await container.deal_service.resolve_dispute(callback.from_user.id, deal_id, resolution)
        except DealServiceError as error:
            await callback.answer(str(error), show_alert=True)
            return

        # Оповещаем участников через основной бот
        from cerber_bot.keyboards.deals import build_deal_open_keyboard
        from cerber_bot.handlers.menu import render_moderation_result_notification

        user_bot = container.user_bot
        if user_bot is not None:
            notification = render_moderation_result_notification(result)
            for tid in (result.buyer_telegram_id, result.seller_telegram_id):
                try:
                    await user_bot.send_message(tid, notification, reply_markup=build_deal_open_keyboard(result.deal_id))
                except AiogramError:
                    pass

        msg = callback.message
        if msg is not None:
            try:
                await msg.edit_text(ADMIN_TEXT.MODERATION_APPLIED, reply_markup=build_admin_home_keyboard())
            except AiogramError:
                await msg.answer(ADMIN_TEXT.MODERATION_APPLIED, reply_markup=build_admin_home_keyboard())
        await callback.answer(ADMIN_TEXT.MODERATION_APPLIED)

    @router.callback_query(F.data == ADMIN_WITHDRAWALS_ACTION)
    async def handle_withdrawals_list(callback: CallbackQuery) -> None:
        if callback.from_user is None or not _is_moderator(callback.from_user.id, container):
            await callback.answer(ADMIN_TEXT.ACCESS_DENIED, show_alert=True)
            return

        requests = await container.deal_service.list_pending_withdrawals()
        text = _render_withdrawals_list(requests)
        request_ids = [r.request_id for r in requests]
        markup = build_withdrawals_list_keyboard(request_ids)
        msg = callback.message
        if msg is not None:
            try:
                await msg.edit_text(text, reply_markup=markup)
            except AiogramError:
                await msg.answer(text, reply_markup=markup)
        await callback.answer()

    @router.callback_query(F.data.startswith(ADMIN_WITHDRAW_PREFIX))
    async def handle_withdrawal_moderation(callback: CallbackQuery) -> None:
        if callback.from_user is None or not _is_moderator(callback.from_user.id, container):
            await callback.answer(ADMIN_TEXT.ACCESS_DENIED, show_alert=True)
            return

        raw = (callback.data or "").removeprefix(ADMIN_WITHDRAW_PREFIX)
        try:
            numeric_part, action = raw.split(":", 1)
            request_id = int(numeric_part)
        except (ValueError, IndexError):
            await callback.answer()
            return

        try:
            result = await container.deal_service.moderate_withdrawal_request(callback.from_user.id, request_id, action)
        except DealServiceError as error:
            await callback.answer(str(error), show_alert=True)
            return

        # Оповещаем владельца заявки через основной бот
        from cerber_bot.handlers.menu import render_withdrawal_status_notification
        from cerber_bot.keyboards.deals import build_deal_home_keyboard

        user_bot = container.user_bot
        if user_bot is not None:
            try:
                await user_bot.send_message(
                    result.owner_telegram_id,
                    render_withdrawal_status_notification(result.request),
                    reply_markup=build_deal_home_keyboard(),
                )
            except AiogramError:
                pass

        msg = callback.message
        if msg is not None:
            try:
                await msg.edit_text(ADMIN_TEXT.WITHDRAWAL_PROCESSED, reply_markup=build_admin_home_keyboard())
            except AiogramError:
                await msg.answer(ADMIN_TEXT.WITHDRAWAL_PROCESSED, reply_markup=build_admin_home_keyboard())
        await callback.answer(ADMIN_TEXT.WITHDRAWAL_PROCESSED)

    return router
