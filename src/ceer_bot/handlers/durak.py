"""Хэндлеры игры «Дурак» для 2–3 игроков (CEER Bot).

Поток:
  1. Игрок нажимает «🂠 Дурак» → FSM запрашивает ставку.
  2. Создаётся лобби с кнопками «Присоединиться» и «Начать».
  3. Другие жмут «Присоединиться» (до 3 игроков).
  4. Создатель нажимает «Начать» (≥2 игроков).
  5. Карты раздаются, отображается доска.
  6. Атакующий выбирает карту (или завершает атаку).
  7. Защитник бьёт карту (или берёт все карты).
  8. Игра продолжается до выявления Дурака.
"""

from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from ceer_bot.container import AppContainer
from ceer_bot.games.durak import (
    DurakGame,
    MAX_PLAYERS,
    add_player,
    check_finished,
    create_game,
    do_attack,
    do_defend,
    do_pass,
    do_take,
    finish_game_force,
    format_board,
    get_game,
    start_game,
)
from ceer_bot.keyboards.game_menu import (
    GAME_DURAK_ACTION,
    build_durak_attack,
    build_durak_defend,
    build_durak_invite,
)
from ceer_bot.services.users import InsufficientBalanceError
from ceer_bot.texts import DURAK_TEXT

logger = logging.getLogger(__name__)


class DurakFSM(StatesGroup):
    waiting_bet = State()


def _name(uid: int, username: str | None, first_name: str | None) -> str:
    return f"@{username}" if username else (first_name or f"user{uid}")


def _board_keyboard(game: DurakGame):
    """Возвращает нужную клавиатуру в зависимости от фазы игры."""
    game_id = game.game_id
    trump   = game.trump

    if game.phase == "attacking":
        att_pid = game.player_ids[game.attacker_idx]
        hand    = game.hands.get(att_pid, [])
        return build_durak_attack(game_id, hand, game.table, trump)

    if game.phase == "defending":
        def_pid = game.player_ids[game.defender_idx]
        hand    = game.hands.get(def_pid, [])
        return build_durak_defend(game_id, hand, trump)

    return None


async def _settle(game: DurakGame, container: AppContainer, currency: str) -> str:
    """Урегулирует ставки и возвращает текст результата."""
    loser_id = game.loser_id
    loser_name = game.player_names.get(loser_id, "?") if loser_id else None

    if loser_id and game.bet > 0:
        winners = [pid for pid in game.player_ids if pid != loser_id]
        try:
            total = game.bet * len(winners)
            await container.user_service.debit(loser_id, total, "durak_loss")
            for wid in winners:
                await container.user_service.credit(wid, game.bet, "durak_win")
        except InsufficientBalanceError:
            logger.warning("Недостаточно средств для расчёта в дураке game_id=%s", game.game_id)

    return DURAK_TEXT.result(loser_name, game.bet, currency)


def build_durak_router(container: AppContainer) -> Router:
    router   = Router(name="ceer_durak")
    currency = container.user_service.wallet_currency

    # ── Кнопка «Дурак» в меню ─────────────────────────────────────────────

    @router.callback_query(F.data == GAME_DURAK_ACTION)
    async def handle_durak_menu(callback: CallbackQuery, state: FSMContext) -> None:
        await callback.answer()
        await state.set_state(DurakFSM.waiting_bet)
        settings = container.settings
        max_str  = str(settings.game_max_bet) if settings.game_max_bet else "∞"
        text = DURAK_TEXT.ASK_BET.format(
            min_bet=settings.game_min_bet,
            max_bet=max_str,
            currency=currency,
        )
        await callback.message.answer(text, parse_mode="HTML")  # type: ignore[union-attr]

    # ── Ввод ставки ───────────────────────────────────────────────────────

    @router.message(DurakFSM.waiting_bet)
    async def handle_durak_bet(message: Message, state: FSMContext) -> None:
        if message.from_user is None:
            return

        raw = (message.text or "").strip().replace(",", ".")
        try:
            bet = Decimal(raw)
            if bet < 0:
                raise ValueError
        except (InvalidOperation, ValueError):
            await message.answer(DURAK_TEXT.INVALID_BET, parse_mode="HTML")
            return

        settings = container.settings
        min_bet  = Decimal(str(settings.game_min_bet))
        max_bet  = Decimal(str(settings.game_max_bet)) if settings.game_max_bet else None

        if bet > 0 and bet < min_bet:
            await message.answer(DURAK_TEXT.BET_TOO_LOW.format(min_bet=min_bet, currency=currency), parse_mode="HTML")
            return
        if max_bet and bet > max_bet:
            await message.answer(DURAK_TEXT.BET_TOO_HIGH.format(max_bet=max_bet, currency=currency), parse_mode="HTML")
            return
        if bet > 0:
            profile = await container.user_service.get_profile(message.from_user.id)
            if profile is None or profile.balance < bet:
                balance = profile.balance if profile else Decimal("0")
                await message.answer(DURAK_TEXT.INSUFFICIENT.format(balance=balance, currency=currency), parse_mode="HTML")
                return

        await state.clear()

        uid   = message.from_user.id
        uname = _name(uid, message.from_user.username, message.from_user.first_name)
        sent  = await message.answer(
            DURAK_TEXT.invite(uname, bet, currency, [uname], MAX_PLAYERS),
            reply_markup=build_durak_invite("pending", [uname]),
            parse_mode="HTML",
        )
        game = create_game(
            chat_id=message.chat.id,
            message_id=sent.message_id,
            creator_id=uid,
            creator_name=uname,
            bet=bet,
        )
        await sent.edit_reply_markup(
            reply_markup=build_durak_invite(game.game_id, list(game.player_names.values())),
        )

    # ── Присоединиться ────────────────────────────────────────────────────

    @router.callback_query(F.data.startswith("durak:join:"))
    async def handle_durak_join(callback: CallbackQuery) -> None:
        if callback.from_user is None:
            await callback.answer()
            return

        game_id = (callback.data or "").split(":", 2)[2]
        game    = get_game(game_id)

        if game is None:
            await callback.answer(DURAK_TEXT.GAME_NOT_FOUND, show_alert=True)
            return
        if game.phase != "joining":
            await callback.answer(DURAK_TEXT.GAME_NOT_FOUND, show_alert=True)
            return

        uid   = callback.from_user.id
        uname = _name(uid, callback.from_user.username, callback.from_user.first_name)

        if uid in game.player_ids:
            await callback.answer(DURAK_TEXT.ALREADY_IN_GAME, show_alert=True)
            return

        # Проверка баланса
        if game.bet > 0:
            profile = await container.user_service.get_profile(uid)
            if profile is None or profile.balance < game.bet:
                balance = profile.balance if profile else Decimal("0")
                await callback.answer(DURAK_TEXT.INSUFFICIENT.format(balance=balance, currency=currency), show_alert=True)
                return

        if not add_player(game, uid, uname):
            await callback.answer(DURAK_TEXT.GAME_FULL, show_alert=True)
            return

        names = list(game.player_names.values())
        creator_name = game.player_names[game.creator_id]
        await callback.message.edit_text(  # type: ignore[union-attr]
            DURAK_TEXT.invite(creator_name, game.bet, currency, names, MAX_PLAYERS),
            reply_markup=build_durak_invite(game_id, names),
            parse_mode="HTML",
        )
        await callback.answer(f"Вы вошли в игру!")

    # ── Отмена ────────────────────────────────────────────────────────────

    @router.callback_query(F.data.startswith("durak:cancel:"))
    async def handle_durak_cancel(callback: CallbackQuery) -> None:
        if callback.from_user is None:
            await callback.answer()
            return

        game_id = (callback.data or "").split(":", 2)[2]
        game    = get_game(game_id)

        if game and callback.from_user.id != game.creator_id:
            await callback.answer(DURAK_TEXT.NOT_CREATOR, show_alert=True)
            return
        if game:
            finish_game_force(game)

        await callback.message.edit_text(DURAK_TEXT.CANCEL, parse_mode="HTML")  # type: ignore[union-attr]
        await callback.answer()

    # ── Начать игру ───────────────────────────────────────────────────────

    @router.callback_query(F.data.startswith("durak:start:"))
    async def handle_durak_start(callback: CallbackQuery) -> None:
        if callback.from_user is None:
            await callback.answer()
            return

        game_id = (callback.data or "").split(":", 2)[2]
        game    = get_game(game_id)

        if game is None:
            await callback.answer(DURAK_TEXT.GAME_NOT_FOUND, show_alert=True)
            return
        if callback.from_user.id != game.creator_id:
            await callback.answer(DURAK_TEXT.NOT_CREATOR, show_alert=True)
            return
        if len(game.player_ids) < 2:
            await callback.answer(DURAK_TEXT.NOT_ENOUGH, show_alert=True)
            return

        start_game(game)
        board_text = format_board(game)
        kb         = _board_keyboard(game)

        await callback.message.edit_text(board_text, reply_markup=kb, parse_mode="HTML")  # type: ignore[union-attr]
        await callback.answer()

    # ── Атака ─────────────────────────────────────────────────────────────

    @router.callback_query(F.data.startswith("durak:atk:"))
    async def handle_durak_attack(callback: CallbackQuery) -> None:
        if callback.from_user is None:
            await callback.answer()
            return

        parts = (callback.data or "").split(":")   # durak:atk:{game_id}:{card}
        if len(parts) != 4:
            await callback.answer()
            return

        game_id, card = parts[2], parts[3]
        game = get_game(game_id)

        if game is None:
            await callback.answer(DURAK_TEXT.GAME_NOT_FOUND, show_alert=True)
            return

        uid = callback.from_user.id
        if uid not in game.player_ids:
            await callback.answer(DURAK_TEXT.NOT_A_PLAYER, show_alert=True)
            return

        att_pid = game.player_ids[game.attacker_idx]
        if uid != att_pid:
            await callback.answer(DURAK_TEXT.NOT_YOUR_TURN, show_alert=True)
            return

        if not do_attack(game, card):
            await callback.answer(DURAK_TEXT.CARD_INVALID, show_alert=True)
            return

        if check_finished(game):
            result_text = await _settle(game, container, currency)
            board_text  = format_board(game)
            await callback.message.edit_text(  # type: ignore[union-attr]
                board_text + "\n\n" + result_text,
                reply_markup=None,
                parse_mode="HTML",
            )
        else:
            await callback.message.edit_text(  # type: ignore[union-attr]
                format_board(game),
                reply_markup=_board_keyboard(game),
                parse_mode="HTML",
            )
        await callback.answer()

    # ── Защита ────────────────────────────────────────────────────────────

    @router.callback_query(F.data.startswith("durak:def:"))
    async def handle_durak_defend(callback: CallbackQuery) -> None:
        if callback.from_user is None:
            await callback.answer()
            return

        parts = (callback.data or "").split(":")
        if len(parts) != 4:
            await callback.answer()
            return

        game_id, card = parts[2], parts[3]
        game = get_game(game_id)

        if game is None:
            await callback.answer(DURAK_TEXT.GAME_NOT_FOUND, show_alert=True)
            return

        uid = callback.from_user.id
        if uid not in game.player_ids:
            await callback.answer(DURAK_TEXT.NOT_A_PLAYER, show_alert=True)
            return

        def_pid = game.player_ids[game.defender_idx]
        if uid != def_pid:
            await callback.answer(DURAK_TEXT.NOT_YOUR_TURN, show_alert=True)
            return

        if not do_defend(game, card):
            await callback.answer(DURAK_TEXT.CARD_INVALID, show_alert=True)
            return

        if check_finished(game):
            result_text = await _settle(game, container, currency)
            await callback.message.edit_text(  # type: ignore[union-attr]
                format_board(game) + "\n\n" + result_text,
                reply_markup=None,
                parse_mode="HTML",
            )
        else:
            await callback.message.edit_text(  # type: ignore[union-attr]
                format_board(game),
                reply_markup=_board_keyboard(game),
                parse_mode="HTML",
            )
        await callback.answer()

    # ── Взять карты ───────────────────────────────────────────────────────

    @router.callback_query(F.data.startswith("durak:take:"))
    async def handle_durak_take(callback: CallbackQuery) -> None:
        if callback.from_user is None:
            await callback.answer()
            return

        game_id = (callback.data or "").split(":", 2)[2]
        game    = get_game(game_id)

        if game is None:
            await callback.answer(DURAK_TEXT.GAME_NOT_FOUND, show_alert=True)
            return

        uid = callback.from_user.id
        if uid not in game.player_ids:
            await callback.answer(DURAK_TEXT.NOT_A_PLAYER, show_alert=True)
            return

        def_pid = game.player_ids[game.defender_idx]
        if uid != def_pid:
            await callback.answer(DURAK_TEXT.NOT_YOUR_TURN, show_alert=True)
            return

        do_take(game)

        if check_finished(game):
            result_text = await _settle(game, container, currency)
            await callback.message.edit_text(  # type: ignore[union-attr]
                format_board(game) + "\n\n" + result_text,
                reply_markup=None,
                parse_mode="HTML",
            )
        else:
            await callback.message.edit_text(  # type: ignore[union-attr]
                format_board(game),
                reply_markup=_board_keyboard(game),
                parse_mode="HTML",
            )
        await callback.answer()

    # ── Закончить атаку (Pass) ────────────────────────────────────────────

    @router.callback_query(F.data.startswith("durak:pass:"))
    async def handle_durak_pass(callback: CallbackQuery) -> None:
        if callback.from_user is None:
            await callback.answer()
            return

        game_id = (callback.data or "").split(":", 2)[2]
        game    = get_game(game_id)

        if game is None:
            await callback.answer(DURAK_TEXT.GAME_NOT_FOUND, show_alert=True)
            return

        uid = callback.from_user.id
        if uid not in game.player_ids:
            await callback.answer(DURAK_TEXT.NOT_A_PLAYER, show_alert=True)
            return

        att_pid = game.player_ids[game.attacker_idx]
        if uid != att_pid:
            await callback.answer(DURAK_TEXT.NOT_YOUR_TURN, show_alert=True)
            return

        if not do_pass(game):
            await callback.answer(DURAK_TEXT.CARD_INVALID, show_alert=True)
            return

        if check_finished(game):
            result_text = await _settle(game, container, currency)
            await callback.message.edit_text(  # type: ignore[union-attr]
                format_board(game) + "\n\n" + result_text,
                reply_markup=None,
                parse_mode="HTML",
            )
        else:
            await callback.message.edit_text(  # type: ignore[union-attr]
                format_board(game),
                reply_markup=_board_keyboard(game),
                parse_mode="HTML",
            )
        await callback.answer()

    return router
