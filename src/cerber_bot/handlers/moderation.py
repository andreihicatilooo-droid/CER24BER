"""Меню администратора/гаранта в основном боте и привязка админ-группы.

Команды:
- /admin, /guarantor — меню модератора (диспуты, выводы, статистика);
- /connect_group — в группе: привязать её как админ-группу CERBER TRADE;
- /disconnect_group — отвязать группу.

Уведомления о диспутах и заявках на вывод отправляются в привязанную группу;
для каждого диспута в форум-группе создаётся отдельная ветка.
"""

from __future__ import annotations

import logging
from html import escape

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from cerber_bot.container import AppContainer
from cerber_bot.keyboards.deals import build_moderator_deal_keyboard, build_moderator_withdrawal_keyboard
from cerber_bot.services.store import format_money
from cerber_bot.texts import ADMIN_GROUP_TEXT, MOD_MENU_TEXT


logger = logging.getLogger(__name__)

MOD_HOME_ACTION = "mod:home"
MOD_DISPUTES_ACTION = "mod:disputes"
MOD_WITHDRAWALS_ACTION = "mod:withdrawals"
MOD_STATS_ACTION = "mod:stats"
MOD_DEAL_PREFIX = "mod:deal:"

GROUP_CHAT_TYPES = {"group", "supergroup"}


def build_mod_home_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=MOD_MENU_TEXT.BTN_DISPUTES, callback_data=MOD_DISPUTES_ACTION),
            InlineKeyboardButton(text=MOD_MENU_TEXT.BTN_WITHDRAWALS, callback_data=MOD_WITHDRAWALS_ACTION),
        ],
        [
            InlineKeyboardButton(text=MOD_MENU_TEXT.BTN_STATS, callback_data=MOD_STATS_ACTION),
            InlineKeyboardButton(text=MOD_MENU_TEXT.BTN_REFRESH, callback_data=MOD_HOME_ACTION),
        ],
    ])


def build_mod_disputes_keyboard(deal_ids: list[int]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=f"⚖️ Диспут #{deal_id}", callback_data=f"{MOD_DEAL_PREFIX}{deal_id}")]
        for deal_id in deal_ids
    ]
    rows.append([InlineKeyboardButton(text=MOD_MENU_TEXT.BTN_REFRESH, callback_data=MOD_HOME_ACTION)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_moderation_router(container: AppContainer) -> Router:
    router = Router(name="moderation")

    def is_moderator(telegram_id: int | None) -> bool:
        return telegram_id is not None and telegram_id in container.deal_service.moderator_ids

    # ── Привязка админ-группы ──────────────────────────────

    @router.message(Command("connect_group"))
    async def handle_connect_group(message: Message) -> None:
        if not is_moderator(message.from_user.id if message.from_user else None):
            await message.answer(ADMIN_GROUP_TEXT.CONNECT_ONLY_MODERATOR)
            return
        if message.chat.type not in GROUP_CHAT_TYPES:
            await message.answer(ADMIN_GROUP_TEXT.CONNECT_ONLY_GROUP)
            return

        is_forum = bool(getattr(message.chat, "is_forum", False))
        await container.admin_group_service.connect_group(message.chat.id, is_forum=is_forum)
        hint = ADMIN_GROUP_TEXT.CONNECTED_FORUM_HINT if is_forum else ADMIN_GROUP_TEXT.CONNECTED_NO_FORUM_HINT
        await message.answer(f"{ADMIN_GROUP_TEXT.CONNECTED}\n{hint}")

    @router.message(Command("disconnect_group"))
    async def handle_disconnect_group(message: Message) -> None:
        if not is_moderator(message.from_user.id if message.from_user else None):
            await message.answer(ADMIN_GROUP_TEXT.CONNECT_ONLY_MODERATOR)
            return
        await container.admin_group_service.disconnect_group()
        await message.answer(ADMIN_GROUP_TEXT.DISCONNECTED)

    # ── Меню администратора / гаранта ──────────────────────

    @router.message(Command("admin", "guarantor", "moderator"))
    async def handle_mod_menu_command(message: Message, state: FSMContext) -> None:
        if not is_moderator(message.from_user.id if message.from_user else None):
            await message.answer(MOD_MENU_TEXT.NOT_ALLOWED)
            return
        await state.clear()
        await message.answer(await render_mod_home(container), reply_markup=build_mod_home_keyboard())

    @router.callback_query(F.data == MOD_HOME_ACTION)
    async def handle_mod_home(callback: CallbackQuery, state: FSMContext) -> None:
        message = _message(callback)
        if message is None or not is_moderator(callback.from_user.id if callback.from_user else None):
            await callback.answer(MOD_MENU_TEXT.NOT_ALLOWED)
            return
        await state.set_state(None)
        await message.answer(await render_mod_home(container), reply_markup=build_mod_home_keyboard())
        await callback.answer(MOD_MENU_TEXT.CALLBACK_OPENED)

    @router.callback_query(F.data == MOD_DISPUTES_ACTION)
    async def handle_mod_disputes(callback: CallbackQuery) -> None:
        message = _message(callback)
        if message is None or not is_moderator(callback.from_user.id if callback.from_user else None):
            await callback.answer(MOD_MENU_TEXT.NOT_ALLOWED)
            return

        deals = await container.deal_service.list_disputed_deals()
        if not deals:
            await message.answer(
                f"{MOD_MENU_TEXT.DISPUTES_TITLE}\n{MOD_MENU_TEXT.DISPUTES_EMPTY}",
                reply_markup=build_mod_home_keyboard(),
            )
            await callback.answer()
            return

        await message.answer(
            MOD_MENU_TEXT.DISPUTES_TITLE,
            reply_markup=build_mod_disputes_keyboard([deal.deal_id for deal in deals]),
        )
        await callback.answer()

    @router.callback_query(F.data.startswith(MOD_DEAL_PREFIX))
    async def handle_mod_deal(callback: CallbackQuery) -> None:
        message = _message(callback)
        if message is None or not is_moderator(callback.from_user.id if callback.from_user else None):
            await callback.answer(MOD_MENU_TEXT.NOT_ALLOWED)
            return

        raw = (callback.data or "").removeprefix(MOD_DEAL_PREFIX)
        deal_id = int(raw) if raw.isdigit() else 0
        deal = await container.deal_service.get_deal_view_admin(deal_id)
        if deal is None:
            await callback.answer(MOD_MENU_TEXT.DISPUTES_EMPTY)
            return

        from cerber_bot.handlers.menu import render_deal_view

        await message.answer(render_deal_view(deal), reply_markup=build_moderator_deal_keyboard(deal.deal_id))
        await callback.answer()

    @router.callback_query(F.data == MOD_WITHDRAWALS_ACTION)
    async def handle_mod_withdrawals(callback: CallbackQuery) -> None:
        message = _message(callback)
        if message is None or not is_moderator(callback.from_user.id if callback.from_user else None):
            await callback.answer(MOD_MENU_TEXT.NOT_ALLOWED)
            return

        requests = await container.deal_service.list_pending_withdrawals()
        if not requests:
            await message.answer(
                f"{MOD_MENU_TEXT.WITHDRAWALS_TITLE}\n{MOD_MENU_TEXT.WITHDRAWALS_EMPTY}",
                reply_markup=build_mod_home_keyboard(),
            )
            await callback.answer()
            return

        for request in requests[:10]:
            row = MOD_MENU_TEXT.WITHDRAWAL_ROW.format(
                request_id=request.request_id,
                amount=escape(format_money(request.amount_usdt, "USDT")),
                network=escape(request.network),
                telegram_id=request.telegram_id,
            )
            await message.answer(
                f"{MOD_MENU_TEXT.WITHDRAWALS_TITLE}\n{row}\n{escape(request.address)}",
                reply_markup=build_moderator_withdrawal_keyboard(request.request_id),
            )
        await callback.answer()

    @router.callback_query(F.data == MOD_STATS_ACTION)
    async def handle_mod_stats(callback: CallbackQuery) -> None:
        message = _message(callback)
        if message is None or not is_moderator(callback.from_user.id if callback.from_user else None):
            await callback.answer(MOD_MENU_TEXT.NOT_ALLOWED)
            return

        stats = await container.user_service.get_stats()
        await message.answer(
            "\n".join(
                [
                    MOD_MENU_TEXT.STATS_TITLE,
                    MOD_MENU_TEXT.STATS_ROW.format(
                        total=stats.total,
                        active_7d=stats.active_7d,
                        active_24h=stats.active_24h,
                    ),
                ]
            ),
            reply_markup=build_mod_home_keyboard(),
        )
        await callback.answer()

    return router


async def render_mod_home(container: AppContainer) -> str:
    disputes, withdrawals = await container.deal_service.get_admin_summary()
    group_chat_id = await container.admin_group_service.get_group_chat_id()
    lines = [
        MOD_MENU_TEXT.TITLE,
        MOD_MENU_TEXT.SUMMARY.format(disputes=disputes, withdrawals=withdrawals),
        "",
    ]
    if group_chat_id is not None:
        lines.append(MOD_MENU_TEXT.GROUP_CONNECTED.format(chat_id=group_chat_id))
    else:
        lines.append(MOD_MENU_TEXT.GROUP_NOT_CONNECTED)
    return "\n".join(lines)


def _message(callback: CallbackQuery) -> Message | None:
    if isinstance(callback.message, Message):
        return callback.message
    return None
