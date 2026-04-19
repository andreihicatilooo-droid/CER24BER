"""Клавиатура выбора игры и доска крестиков-ноликов."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

GAME_POKER_ACTION = "game:poker"
GAME_MENU_ACTION  = "game:menu"
GAME_TTT_ACTION   = "game:ttt"


def build_game_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="♠️ Покер-дуэль",      callback_data=GAME_POKER_ACTION)],
        [InlineKeyboardButton(text="❌⭕ Крестики-нолики", callback_data=GAME_TTT_ACTION)],
    ])


def build_cancel_game() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="game:cancel")],
    ])


def build_ttt_invite(game_id: str) -> InlineKeyboardMarkup:
    """Клавиатура для сообщения-приглашения (до принятия вызова)."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="✅ Принять вызов",
            callback_data=f"ttt:accept:{game_id}",
        )],
        [InlineKeyboardButton(text="❌ Отменить", callback_data=f"ttt:decline:{game_id}")],
    ])


def build_ttt_board(board: list[str], game_id: str, finished: bool) -> InlineKeyboardMarkup:
    """Inline-клавиатура 3×3 с текущим состоянием доски."""
    from ceer_bot.games.tictactoe import EMPTY  # локальный импорт во избежание цикла
    buttons: list[list[InlineKeyboardButton]] = []
    for row in range(3):
        row_btns: list[InlineKeyboardButton] = []
        for col in range(3):
            idx = row * 3 + col
            cell = board[idx]
            if finished or cell != EMPTY:
                cb = "ttt:noop"
            else:
                cb = f"ttt:move:{game_id}:{idx}"
            row_btns.append(InlineKeyboardButton(text=cell, callback_data=cb))
        buttons.append(row_btns)
    return InlineKeyboardMarkup(inline_keyboard=buttons)
