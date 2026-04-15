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

# Чат модератора в диспуте
ADMIN_DEAL_CHAT_PREFIX = "adm:chat:"                   # adm:chat:123
ADMIN_DEAL_REFRESH_PREFIX = "adm:dealrefresh:"         # adm:dealrefresh:123

# Управление балансом пользователей
ADMIN_USERS_ACTION = "adm:users"
ADMIN_USER_BAL_PREFIX = "adm:ubal:"                    # adm:ubal:123456789

# Статус системы
ADMIN_STATUS_ACTION = "adm:status"
ADMIN_LOGS_BOT_ACTION = "adm:logs:bot"
ADMIN_LOGS_ERR_ACTION = "adm:logs:err"
ADMIN_LOGS_TUNNEL_ACTION = "adm:logs:tunnel"
ADMIN_CHECK_SERVICES_ACTION = "adm:svccheck"

# Статистика пользователей
ADMIN_STATS_ACTION = "adm:stats"


def build_admin_home_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=ADMIN_TEXT.BTN_DISPUTES, callback_data=ADMIN_DISPUTES_ACTION),
            InlineKeyboardButton(text=ADMIN_TEXT.BTN_WITHDRAWALS, callback_data=ADMIN_WITHDRAWALS_ACTION),
        ],
        [
            InlineKeyboardButton(text=ADMIN_TEXT.BTN_USERS, callback_data=ADMIN_USERS_ACTION),
            InlineKeyboardButton(text=ADMIN_TEXT.BTN_STATS, callback_data=ADMIN_STATS_ACTION),
        ],
        [
            InlineKeyboardButton(text=ADMIN_TEXT.BTN_STATUS, callback_data=ADMIN_STATUS_ACTION),
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
            InlineKeyboardButton(text=ADMIN_TEXT.BTN_WRITE_TO_CHAT, callback_data=f"{ADMIN_DEAL_CHAT_PREFIX}{deal_id}"),
            InlineKeyboardButton(text=ADMIN_TEXT.BTN_REFRESH_DEAL, callback_data=f"{ADMIN_DEAL_REFRESH_PREFIX}{deal_id}"),
        ],
        [
            InlineKeyboardButton(text=ADMIN_TEXT.BTN_BACK_TO_LIST, callback_data=ADMIN_DISPUTES_ACTION),
            InlineKeyboardButton(text=ADMIN_TEXT.BTN_HOME, callback_data=ADMIN_HOME_ACTION),
        ],
    ])


def build_admin_deal_readonly_keyboard(deal_id: int) -> InlineKeyboardMarkup:
    """Для не-диспутных сделок: только просмотр и обновление."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=ADMIN_TEXT.BTN_REFRESH_DEAL, callback_data=f"{ADMIN_DEAL_REFRESH_PREFIX}{deal_id}"),
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


def build_user_profile_keyboard(telegram_id: int) -> InlineKeyboardMarkup:
    """Клавиатура просмотра профиля пользователя с кнопками корректировки баланса."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=ADMIN_TEXT.BTN_BALANCE_ADD, callback_data=f"{ADMIN_USER_BAL_PREFIX}{telegram_id}:add"),
            InlineKeyboardButton(text=ADMIN_TEXT.BTN_BALANCE_SUB, callback_data=f"{ADMIN_USER_BAL_PREFIX}{telegram_id}:sub"),
        ],
        [InlineKeyboardButton(text=ADMIN_TEXT.BTN_HOME, callback_data=ADMIN_HOME_ACTION)],
    ])


def build_status_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура панели статуса с кнопками просмотра логов."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=ADMIN_TEXT.BTN_LOG_BOT, callback_data=ADMIN_LOGS_BOT_ACTION),
            InlineKeyboardButton(text=ADMIN_TEXT.BTN_LOG_ERR, callback_data=ADMIN_LOGS_ERR_ACTION),
            InlineKeyboardButton(text=ADMIN_TEXT.BTN_LOG_TUNNEL, callback_data=ADMIN_LOGS_TUNNEL_ACTION),
        ],
        [
            InlineKeyboardButton(text=ADMIN_TEXT.BTN_CHECK_SERVICES, callback_data=ADMIN_CHECK_SERVICES_ACTION),
            InlineKeyboardButton(text=ADMIN_TEXT.BTN_HOME, callback_data=ADMIN_HOME_ACTION),
        ],
    ])
