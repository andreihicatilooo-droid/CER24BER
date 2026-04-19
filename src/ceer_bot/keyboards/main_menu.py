"""Главное меню CEER Bot (личные сообщения)."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from ceer_bot.texts import MAIN_MENU_TEXT

CEER_PROFILE_ACTION = "ceer:profile"
CEER_BALANCE_ACTION = "ceer:balance"
CEER_RULES_ACTION   = "ceer:rules"
CEER_HOME_ACTION    = "ceer:home"

# URL-шаблон для добавления бота в чат с запросом прав администратора
_ADMIN_RIGHTS = "delete_messages+restrict_members+pin_messages+manage_chat"
_ADD_TO_CHAT_URL = "https://t.me/{username}?startgroup=start&admin=" + _ADMIN_RIGHTS


def build_main_menu(support_url: str = "", bot_username: str = "") -> InlineKeyboardMarkup:
    keyboard: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(text=MAIN_MENU_TEXT.PROFILE, callback_data=CEER_PROFILE_ACTION),
            InlineKeyboardButton(text=MAIN_MENU_TEXT.BALANCE, callback_data=CEER_BALANCE_ACTION),
        ],
        [
            InlineKeyboardButton(text=MAIN_MENU_TEXT.RULES, callback_data=CEER_RULES_ACTION),
        ],
    ]
    if bot_username:
        keyboard.append([
            InlineKeyboardButton(
                text=MAIN_MENU_TEXT.ADD_TO_CHAT,
                url=_ADD_TO_CHAT_URL.format(username=bot_username),
            ),
        ])
    if support_url:
        keyboard.append([
            InlineKeyboardButton(text=MAIN_MENU_TEXT.SUPPORT, url=support_url),
        ])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def build_back_to_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data=CEER_HOME_ACTION)],
    ])
