"""Логика игры «Крестики-нолики» для CEER Bot.

Хранит состояние в памяти (_registry). При перезапуске бота активные
игры сбрасываются — это приемлемо для легковесного игрового бота.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from decimal import Decimal

EMPTY = "·"
X = "✕"
O = "◯"

WINNING_COMBOS: list[tuple[int, int, int]] = [
    (0, 1, 2), (3, 4, 5), (6, 7, 8),  # строки
    (0, 3, 6), (1, 4, 7), (2, 5, 8),  # столбцы
    (0, 4, 8), (2, 4, 6),             # диагонали
]


@dataclass(slots=True)
class TicTacToeGame:
    game_id: str
    chat_id: int
    message_id: int          # сообщение с доской (для edit)
    player_x_id: int
    player_x_name: str
    bet: Decimal
    player_o_id: int | None = None
    player_o_name: str | None = None
    board: list[str] = field(default_factory=lambda: [EMPTY] * 9)
    current_turn_id: int | None = None
    finished: bool = False
    winner_id: int | None = None   # None = ничья, если finished=True


# Реестр активных игр: game_id → TicTacToeGame
_registry: dict[str, TicTacToeGame] = {}


def create_game(
    chat_id: int,
    message_id: int,
    player_x_id: int,
    player_x_name: str,
    bet: Decimal,
) -> TicTacToeGame:
    game = TicTacToeGame(
        game_id=str(uuid.uuid4()),
        chat_id=chat_id,
        message_id=message_id,
        player_x_id=player_x_id,
        player_x_name=player_x_name,
        bet=bet,
    )
    _registry[game.game_id] = game
    return game


def get_game(game_id: str) -> TicTacToeGame | None:
    return _registry.get(game_id)


def accept_game(game: TicTacToeGame, player_o_id: int, player_o_name: str) -> None:
    game.player_o_id = player_o_id
    game.player_o_name = player_o_name
    game.current_turn_id = game.player_x_id


def make_move(game: TicTacToeGame, cell: int, player_id: int) -> bool:
    """Делает ход. Возвращает True при успехе."""
    if game.finished or game.player_o_id is None:
        return False
    if game.current_turn_id != player_id:
        return False
    if game.board[cell] != EMPTY:
        return False
    symbol = X if player_id == game.player_x_id else O
    game.board[cell] = symbol
    return True


def check_winner(board: list[str]) -> str | None:
    """Возвращает 'X', 'O' или None если победителя нет."""
    for a, b, c in WINNING_COMBOS:
        if board[a] != EMPTY and board[a] == board[b] == board[c]:
            return board[a]
    return None


def is_draw(board: list[str]) -> bool:
    return EMPTY not in board


def finish_game(game: TicTacToeGame, winner_symbol: str | None) -> None:
    """Фиксирует конец игры."""
    game.finished = True
    if winner_symbol is None:
        game.winner_id = None
    elif winner_symbol == X:
        game.winner_id = game.player_x_id
    else:
        game.winner_id = game.player_o_id
    _registry.pop(game.game_id, None)


def next_turn(game: TicTacToeGame) -> None:
    """Передаёт ход другому игроку."""
    if game.current_turn_id == game.player_x_id:
        game.current_turn_id = game.player_o_id
    else:
        game.current_turn_id = game.player_x_id
