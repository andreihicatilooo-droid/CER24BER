"""Логика карточной игры «Дурак» для 2–3 игроков (CEER Bot).

Правила (упрощённые для чат-игры):
  - Колода 36 карт (6–Туз × 4 масти).
  - Козырь = масть нижней карты колоды.
  - Атакует владелец наименьшего козыря (если нет козырей — первый по порядку).
  - Карты открытые (все видят руки всех игроков).
  - За одну атаку кладётся ОДНА карта; после защиты атакующий может добавить
    ещё карту с совпадающим значением или закончить атаку.
  - После удачной защиты: защитник становится атакующим.
  - После взятия: атакует следующий за защитником по кругу.
  - Игроки добирают карты до 6 после каждого раунда.
  - Игра заканчивается когда остаётся один игрок с картами — это Дурак.
"""

from __future__ import annotations

import random
import uuid
from dataclasses import dataclass, field
from decimal import Decimal

SUITS_KEYS = ("s", "h", "d", "c")
SUITS = {"s": "♠", "h": "♥", "d": "♦", "c": "♣"}
VALUES = ("6", "7", "8", "9", "10", "J", "Q", "K", "A")
VALUE_RANK = {v: i for i, v in enumerate(VALUES)}

HAND_SIZE = 6
MAX_PLAYERS = 3

_registry: dict[str, "DurakGame"] = {}
_chat_games: dict[int, str] = {}   # chat_id → game_id (одна игра на чат)

# Карточный ввод: русские обозначения → внутренние ключи
_SUIT_MAP: dict[str, str] = {
    "п": "s", "ч": "h", "б": "d", "к": "c", "т": "c",
    "♠": "s", "♥": "h", "♦": "d", "♣": "c",
    "s": "s", "h": "h", "d": "d", "c": "c",
}
_VALUE_MAP: dict[str, str] = {
    "6": "6", "7": "7", "8": "8", "9": "9", "10": "10",
    "в": "J", "j": "J",
    "д": "Q", "q": "Q",
    "к": "K", "k": "K",
    "т": "A", "a": "A", "а": "A",
}


# ─── Вспомогательные функции ──────────────────────────────────────────────────

def _new_deck() -> list[str]:
    deck = [f"{v}{s}" for s in SUITS_KEYS for v in VALUES]
    random.shuffle(deck)
    return deck


def card_display(card: str) -> str:
    """Красивое отображение карты: «J♠»."""
    return f"{card[:-1]}{SUITS.get(card[-1], '?')}"


def hand_display(hand: list[str], trump: str) -> str:
    """Рука игрока: козыри помечены [скобками]."""
    if not hand:
        return "—"
    parts = []
    for c in hand:
        d = card_display(c)
        parts.append(f"[{d}]" if c[-1] == trump else d)
    return "  ".join(parts)


def can_beat(atk: str, dfn: str, trump: str) -> bool:
    av, as_ = atk[:-1], atk[-1]
    dv, ds_ = dfn[:-1], dfn[-1]
    if as_ == ds_:
        return VALUE_RANK[dv] > VALUE_RANK[av]
    return ds_ == trump and as_ != trump


def table_values(table: list[tuple[str, str | None]]) -> set[str]:
    vals: set[str] = set()
    for atk, dfn in table:
        vals.add(atk[:-1])
        if dfn:
            vals.add(dfn[:-1])
    return vals


def can_add_to_table(card: str, table: list[tuple[str, str | None]]) -> bool:
    if not table:
        return False
    return card[:-1] in table_values(table)


# ─── Модель игры ──────────────────────────────────────────────────────────────

@dataclass(slots=True)
class DurakGame:
    game_id:     str
    chat_id:     int
    message_id:  int
    creator_id:  int
    bet:         Decimal

    player_ids:   list[int]           = field(default_factory=list)
    player_names: dict[int, str]      = field(default_factory=dict)

    deck:    list[str]                        = field(default_factory=list)
    trump:   str                              = ""   # ключ масти: s/h/d/c
    hands:   dict[int, list[str]]             = field(default_factory=dict)
    table:   list[tuple[str, str | None]]     = field(default_factory=list)
    discard: list[str]                        = field(default_factory=list)

    attacker_idx: int  = 0
    defender_idx: int  = 1

    # joining / attacking / defending / finished
    phase:        str  = "joining"

    finished: bool      = False
    loser_id: int | None = None
    winners:  list[int]  = field(default_factory=list)


# ─── CRUD реестра ─────────────────────────────────────────────────────────────

def create_game(
    chat_id: int, message_id: int,
    creator_id: int, creator_name: str, bet: Decimal,
) -> DurakGame:
    g = DurakGame(
        game_id=str(uuid.uuid4()),
        chat_id=chat_id,
        message_id=message_id,
        creator_id=creator_id,
        bet=bet,
    )
    g.player_ids.append(creator_id)
    g.player_names[creator_id] = creator_name
    _registry[g.game_id] = g
    _chat_games[chat_id] = g.game_id
    return g


def get_game(game_id: str) -> DurakGame | None:
    return _registry.get(game_id)


def find_active_game_in_chat(chat_id: int) -> "DurakGame | None":
    """Возвращает активную игру в чате (не в фазе 'joining' и не завершённую)."""
    gid = _chat_games.get(chat_id)
    if gid:
        return _registry.get(gid)
    return None


def parse_card(text: str) -> str | None:
    """Парсит строку в код карты (напр. «6п» → «6s», «Кч» → «Kh»).

    Формат: значение + масть (последний символ).
    Масти: п=♠, ч=♥, б=♦, к=♣, т=♣
    Значения: 6-10, В/J=валет, Д/Q=дама, К/K=король, Т/A/А=туз
    """
    text = text.strip().lower()
    if len(text) < 2:
        return None
    suit_key = _SUIT_MAP.get(text[-1])
    if suit_key is None:
        return None
    val_raw = text[:-1]
    val = _VALUE_MAP.get(val_raw)
    if val is None:
        return None
    return f"{val}{suit_key}"


def add_player(game: DurakGame, pid: int, name: str) -> bool:
    if len(game.player_ids) >= MAX_PLAYERS or pid in game.player_ids:
        return False
    game.player_ids.append(pid)
    game.player_names[pid] = name
    return True


# ─── Старт игры ──────────────────────────────────────────────────────────────

def start_game(game: DurakGame) -> None:
    """Раздаёт карты, определяет козырь и первого атакующего."""
    deck = _new_deck()
    for pid in game.player_ids:
        game.hands[pid] = [deck.pop() for _ in range(HAND_SIZE)]
    game.trump = deck[-1][-1]   # масть нижней карты
    game.deck = deck

    # Атакует владелец наименьшего козыря
    best_rank = 999
    best_idx  = 0
    for i, pid in enumerate(game.player_ids):
        for c in game.hands[pid]:
            if c[-1] == game.trump:
                r = VALUE_RANK[c[:-1]]
                if r < best_rank:
                    best_rank = r
                    best_idx  = i
    game.attacker_idx = best_idx
    game.defender_idx = (best_idx + 1) % len(game.player_ids)
    game.phase = "attacking"


# ─── Внутренние утилиты ───────────────────────────────────────────────────────

def _active(game: DurakGame) -> list[int]:
    return [pid for pid in game.player_ids if pid not in game.winners]


def _draw_cards(game: DurakGame, skip_pid: int | None = None) -> None:
    """Добирают карты до HAND_SIZE; атакующий первый, защитник последний."""
    n = len(game.player_ids)
    order: list[int] = []
    idx = game.attacker_idx
    for _ in range(n):
        pid = game.player_ids[idx]
        if idx != game.defender_idx:
            order.append(pid)
        idx = (idx + 1) % n
    order.append(game.player_ids[game.defender_idx])

    for pid in order:
        if pid in game.winners or pid == skip_pid:
            continue
        while len(game.hands[pid]) < HAND_SIZE and game.deck:
            game.hands[pid].append(game.deck.pop())


def _exit_winners(game: DurakGame) -> None:
    """Игроки без карт (при пустой колоде) выходят победителями."""
    for pid in game.player_ids:
        if pid not in game.winners and not game.hands.get(pid) and not game.deck:
            game.winners.append(pid)


def _next_after(game: DurakGame, start_idx: int) -> int:
    """Следующий активный игрок после start_idx."""
    n = len(game.player_ids)
    idx = start_idx
    for _ in range(n):
        idx = (idx + 1) % n
        if game.player_ids[idx] not in game.winners:
            return idx
    return start_idx


def _advance_after_defense(game: DurakGame) -> None:
    """Защитник становится атакующим."""
    def_id = game.player_ids[game.defender_idx]
    if def_id in game.winners:
        active = _active(game)
        def_id = active[0] if active else game.player_ids[0]
    new_att = game.player_ids.index(def_id)
    game.attacker_idx = new_att
    game.defender_idx = _next_after(game, new_att)


def _advance_after_take(game: DurakGame) -> None:
    """После взятия: атакует следующий за защитником."""
    new_att = _next_after(game, game.defender_idx)
    game.attacker_idx = new_att
    game.defender_idx = _next_after(game, new_att)


# ─── Игровые действия ────────────────────────────────────────────────────────

def do_attack(game: DurakGame, card: str) -> bool:
    if game.phase != "attacking":
        return False
    pid = game.player_ids[game.attacker_idx]
    if card not in game.hands[pid]:
        return False
    if game.table and not can_add_to_table(card, game.table):
        return False
    game.hands[pid].remove(card)
    game.table.append((card, None))
    game.phase = "defending"
    return True


def do_defend(game: DurakGame, card: str) -> bool:
    if game.phase != "defending":
        return False
    pid = game.player_ids[game.defender_idx]
    if card not in game.hands[pid]:
        return False
    for i, (atk, dfn) in enumerate(game.table):
        if dfn is None:
            if not can_beat(atk, card, game.trump):
                return False
            game.hands[pid].remove(card)
            game.table[i] = (atk, card)
            # Если все карты побиты — атакующий может добавить ещё или пасовать
            if all(d is not None for _, d in game.table):
                game.phase = "attacking"
            return True
    return False


def do_take(game: DurakGame) -> None:
    """Защитник берёт все карты со стола."""
    def_pid = game.player_ids[game.defender_idx]
    for atk, dfn in game.table:
        game.hands[def_pid].append(atk)
        if dfn:
            game.hands[def_pid].append(dfn)
    game.table = []
    _draw_cards(game, skip_pid=def_pid)   # Защитник не добирает
    _advance_after_take(game)
    game.phase = "attacking"


def do_pass(game: DurakGame) -> bool:
    """Атакующий заканчивает атаку — все карты в отбой."""
    if game.phase != "attacking" or not game.table:
        return False
    if any(dfn is None for _, dfn in game.table):
        return False    # Ещё есть незащищённые карты
    for atk, dfn in game.table:
        game.discard.append(atk)
        if dfn:
            game.discard.append(dfn)
    game.table = []
    _draw_cards(game)
    _advance_after_defense(game)
    game.phase = "attacking"
    return True


def check_finished(game: DurakGame) -> bool:
    """Проверяет завершение игры."""
    _exit_winners(game)
    active = _active(game)
    if len(active) <= 1:
        game.finished = True
        game.phase = "finished"
        game.loser_id = active[0] if active else None
        _registry.pop(game.game_id, None)
        _chat_games.pop(game.chat_id, None)
        return True
    return False


def finish_game_force(game: DurakGame) -> None:
    game.finished = True
    game.phase = "finished"
    game.loser_id = None
    _registry.pop(game.game_id, None)
    _chat_games.pop(game.chat_id, None)


# ─── Форматирование доски ────────────────────────────────────────────────────

def format_board(game: DurakGame) -> str:
    """Публичная доска: козырь, колода, стол, количество карт у игроков.

    Сами карты НЕ показываются — игрок смотрит свою руку кнопкой «👁 Карты».
    """
    trump_sym  = SUITS.get(game.trump, "?")
    deck_count = len(game.deck)

    # Стол
    if game.table:
        parts = []
        for atk, dfn in game.table:
            if dfn:
                parts.append(f"{card_display(atk)}→{card_display(dfn)}")
            else:
                parts.append(f"{card_display(atk)}→❓")
        table_str = "  ".join(parts)
    else:
        table_str = "(пусто)"

    # Игроки (только количество карт)
    lines = []
    for i, pid in enumerate(game.player_ids):
        name = game.player_names[pid]
        if pid in game.winners:
            lines.append(f"✅ {name}: вышел")
            continue
        cnt = len(game.hands.get(pid, []))
        if i == game.attacker_idx and game.phase in ("attacking", "defending"):
            icon = "⚔️"
        elif i == game.defender_idx and game.phase in ("attacking", "defending"):
            icon = "🛡"
        else:
            icon = "👤"
        lines.append(f"{icon} <b>{name}</b>: {cnt} карт")

    players_str = "\n".join(lines)

    # Подсказка хода и формат ввода
    if game.phase == "attacking":
        att_name = game.player_names.get(game.player_ids[game.attacker_idx], "?")
        action = "добавить карту или нажмите ✅ Закончить" if game.table else "введите карту в чат"
        hint = f"🎯 <b>{att_name}</b> атакует — {action}"
    elif game.phase == "defending":
        def_name = game.player_names.get(game.player_ids[game.defender_idx], "?")
        hint = f"🎯 <b>{def_name}</b> защищается — введите карту или нажмите 🤚 Взять"
    else:
        hint = ""

    fmt_hint = "<i>Формат карты: 6п, 10ч, Кб, Тк</i>  <i>(п♠ ч♥ б♦ к♣ | К=король Т=туз)</i>"

    return (
        f"🃏 <b>Дурак</b>   Козырь: {trump_sym}   Колода: {deck_count}\n"
        f"───────────────────\n"
        f"<b>Стол:</b> {table_str}\n"
        f"───────────────────\n"
        f"{players_str}\n"
        f"───────────────────\n"
        f"{hint}\n"
        f"{fmt_hint}"
    )


def format_hand_private(game: DurakGame, pid: int) -> str:
    """Строка для всплывающего уведомления: карты конкретного игрока."""
    hand  = game.hands.get(pid, [])
    trump = SUITS.get(game.trump, "?")
    if not hand:
        return f"Ваши карты (козырь {trump}):\nНет карт — вы вышли из игры!"
    cards = "  ".join(
        f"[{card_display(c)}]" if c[-1] == game.trump else card_display(c)
        for c in hand
    )
    return f"Ваши карты (козырь {trump}, [козыри]):\n{cards}"
