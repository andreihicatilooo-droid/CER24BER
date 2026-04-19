"""Хэндлеры игры «Блэкджек» для двоих (CEER Bot).

Поток:
  1. Игрок нажимает «🃏 Блэкджек» в меню игры → FSM запрашивает ставку.
  2. Ставка подтверждена → создаётся игра, отправляется сообщение-приглашение.
  3. Второй игрок принимает → карты раздаются, доска отображается.
  4. Игрок 1 жмёт «Ещё карту» (Hit) или «Хватит» (Stand).
     — Hit: получает карту, при перебое игра завершается немедленно.
     — Stand: ход переходит к игроку 2.
  5. После Stand/Bust обоих — очки сравниваются, баланс урегулируется.
"""

from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from ceer_bot.container import AppContainer
from ceer_bot.games.blackjack import (
    BlackjackGame,
    accept_game,
    active_score,
    create_game,
    finish_game,
    get_game,
    hand_score,
    hit,
    resolve_winner,
    stand,
)
from ceer_bot.keyboards.game_menu import (
    GAME_BJ_ACTION,
    build_bj_board,
    build_bj_invite,
)
from ceer_bot.services.users import InsufficientBalanceError
from ceer_bot.texts import BJ_TEXT

logger = logging.getLogger(__name__)


class BlackjackFSM(StatesGroup):
    waiting_bet = State()


def _name(user_id: int, username: str | None, first_name: str | None) -> str:
    return f"@{username}" if username else (first_name or f"user{user_id}")


async def _render_board(game: BlackjackGame, callback_or_message: CallbackQuery) -> None:
    """Перерисовывает доску в сообщении."""
    s1   = hand_score(game.hand1)
    s2   = hand_score(game.hand2)
    text = BJ_TEXT.board(
        p1_name=game.player1_name, hand1=game.hand1, score1=s1,
        p2_name=game.player2_name or "?", hand2=game.hand2, score2=s2,
        active_player=game.active_player,
        bet=game.bet,
        currency="?",  # подставится ниже
    )
    # currency недоступен здесь напрямую — текст собирается через BJ_TEXT.board
    # поэтому этот хелпер не используем; вместо него вызываем напрямую в хэндлерах


async def _settle(
    game: BlackjackGame,
    container: AppContainer,
) -> tuple[str | None, Decimal]:
    """Урегулирует баланс, возвращает (winner_name, new_balance_winner)."""
    winner_id = resolve_winner(game)
    finish_game(game, winner_id)

    if winner_id and game.bet > 0:
        loser_id = game.player2_id if winner_id == game.player1_id else game.player1_id
        try:
            await container.user_service.debit(loser_id, game.bet, "bj_loss")
            await container.user_service.credit(winner_id, game.bet * 2, "bj_win")
            winner_profile = await container.user_service.get_profile(winner_id)
            return (
                game.player1_name if winner_id == game.player1_id else game.player2_name,
                winner_profile.balance if winner_profile else Decimal("0"),
            )
        except InsufficientBalanceError:
            logger.warning("InsufficientBalance при урегулировании BJ game_id=%s", game.game_id)

    winner_name = (
        game.player1_name if winner_id == game.player1_id else game.player2_name
    ) if winner_id else None
    return winner_name, Decimal("0")


def build_blackjack_router(container: AppContainer) -> Router:
    router = Router(name="ceer_blackjack")
    currency = container.user_service.wallet_currency

    # ── Кнопка «Блэкджек» в меню ──────────────────────────────────────────

    @router.callback_query(F.data == GAME_BJ_ACTION)
    async def handle_bj_start(callback: CallbackQuery, state: FSMContext) -> None:
        await callback.answer()
        await state.set_state(BlackjackFSM.waiting_bet)
        settings = container.settings
        max_bet_str = str(settings.game_max_bet) if settings.game_max_bet else "∞"
        text = BJ_TEXT.ASK_BET.format(
            min_bet=settings.game_min_bet,
            max_bet=max_bet_str,
            currency=currency,
        )
        await callback.message.answer(text, parse_mode="HTML")  # type: ignore[union-attr]

    # ── Ввод ставки ────────────────────────────────────────────────────────

    @router.message(BlackjackFSM.waiting_bet)
    async def handle_bj_bet(message: Message, state: FSMContext) -> None:
        if message.from_user is None:
            return

        raw = (message.text or "").strip().replace(",", ".")
        try:
            bet = Decimal(raw)
            if bet < 0:
                raise ValueError
        except (InvalidOperation, ValueError):
            await message.answer(BJ_TEXT.INVALID_BET, parse_mode="HTML")
            return

        settings = container.settings
        min_bet = Decimal(str(settings.game_min_bet))
        max_bet = Decimal(str(settings.game_max_bet)) if settings.game_max_bet else None

        if bet > 0 and bet < min_bet:
            await message.answer(BJ_TEXT.BET_TOO_LOW.format(min_bet=min_bet, currency=currency), parse_mode="HTML")
            return
        if max_bet and bet > max_bet:
            await message.answer(BJ_TEXT.BET_TOO_HIGH.format(max_bet=max_bet, currency=currency), parse_mode="HTML")
            return

        if bet > 0:
            profile = await container.user_service.get_profile(message.from_user.id)
            if profile is None or profile.balance < bet:
                balance = profile.balance if profile else Decimal("0")
                await message.answer(BJ_TEXT.INSUFFICIENT.format(balance=balance, currency=currency), parse_mode="HTML")
                return

        await state.clear()

        creator_name = _name(message.from_user.id, message.from_user.username, message.from_user.first_name)
        sent = await message.answer(
            BJ_TEXT.invite(creator_name, bet, currency),
            reply_markup=build_bj_invite("pending"),
            parse_mode="HTML",
        )
        game = create_game(
            chat_id=message.chat.id,
            message_id=sent.message_id,
            player1_id=message.from_user.id,
            player1_name=creator_name,
            bet=bet,
        )
        await sent.edit_reply_markup(reply_markup=build_bj_invite(game.game_id))

    # ── Принятие вызова ────────────────────────────────────────────────────

    @router.callback_query(F.data.startswith("bj:accept:"))
    async def handle_bj_accept(callback: CallbackQuery) -> None:
        if callback.from_user is None:
            await callback.answer()
            return

        game_id = (callback.data or "").split(":", 2)[2]
        game = get_game(game_id)

        if game is None:
            await callback.answer(BJ_TEXT.GAME_NOT_FOUND, show_alert=True)
            return
        if game.player2_id is not None:
            await callback.answer(BJ_TEXT.ALREADY_ACCEPTED, show_alert=True)
            return
        if callback.from_user.id == game.player1_id:
            await callback.answer(BJ_TEXT.CANNOT_ACCEPT_OWN, show_alert=True)
            return

        if game.bet > 0:
            profile = await container.user_service.get_profile(callback.from_user.id)
            if profile is None or profile.balance < game.bet:
                balance = profile.balance if profile else Decimal("0")
                await callback.answer(BJ_TEXT.INSUFFICIENT.format(balance=balance, currency=currency), show_alert=True)
                return

        p2_name = _name(callback.from_user.id, callback.from_user.username, callback.from_user.first_name)
        accept_game(game, callback.from_user.id, p2_name)

        s1 = hand_score(game.hand1)
        s2 = hand_score(game.hand2)
        text = BJ_TEXT.board(
            p1_name=game.player1_name, hand1=game.hand1, score1=s1,
            p2_name=p2_name, hand2=game.hand2, score2=s2,
            active_player=1, bet=game.bet, currency=currency,
        )

        # Проверяем натуральный блэкджек (21 с 2 карт) у игрока 1
        if s1 == 21 and len(game.hand1) == 2:
            winner_name, new_balance = await _settle(game, container)
            finish_text = BJ_TEXT.result(
                winner_name=winner_name,
                p1_name=game.player1_name, hand1=game.hand1, score1=s1,
                p2_name=p2_name, hand2=game.hand2, score2=s2,
                bet=game.bet, currency=currency, new_balance=new_balance,
            )
            await callback.message.edit_text(finish_text, reply_markup=None, parse_mode="HTML")  # type: ignore[union-attr]
        else:
            await callback.message.edit_text(  # type: ignore[union-attr]
                text, reply_markup=build_bj_board(game.game_id), parse_mode="HTML",
            )
        await callback.answer()

    # ── Отказ / отмена ─────────────────────────────────────────────────────

    @router.callback_query(F.data.startswith("bj:decline:"))
    async def handle_bj_decline(callback: CallbackQuery) -> None:
        if callback.from_user is None:
            await callback.answer()
            return
        game_id = (callback.data or "").split(":", 2)[2]
        game = get_game(game_id)
        if game and callback.from_user.id != game.player1_id:
            await callback.answer()
            return
        if game:
            finish_game(game, None)
        await callback.message.edit_text(BJ_TEXT.CANCEL, parse_mode="HTML")  # type: ignore[union-attr]
        await callback.answer()

    # ── Ещё карту (Hit) ────────────────────────────────────────────────────

    @router.callback_query(F.data.startswith("bj:hit:"))
    async def handle_bj_hit(callback: CallbackQuery) -> None:
        if callback.from_user is None:
            await callback.answer()
            return

        game_id = (callback.data or "").split(":", 2)[2]
        game = get_game(game_id)
        if game is None:
            await callback.answer(BJ_TEXT.GAME_NOT_FOUND, show_alert=True)
            return

        pid = callback.from_user.id
        if pid not in (game.player1_id, game.player2_id):
            await callback.answer(BJ_TEXT.NOT_A_PLAYER, show_alert=True)
            return

        expected = game.player1_id if game.active_player == 1 else game.player2_id
        if pid != expected:
            await callback.answer(BJ_TEXT.NOT_YOUR_TURN, show_alert=True)
            return

        hit(game)
        score = active_score(game)

        s1 = hand_score(game.hand1)
        s2 = hand_score(game.hand2)

        if score > 21:
            # Перебор — противник побеждает
            winner_id = game.player2_id if game.active_player == 1 else game.player1_id
            winner_name = game.player2_name if game.active_player == 1 else game.player1_name
            finish_game(game, winner_id)
            new_balance = Decimal("0")
            if game.bet > 0 and winner_id:
                loser_id = game.player1_id if winner_id == game.player2_id else game.player2_id
                try:
                    await container.user_service.debit(loser_id, game.bet, "bj_loss")
                    await container.user_service.credit(winner_id, game.bet * 2, "bj_win")
                    wp = await container.user_service.get_profile(winner_id)
                    new_balance = wp.balance if wp else Decimal("0")
                except InsufficientBalanceError:
                    logger.warning("InsufficientBalance при перебое BJ game_id=%s", game_id)

            text = BJ_TEXT.result(
                winner_name=winner_name,
                p1_name=game.player1_name, hand1=game.hand1, score1=s1,
                p2_name=game.player2_name or "?", hand2=game.hand2, score2=s2,
                bet=game.bet, currency=currency, new_balance=new_balance,
            )
            await callback.message.edit_text(text, reply_markup=None, parse_mode="HTML")  # type: ignore[union-attr]
        else:
            text = BJ_TEXT.board(
                p1_name=game.player1_name, hand1=game.hand1, score1=s1,
                p2_name=game.player2_name or "?", hand2=game.hand2, score2=s2,
                active_player=game.active_player, bet=game.bet, currency=currency,
            )
            await callback.message.edit_text(text, reply_markup=build_bj_board(game.game_id), parse_mode="HTML")  # type: ignore[union-attr]

        await callback.answer()

    # ── Хватит (Stand) ────────────────────────────────────────────────────

    @router.callback_query(F.data.startswith("bj:stand:"))
    async def handle_bj_stand(callback: CallbackQuery) -> None:
        if callback.from_user is None:
            await callback.answer()
            return

        game_id = (callback.data or "").split(":", 2)[2]
        game = get_game(game_id)
        if game is None:
            await callback.answer(BJ_TEXT.GAME_NOT_FOUND, show_alert=True)
            return

        pid = callback.from_user.id
        if pid not in (game.player1_id, game.player2_id):
            await callback.answer(BJ_TEXT.NOT_A_PLAYER, show_alert=True)
            return

        expected = game.player1_id if game.active_player == 1 else game.player2_id
        if pid != expected:
            await callback.answer(BJ_TEXT.NOT_YOUR_TURN, show_alert=True)
            return

        both_done = stand(game)
        s1 = hand_score(game.hand1)
        s2 = hand_score(game.hand2)

        if both_done:
            winner_name, new_balance = await _settle(game, container)
            text = BJ_TEXT.result(
                winner_name=winner_name,
                p1_name=game.player1_name, hand1=game.hand1, score1=s1,
                p2_name=game.player2_name or "?", hand2=game.hand2, score2=s2,
                bet=game.bet, currency=currency, new_balance=new_balance,
            )
            await callback.message.edit_text(text, reply_markup=None, parse_mode="HTML")  # type: ignore[union-attr]
        else:
            # Ход передан второму игроку
            text = BJ_TEXT.board(
                p1_name=game.player1_name, hand1=game.hand1, score1=s1,
                p2_name=game.player2_name or "?", hand2=game.hand2, score2=s2,
                active_player=game.active_player, bet=game.bet, currency=currency,
            )
            await callback.message.edit_text(text, reply_markup=build_bj_board(game.game_id), parse_mode="HTML")  # type: ignore[union-attr]

        await callback.answer()

    return router
