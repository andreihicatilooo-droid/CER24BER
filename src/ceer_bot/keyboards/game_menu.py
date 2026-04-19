"""Клавиатура выбора игры, доска крестиков-ноликов, блэкджека и дурака."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

GAME_POKER_ACTION = "game:poker"
GAME_MENU_ACTION  = "game:menu"
GAME_TTT_ACTION   = "game:ttt"
GAME_BJ_ACTION    = "game:bj"
GAME_DURAK_ACTION = "game:durak"


def build_game_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="♠️ Покер-дуэль",      callback_data=GAME_POKER_ACTION)],
        [InlineKeyboardButton(text="❌⭕ Крестики-нолики", callback_data=GAME_TTT_ACTION)],
        [InlineKeyboardButton(text="🃏 Блэкджек",          callback_data=GAME_BJ_ACTION)],
        [InlineKeyboardButton(text="🂠 Дурак",              callback_data=GAME_DURAK_ACTION)],
    ])


def build_cancel_game() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="game:cancel")],
    ])


# ─── TTT ──────────────────────────────────────────────────────────────────────

def build_ttt_invite(game_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Принять вызов", callback_data=f"ttt:accept:{game_id}")],
        [InlineKeyboardButton(text="❌ Отменить",      callback_data=f"ttt:decline:{game_id}")],
    ])


def build_ttt_board(board: list[str], game_id: str, finished: bool) -> InlineKeyboardMarkup:
    from ceer_bot.games.tictactoe import EMPTY
    buttons: list[list[InlineKeyboardButton]] = []
    for row in range(3):
        row_btns: list[InlineKeyboardButton] = []
        for col in range(3):
            idx = row * 3 + col
            cell = board[idx]
            cb = "ttt:noop" if (finished or cell != EMPTY) else f"ttt:move:{game_id}:{idx}"
            row_btns.append(InlineKeyboardButton(text=cell, callback_data=cb))
        buttons.append(row_btns)
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ─── Blackjack ────────────────────────────────────────────────────────────────

def build_bj_invite(game_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Принять вызов", callback_data=f"bj:accept:{game_id}")],
        [InlineKeyboardButton(text="❌ Отменить",      callback_data=f"bj:decline:{game_id}")],
    ])


def build_bj_board(game_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🃏 Ещё карту", callback_data=f"bj:hit:{game_id}"),
            InlineKeyboardButton(text="✋ Хватит",    callback_data=f"bj:stand:{game_id}"),
        ],
    ])


# ─── Durak ────────────────────────────────────────────────────────────────────

def build_durak_invite(
    game_id: str,
    player_names: list[str],
    max_players: int = 3,
) -> InlineKeyboardMarkup:
    btns: list[list[InlineKeyboardButton]] = []
    if len(player_names) < max_players:
        btns.append([InlineKeyboardButton(text="➕ Присоединиться", callback_data=f"durak:join:{game_id}")])
    btns.append([InlineKeyboardButton(text="▶ Начать игру", callback_data=f"durak:start:{game_id}")])
    btns.append([InlineKeyboardButton(text="❌ Отменить",   callback_data=f"durak:cancel:{game_id}")])
    return InlineKeyboardMarkup(inline_keyboard=btns)


def build_durak_board(
    game_id: str,
    phase: str,
    table_non_empty: bool,
) -> InlineKeyboardMarkup:
    """Клавиатура игровой доски: просмотр карт + ситуационные кнопки."""
    btns: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text="👁 Посмотреть карты", callback_data=f"durak:hand:{game_id}")],
    ]
    if phase == "attacking" and table_non_empty:
        btns.append([InlineKeyboardButton(text="✅ Закончить атаку", callback_data=f"durak:pass:{game_id}")])
    elif phase == "defending":
        btns.append([InlineKeyboardButton(text="🤚 Взять карты", callback_data=f"durak:take:{game_id}")])
    return InlineKeyboardMarkup(inline_keyboard=btns)


def build_cancel_game() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="game:cancel")],
    ])


# ─── TTT ──────────────────────────────────────────────────────────────────────

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


# ─── Blackjack ────────────────────────────────────────────────────────────────

def build_bj_invite(game_id: str) -> InlineKeyboardMarkup:
    """Клавиатура приглашения в блэкджек."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Принять вызов", callback_data=f"bj:accept:{game_id}")],
        [InlineKeyboardButton(text="❌ Отменить",      callback_data=f"bj:decline:{game_id}")],
    ])


def build_bj_board(game_id: str) -> InlineKeyboardMarkup:
    """Кнопки действий во время игры в блэкджек."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🃏 Ещё карту", callback_data=f"bj:hit:{game_id}"),
            InlineKeyboardButton(text="✋ Хватит",    callback_data=f"bj:stand:{game_id}"),
        ],
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
