"""Логика карточной игры «Блэкджек» для двоих (CEER Bot).

Оба игрока видят карты друг друга — карты открытые (group-chat игра).
Состояние хранится в памяти. При перезапуске бота активные игры сбрасываются.

Правила:
  - Стандартная колода 52 карты, перетасована при создании игры.
  - Карты 2–10 = номинал, J/Q/K = 10, A = 11 (уменьшается до 1 при перебое).
  - Игрок 1 ходит первым: может брать карты (Hit) или остановиться (Stand).
  - После остановки или перебора ходит Игрок 2.
  - По окончании: ближе к 21 побеждает. Равенство = ничья.
"""

from __future__ import annotations

import random
import uuid
from dataclasses import dataclass, field
from decimal import Decimal

SUITS  = ["♠", "♥", "♦", "♣"]
VALUES = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]

_registry: dict[str, "BlackjackGame"] = {}


def _new_deck() -> list[str]:
    deck = [f"{v}{s}" for s in SUITS for v in VALUES]
    random.shuffle(deck)
    return deck


def card_value(card: str) -> int:
    """Числовое значение карты (без учёта Ace-reduction)."""
    v = card[:-1]            # убираем масть (один unicode-символ)
    if v in ("J", "Q", "K"):
        return 10
    if v == "A":
        return 11
    return int(v)


def hand_score(hand: list[str]) -> int:
    """Сумма очков руки с автоматическим уменьшением тузов при перебое."""
    total = sum(card_value(c) for c in hand)
    aces  = sum(1 for c in hand if c[:-1] == "A")
    while total > 21 and aces:
        total -= 10
        aces  -= 1
    return total


def hand_display(hand: list[str]) -> str:
    return "  ".join(hand)


@dataclass(slots=True)
class BlackjackGame:
    game_id:      str
    chat_id:      int
    message_id:   int
    player1_id:   int
    player1_name: str
    bet:          Decimal
    deck:         list[str] = field(default_factory=_new_deck)
    hand1:        list[str] = field(default_factory=list)
    hand2:        list[str] = field(default_factory=list)
    player2_id:   int | None  = None
    player2_name: str | None  = None
    # 1 = ходит игрок 1, 2 = ходит игрок 2
    active_player: int  = 1
    stood1:        bool = False
    stood2:        bool = False
    finished:      bool = False
    winner_id:     int | None = None  # None = ничья, если finished=True


def create_game(
    chat_id:      int,
    message_id:   int,
    player1_id:   int,
    player1_name: str,
    bet:          Decimal,
) -> BlackjackGame:
    game = BlackjackGame(
        game_id=str(uuid.uuid4()),
        chat_id=chat_id,
        message_id=message_id,
        player1_id=player1_id,
        player1_name=player1_name,
        bet=bet,
    )
    _registry[game.game_id] = game
    return game


def get_game(game_id: str) -> BlackjackGame | None:
    return _registry.get(game_id)


def accept_game(game: BlackjackGame, player2_id: int, player2_name: str) -> None:
    """Второй игрок принимает вызов, карты раздаются."""
    game.player2_id   = player2_id
    game.player2_name = player2_name
    # Раздаём по 2 карты
    game.hand1 = [game.deck.pop(), game.deck.pop()]
    game.hand2 = [game.deck.pop(), game.deck.pop()]
    game.active_player = 1


def hit(game: BlackjackGame) -> str:
    """Берёт карту для текущего игрока, возвращает новую карту."""
    card = game.deck.pop()
    if game.active_player == 1:
        game.hand1.append(card)
    else:
        game.hand2.append(card)
    return card


def active_score(game: BlackjackGame) -> int:
    return hand_score(game.hand1 if game.active_player == 1 else game.hand2)


def stand(game: BlackjackGame) -> bool:
    """Текущий игрок останавливается. Возвращает True если игра завершена."""
    if game.active_player == 1:
        game.stood1 = True
        game.active_player = 2
    else:
        game.stood2 = True
    return game.stood1 and game.stood2


def resolve_winner(game: BlackjackGame) -> int | None:
    """Определяет победителя по очкам. None = ничья."""
    s1 = hand_score(game.hand1)
    s2 = hand_score(game.hand2)
    if s1 > 21 and s2 > 21:
        return None
    if s1 > 21:
        return game.player2_id
    if s2 > 21:
        return game.player1_id
    if s1 > s2:
        return game.player1_id
    if s2 > s1:
        return game.player2_id
    return None


def finish_game(game: BlackjackGame, winner_id: int | None) -> None:
    game.finished  = True
    game.winner_id = winner_id
    _registry.pop(game.game_id, None)
