"""Логика покер-дуэли для CEER Bot.

Простая дуэль: игрок и бот тянут по одной карте случайно.
Старшая карта забирает ставку. При ничьей — ставка возвращается.
Все денежные операции через CeerUserService (CERBER БД).
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum


DECK: list[str] = [
    "2", "3", "4", "5", "6", "7", "8", "9", "10",
    "J", "Q", "K", "A",
]

CARD_VALUE: dict[str, int] = {c: i for i, c in enumerate(DECK)}

SUITS = ["♠", "♥", "♦", "♣"]


class PokerResult(str, Enum):
    WIN = "win"
    LOSE = "lose"
    DRAW = "draw"


@dataclass(slots=True, frozen=True)
class DuelOutcome:
    result: PokerResult
    player_card: str
    bot_card: str


def draw_card() -> str:
    """Тянет случайную карту (масть + номинал)."""
    suit = random.choice(SUITS)
    rank = random.choice(DECK)
    return f"{rank}{suit}"


def _rank(card: str) -> int:
    """Возвращает числовой вес карты по номиналу (масть игнорируется)."""
    for rank in reversed(DECK):
        if card.startswith(rank):
            return CARD_VALUE[rank]
    return 0


def play_duel() -> DuelOutcome:
    """Разыгрывает одну дуэль, возвращает результат."""
    player_card = draw_card()
    bot_card = draw_card()

    pv = _rank(player_card)
    bv = _rank(bot_card)

    if pv > bv:
        result = PokerResult.WIN
    elif pv < bv:
        result = PokerResult.LOSE
    else:
        result = PokerResult.DRAW

    return DuelOutcome(result=result, player_card=player_card, bot_card=bot_card)
