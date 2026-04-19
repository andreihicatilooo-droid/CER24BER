"""Клавиатура выбора игры в чате."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

GAME_POKER_ACTION = "game:poker"
GAME_MENU_ACTION = "game:menu"


def build_game_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="♠️ Покер-дуэль", callback_data=GAME_POKER_ACTION)],
    ])


def build_cancel_game() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="game:cancel")],
    ])
