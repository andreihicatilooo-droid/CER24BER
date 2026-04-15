"""Обработчики для административного бота.

Содержит build_admin_router() — роутер с командами /start, списком диспутов,
модерацией сделок, обработкой заявок на вывод, чатом в диспутах,
редактированием баланса пользователей и панелью статуса.
"""

from __future__ import annotations

import asyncio
import logging
import urllib.error
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal
from html import escape
from pathlib import Path

from aiogram import F, Router
from aiogram.exceptions import AiogramError
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, ForceReply, InlineKeyboardButton, InlineKeyboardMarkup, Message

from cerber_bot.container import AppContainer
from cerber_bot.keyboards.admin import (
    ADMIN_CHECK_SERVICES_ACTION,
    ADMIN_DEAL_CHAT_PREFIX,
    ADMIN_DEAL_PREFIX,
    ADMIN_DEAL_REFRESH_PREFIX,
    ADMIN_DISPUTES_ACTION,
    ADMIN_HOME_ACTION,
    ADMIN_LOGS_BOT_ACTION,
    ADMIN_LOGS_ERR_ACTION,
    ADMIN_LOGS_TUNNEL_ACTION,
    ADMIN_MODERATE_PREFIX,
    ADMIN_STATS_ACTION,
    ADMIN_STATUS_ACTION,
    ADMIN_USER_BAL_PREFIX,
    ADMIN_USERS_ACTION,
    ADMIN_WITHDRAW_PREFIX,
    ADMIN_WITHDRAWALS_ACTION,
    build_admin_deal_keyboard,
    build_admin_deal_readonly_keyboard,
    build_admin_home_keyboard,
    build_disputes_list_keyboard,
    build_status_keyboard,
    build_user_profile_keyboard,
    build_withdrawals_list_keyboard,
)
from cerber_bot.services.deals import DealServiceError, DealStateError, DealView, WithdrawalRequestView
from cerber_bot.services.store import format_money
from cerber_bot.texts import ADMIN_TEXT, DEAL_HANDLER_TEXT

logger = logging.getLogger(__name__)

# ── Пути к логам (относительно корня проекта) ─────────────────
_ROOT = Path(__file__).resolve().parents[3]
_LOGS_DIR = _ROOT / "logs"
_LOG_FILES = {
    "bot": _LOGS_DIR / "bot.log",
    "err": _LOGS_DIR / "bot_error.log",
    "tunnel": _LOGS_DIR / "tunnel.log",
}
_LOG_TAIL_LINES = 30

# ── Сервисы для проверки доступности ──────────────────────────
_SERVICE_CHECKS: list[tuple[str, str]] = [
    ("Telegram API", "https://api.telegram.org"),
    ("NicePay", "https://nicepay.io"),
    ("GiftAPI", "https://api.giftapi.io"),
]


class AdminStates(StatesGroup):  # noqa: D101
    waiting_chat_message = State()       # data: {"deal_id": int}
    waiting_user_identifier = State()    # поиск пользователя
    waiting_balance_delta = State()      # data: {"telegram_id": int, "balance": str, "currency": str}


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


# ── Вспомогательные функции для статуса ──────────────────────────────────────

def _tail_log(key: str) -> str:
    """Читает последние N строк лог-файла (синхронно, вызывается через asyncio.to_thread)."""
    path = _LOG_FILES.get(key)
    if path is None or not path.exists():
        return ADMIN_TEXT.STATUS_LOG_NOT_FOUND
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ADMIN_TEXT.STATUS_LOG_NOT_FOUND
    if not lines:
        return ADMIN_TEXT.STATUS_LOG_EMPTY
    tail = lines[-_LOG_TAIL_LINES:]
    return "\n".join(f"<code>{escape(ln)}</code>" for ln in tail)


def _check_url_sync(name: str, url: str) -> str:
    """HEAD-запрос. Возвращает строку статуса (синхронно)."""
    try:
        req = urllib.request.Request(url, method="HEAD")
        req.add_header("User-Agent", "CERBER-Admin/1.0")
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        resp = opener.open(req, timeout=8)
        return ADMIN_TEXT.STATUS_SERVICE_OK.format(name=name)
    except urllib.error.HTTPError:
        # Сервер ответил — значит доступен
        return ADMIN_TEXT.STATUS_SERVICE_OK.format(name=name)
    except Exception as exc:
        reason = str(exc)[:60]
        return ADMIN_TEXT.STATUS_SERVICE_FAIL.format(name=name, reason=escape(reason))


async def _render_status_text() -> str:
    """Формирует текст панели статуса с проверкой сервисов."""
    lines = [ADMIN_TEXT.STATUS_TITLE, ADMIN_TEXT.STATUS_SERVICES_HEADER]
    checks = await asyncio.gather(*[
        asyncio.to_thread(_check_url_sync, name, url)
        for name, url in _SERVICE_CHECKS
    ])
    lines.extend(checks)
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

    # ── Обновление карточки сделки ────────────────────────────────────────────

    @router.callback_query(F.data.startswith(ADMIN_DEAL_REFRESH_PREFIX))
    async def handle_deal_refresh(callback: CallbackQuery) -> None:
        if callback.from_user is None or not _is_moderator(callback.from_user.id, container):
            await callback.answer(ADMIN_TEXT.ACCESS_DENIED, show_alert=True)
            return

        raw = (callback.data or "").removeprefix(ADMIN_DEAL_REFRESH_PREFIX)
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
        markup = build_admin_deal_keyboard(deal_id) if deal.status == "disputed" else build_admin_deal_readonly_keyboard(deal_id)
        msg = callback.message
        if msg is not None:
            try:
                await msg.edit_text(text, reply_markup=markup)
            except AiogramError:
                await msg.answer(text, reply_markup=markup)
        await callback.answer()

    # ── Чат модератора в диспуте ──────────────────────────────────────────────

    @router.callback_query(F.data.startswith(ADMIN_DEAL_CHAT_PREFIX))
    async def handle_deal_chat_start(callback: CallbackQuery, state: FSMContext) -> None:
        if callback.from_user is None or not _is_moderator(callback.from_user.id, container):
            await callback.answer(ADMIN_TEXT.ACCESS_DENIED, show_alert=True)
            return

        raw = (callback.data or "").removeprefix(ADMIN_DEAL_CHAT_PREFIX)
        try:
            deal_id = int(raw)
        except ValueError:
            await callback.answer()
            return

        deal = await container.deal_service.get_deal_view_admin(deal_id)
        if deal is None:
            await callback.answer(DEAL_HANDLER_TEXT.CALLBACK_DEAL_NOT_FOUND, show_alert=True)
            return

        if deal.status not in {"active", "disputed"}:
            await callback.answer(ADMIN_TEXT.CHAT_DEAL_NOT_ACTIVE, show_alert=True)
            return

        await state.set_state(AdminStates.waiting_chat_message)
        await state.update_data(deal_id=deal_id)

        prompt = ADMIN_TEXT.CHAT_INPUT_PROMPT.format(
            deal_id=deal_id,
            buyer=escape(deal.buyer.display_name),
            seller=escape(deal.seller.display_name),
        )
        msg = callback.message
        if msg is not None:
            await msg.answer(prompt, reply_markup=ForceReply(selective=True))
        await callback.answer()

    @router.message(AdminStates.waiting_chat_message)
    async def handle_deal_chat_message(message: Message, state: FSMContext) -> None:
        if message.from_user is None or not _is_moderator(message.from_user.id, container):
            await state.clear()
            return

        data = await state.get_data()
        deal_id = int(data.get("deal_id", 0))
        body = (message.text or "").strip()

        if not body:
            await message.answer(ADMIN_TEXT.CHAT_DEAL_NOT_ACTIVE)
            await state.clear()
            return

        try:
            _view, buyer_id, seller_id = await container.deal_service.send_moderator_message(
                message.from_user.id,
                deal_id=deal_id,
                body=body,
            )
        except (DealServiceError, DealStateError) as exc:
            await message.answer(str(exc))
            await state.clear()
            return

        await state.clear()

        # Ретранслируем через основной бот покупателю и продавцу
        from cerber_bot.keyboards.deals import build_deal_open_keyboard
        user_bot = container.user_bot
        if user_bot is not None:
            notification = ADMIN_TEXT.CHAT_RELAY_NOTIFICATION.format(deal_id=deal_id, body=escape(body))
            for tid in (buyer_id, seller_id):
                try:
                    await user_bot.send_message(tid, notification, reply_markup=build_deal_open_keyboard(deal_id))
                except AiogramError:
                    pass

        await message.answer(ADMIN_TEXT.CHAT_SENT.format(deal_id=deal_id))

    # ── Управление балансом пользователей ─────────────────────────────────────

    @router.callback_query(F.data == ADMIN_USERS_ACTION)
    async def handle_users(callback: CallbackQuery, state: FSMContext) -> None:
        if callback.from_user is None or not _is_moderator(callback.from_user.id, container):
            await callback.answer(ADMIN_TEXT.ACCESS_DENIED, show_alert=True)
            return

        await state.set_state(AdminStates.waiting_user_identifier)
        msg = callback.message
        if msg is not None:
            await msg.answer(ADMIN_TEXT.USERS_FIND_PROMPT, reply_markup=ForceReply(selective=True))
        await callback.answer()

    @router.message(AdminStates.waiting_user_identifier)
    async def handle_user_identifier(message: Message, state: FSMContext) -> None:
        if message.from_user is None or not _is_moderator(message.from_user.id, container):
            await state.clear()
            return

        identifier = (message.text or "").strip()
        await state.clear()

        user = await container.build_user_service().find_user(identifier)
        if user is None:
            await message.answer(ADMIN_TEXT.USER_NOT_FOUND)
            return

        currency = user.balance_currency or "USD"
        lines = [
            ADMIN_TEXT.USER_PROFILE_TITLE.format(telegram_id=user.telegram_id),
            ADMIN_TEXT.USER_PROFILE_NAME.format(name=escape(user.first_name or "—")),
        ]
        if user.username:
            lines.append(ADMIN_TEXT.USER_PROFILE_USERNAME.format(username=escape(user.username)))
        lines.append(ADMIN_TEXT.USER_PROFILE_BALANCE.format(
            balance=format_money(user.balance, currency), currency="",
        ).rstrip())
        lines.append(ADMIN_TEXT.USER_PROFILE_HELD.format(
            held=format_money(user.held_balance, currency), currency="",
        ).rstrip())
        await message.answer("\n".join(lines), reply_markup=build_user_profile_keyboard(user.telegram_id))

    @router.callback_query(F.data.startswith(ADMIN_USER_BAL_PREFIX))
    async def handle_balance_edit_start(callback: CallbackQuery, state: FSMContext) -> None:
        if callback.from_user is None or not _is_moderator(callback.from_user.id, container):
            await callback.answer(ADMIN_TEXT.ACCESS_DENIED, show_alert=True)
            return

        # adm:ubal:123456789:add  или  adm:ubal:123456789:sub
        raw = (callback.data or "").removeprefix(ADMIN_USER_BAL_PREFIX)
        try:
            tid_str, direction = raw.rsplit(":", 1)
            telegram_id = int(tid_str)
        except (ValueError, IndexError):
            await callback.answer()
            return

        user = await container.build_user_service().get_profile(telegram_id)
        if user is None:
            await callback.answer(ADMIN_TEXT.USER_NOT_FOUND, show_alert=True)
            return

        currency = user.balance_currency or "USD"
        await state.set_state(AdminStates.waiting_balance_delta)
        await state.update_data(
            telegram_id=telegram_id,
            balance=str(user.balance),
            currency=currency,
            direction=direction,
        )
        prompt = ADMIN_TEXT.BALANCE_DELTA_PROMPT.format(
            balance=format_money(user.balance, currency),
            currency=currency,
        )
        msg = callback.message
        if msg is not None:
            await msg.answer(prompt, reply_markup=ForceReply(selective=True))
        await callback.answer()

    @router.message(AdminStates.waiting_balance_delta)
    async def handle_balance_delta(message: Message, state: FSMContext) -> None:
        if message.from_user is None or not _is_moderator(message.from_user.id, container):
            await state.clear()
            return

        data = await state.get_data()
        telegram_id: int = int(data["telegram_id"])
        currency: str = data["currency"]
        direction: str = data.get("direction", "add")
        raw_input = (message.text or "").strip().lstrip("+")

        try:
            delta = Decimal(raw_input)
        except Exception:
            await message.answer(ADMIN_TEXT.BALANCE_DELTA_INVALID)
            await state.clear()
            return

        # Направление из кнопки
        if direction == "sub":
            delta = -abs(delta)
        else:
            delta = abs(delta)

        try:
            old_balance, updated = await container.build_user_service().adjust_balance(
                telegram_id,
                delta=delta,
                admin_id=message.from_user.id,
            )
        except ValueError as exc:
            await message.answer(str(exc))
            await state.clear()
            return

        await state.clear()
        await message.answer(
            ADMIN_TEXT.BALANCE_ADJUSTED.format(
                old=format_money(old_balance, currency),
                new=format_money(updated.balance, currency),
                currency=currency,
            ),
            reply_markup=build_user_profile_keyboard(telegram_id),
        )

    # ── Статистика пользователей ──────────────────────────────────────────────

    @router.callback_query(F.data == ADMIN_STATS_ACTION)
    async def handle_stats(callback: CallbackQuery) -> None:
        if callback.from_user is None or not _is_moderator(callback.from_user.id, container):
            await callback.answer(ADMIN_TEXT.ACCESS_DENIED, show_alert=True)
            return
        await callback.answer(ADMIN_TEXT.CALLBACK_WAIT)

        stats = await container.build_user_service().get_stats()
        text = "\n".join([
            ADMIN_TEXT.STATS_TITLE,
            ADMIN_TEXT.STATS_TOTAL.format(count=stats.total),
            ADMIN_TEXT.STATS_ACTIVE_7D.format(count=stats.active_7d),
            ADMIN_TEXT.STATS_ACTIVE_24H.format(count=stats.active_24h),
        ])
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=ADMIN_TEXT.BTN_HOME, callback_data=ADMIN_HOME_ACTION)],
        ])
        msg = callback.message
        if msg is not None:
            try:
                await msg.edit_text(text, reply_markup=keyboard)
            except Exception:
                await msg.answer(text, reply_markup=keyboard)

    # ── Статус системы ────────────────────────────────────────────────────────

    @router.callback_query(F.data == ADMIN_STATUS_ACTION)
    async def handle_status(callback: CallbackQuery) -> None:
        if callback.from_user is None or not _is_moderator(callback.from_user.id, container):
            await callback.answer(ADMIN_TEXT.ACCESS_DENIED, show_alert=True)
            return
        await callback.answer(ADMIN_TEXT.CALLBACK_WAIT)

        text = await _render_status_text()
        msg = callback.message
        if msg is not None:
            try:
                await msg.edit_text(text, reply_markup=build_status_keyboard())
            except AiogramError:
                await msg.answer(text, reply_markup=build_status_keyboard())

    @router.callback_query(F.data == ADMIN_CHECK_SERVICES_ACTION)
    async def handle_check_services(callback: CallbackQuery) -> None:
        if callback.from_user is None or not _is_moderator(callback.from_user.id, container):
            await callback.answer(ADMIN_TEXT.ACCESS_DENIED, show_alert=True)
            return
        await callback.answer(ADMIN_TEXT.CALLBACK_WAIT)

        text = await _render_status_text()
        msg = callback.message
        if msg is not None:
            try:
                await msg.edit_text(text, reply_markup=build_status_keyboard())
            except AiogramError:
                await msg.answer(text, reply_markup=build_status_keyboard())

    async def _send_log(callback: CallbackQuery, log_key: str, log_name: str) -> None:
        tail = await asyncio.to_thread(_tail_log, log_key)
        header = ADMIN_TEXT.STATUS_LOGS_HEADER.format(name=log_name, n=_LOG_TAIL_LINES)
        text = f"{header}\n\n{tail}"
        msg = callback.message
        if msg is not None:
            try:
                await msg.edit_text(text, reply_markup=build_status_keyboard())
            except AiogramError:
                await msg.answer(text, reply_markup=build_status_keyboard())
        await callback.answer()

    @router.callback_query(F.data == ADMIN_LOGS_BOT_ACTION)
    async def handle_log_bot(callback: CallbackQuery) -> None:
        if callback.from_user is None or not _is_moderator(callback.from_user.id, container):
            await callback.answer(ADMIN_TEXT.ACCESS_DENIED, show_alert=True)
            return
        await _send_log(callback, "bot", "бот")

    @router.callback_query(F.data == ADMIN_LOGS_ERR_ACTION)
    async def handle_log_err(callback: CallbackQuery) -> None:
        if callback.from_user is None or not _is_moderator(callback.from_user.id, container):
            await callback.answer(ADMIN_TEXT.ACCESS_DENIED, show_alert=True)
            return
        await _send_log(callback, "err", "ошибки")

    @router.callback_query(F.data == ADMIN_LOGS_TUNNEL_ACTION)
    async def handle_log_tunnel(callback: CallbackQuery) -> None:
        if callback.from_user is None or not _is_moderator(callback.from_user.id, container):
            await callback.answer(ADMIN_TEXT.ACCESS_DENIED, show_alert=True)
            return
        await _send_log(callback, "tunnel", "туннель")

    return router
