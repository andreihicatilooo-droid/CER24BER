"""Клавиатуры для административного бота."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from cerber_bot.texts import ADMIN_TEXT

# ── callback-data префиксы ──────────────────────────────────────
ADMIN_HOME_ACTION = "adm:home"
ADMIN_DISPUTES_ACTION = "adm:disputes"
ADMIN_WITHDRAWALS_ACTION = "adm:withdrawals"
ADMIN_DEAL_PREFIX = "adm:deal:"                        # adm:deal:123
ADMIN_MODERATE_PREFIX = "adm:moderate:"                # adm:moderate:123:release / :refund
ADMIN_WITHDRAW_PREFIX = "adm:withdraw:"                # adm:withdraw:456:approve / :reject


def build_admin_home_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=ADMIN_TEXT.BTN_DISPUTES, callback_data=ADMIN_DISPUTES_ACTION),
            InlineKeyboardButton(text=ADMIN_TEXT.BTN_WITHDRAWALS, callback_data=ADMIN_WITHDRAWALS_ACTION),
        ],
    ])


def build_disputes_list_keyboard(deal_ids: list[int]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for deal_id in deal_ids:
        rows.append([
            InlineKeyboardButton(
                text=f"#{deal_id} — {ADMIN_TEXT.BTN_OPEN_DEAL}",
                callback_data=f"{ADMIN_DEAL_PREFIX}{deal_id}",
            ),
        ])
    rows.append([InlineKeyboardButton(text=ADMIN_TEXT.BTN_HOME, callback_data=ADMIN_HOME_ACTION)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_admin_deal_keyboard(deal_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=ADMIN_TEXT.BTN_RELEASE, callback_data=f"{ADMIN_MODERATE_PREFIX}{deal_id}:release"),
            InlineKeyboardButton(text=ADMIN_TEXT.BTN_REFUND, callback_data=f"{ADMIN_MODERATE_PREFIX}{deal_id}:refund"),
        ],
        [
            InlineKeyboardButton(text=ADMIN_TEXT.BTN_BACK_TO_LIST, callback_data=ADMIN_DISPUTES_ACTION),
            InlineKeyboardButton(text=ADMIN_TEXT.BTN_HOME, callback_data=ADMIN_HOME_ACTION),
        ],
    ])


def build_withdrawals_list_keyboard(request_ids: list[int]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for request_id in request_ids:
        rows.append([
            InlineKeyboardButton(
                text=f"#{request_id} — {ADMIN_TEXT.BTN_APPROVE_WITHDRAWAL}",
                callback_data=f"{ADMIN_WITHDRAW_PREFIX}{request_id}:approve",
            ),
            InlineKeyboardButton(
                text=ADMIN_TEXT.BTN_REJECT_WITHDRAWAL,
                callback_data=f"{ADMIN_WITHDRAW_PREFIX}{request_id}:reject",
            ),
        ])
    rows.append([InlineKeyboardButton(text=ADMIN_TEXT.BTN_HOME, callback_data=ADMIN_HOME_ACTION)])
    return InlineKeyboardMarkup(inline_keyboard=rows)
