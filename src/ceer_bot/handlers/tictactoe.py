"""Хэндлеры игры «Крестики-нолики» для CEER Bot.

Поток:
  1. Пользователь нажимает «Крестики-нолики» в меню игры.
  2. FSM (TttFSM.waiting_bet) ждёт ввода ставки текстом.
  3. Ставка подтверждена → создаётся игра, отправляется сообщение-приглашение.
  4. Второй игрок нажимает «Принять вызов» → доска появляется.
  5. Игроки нажимают на ячейки доски — ходы через callback_data «ttt:move:{id}:{cell}».
  6. При победе или ничьей — баланс урегулируется через CeerUserService.
"""

from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from ceer_bot.container import AppContainer
from ceer_bot.games.tictactoe import (
    EMPTY,
    X,
    accept_game,
    check_winner,
    create_game,
    finish_game,
    get_game,
    is_draw,
    make_move,
    next_turn,
)
from ceer_bot.keyboards.game_menu import (
    GAME_MENU_ACTION,
    GAME_TTT_ACTION,
    build_ttt_board,
    build_ttt_invite,
)
from ceer_bot.services.users import InsufficientBalanceError
from ceer_bot.texts import TTT_TEXT

logger = logging.getLogger(__name__)


class TttFSM(StatesGroup):
    waiting_bet = State()


def _display_name(user_id: int, username: str | None, first_name: str | None) -> str:
    return f"@{username}" if username else (first_name or f"user{user_id}")


def build_tictactoe_router(container: AppContainer) -> Router:
    router = Router(name="ceer_tictactoe")

    # ── Нажатие «Крестики-нолики» в меню ──────────────────────────────────

    @router.callback_query(F.data == GAME_TTT_ACTION)
    async def handle_ttt_start(callback: CallbackQuery, state: FSMContext) -> None:
        await callback.answer()
        await state.set_state(TttFSM.waiting_bet)
        settings = container.settings
        text = TTT_TEXT.ASK_BET.format(
            min_bet=settings.game_min_bet,
            max_bet=settings.game_max_bet if settings.game_max_bet else "∞",
            currency=container.user_service.wallet_currency,
        )
        await callback.message.answer(text, parse_mode="HTML")  # type: ignore[union-attr]

    # ── Ввод ставки ────────────────────────────────────────────────────────

    @router.message(TttFSM.waiting_bet)
    async def handle_ttt_bet_input(message: Message, state: FSMContext) -> None:
        if message.from_user is None:
            return

        raw = (message.text or "").strip().replace(",", ".")
        try:
            bet = Decimal(raw)
            if bet < 0:
                raise ValueError
        except (InvalidOperation, ValueError):
            await message.answer(TTT_TEXT.INVALID_BET, parse_mode="HTML")
            return

        settings = container.settings
        currency = container.user_service.wallet_currency
        min_bet = Decimal(str(settings.game_min_bet))
        max_bet = Decimal(str(settings.game_max_bet)) if settings.game_max_bet else None

        if bet > 0 and bet < min_bet:
            await message.answer(
                TTT_TEXT.BET_TOO_LOW.format(min_bet=min_bet, currency=currency),
                parse_mode="HTML",
            )
            return
        if max_bet and bet > max_bet:
            await message.answer(
                TTT_TEXT.BET_TOO_HIGH.format(max_bet=max_bet, currency=currency),
                parse_mode="HTML",
            )
            return

        # Проверяем баланс создателя, если ставка > 0
        if bet > 0:
            profile = await container.user_service.get_profile(message.from_user.id)
            if profile is None or profile.balance < bet:
                balance = profile.balance if profile else Decimal("0")
                await message.answer(
                    TTT_TEXT.INSUFFICIENT.format(balance=balance, currency=currency),
                    parse_mode="HTML",
                )
                return

        await state.clear()

        creator_name = _display_name(
            message.from_user.id,
            message.from_user.username,
            message.from_user.first_name,
        )
        text = TTT_TEXT.invite(creator_name, bet, currency)

        # Отправляем сообщение-приглашение и создаём игру
        sent = await message.answer(text, parse_mode="HTML", reply_markup=build_ttt_invite("pending"))
        game = create_game(
            chat_id=message.chat.id,
            message_id=sent.message_id,
            player_x_id=message.from_user.id,
            player_x_name=creator_name,
            bet=bet,
        )
        # Обновляем клавиатуру с реальным game_id
        await sent.edit_reply_markup(reply_markup=build_ttt_invite(game.game_id))

    # ── Принятие вызова ────────────────────────────────────────────────────

    @router.callback_query(F.data.startswith("ttt:accept:"))
    async def handle_ttt_accept(callback: CallbackQuery) -> None:
        if callback.from_user is None:
            await callback.answer()
            return

        game_id = callback.data.split(":", 2)[2]  # type: ignore[union-attr]
        game = get_game(game_id)

        if game is None:
            await callback.answer(TTT_TEXT.GAME_NOT_FOUND, show_alert=True)
            return
        if game.player_o_id is not None:
            await callback.answer(TTT_TEXT.ALREADY_ACCEPTED, show_alert=True)
            return
        if callback.from_user.id == game.player_x_id:
            await callback.answer(TTT_TEXT.CANNOT_ACCEPT_OWN, show_alert=True)
            return

        # Проверяем баланс второго игрока, если ставка > 0
        currency = container.user_service.wallet_currency
        if game.bet > 0:
            profile = await container.user_service.get_profile(callback.from_user.id)
            if profile is None or profile.balance < game.bet:
                balance = profile.balance if profile else Decimal("0")
                await callback.answer(
                    TTT_TEXT.INSUFFICIENT.format(balance=balance, currency=currency),
                    show_alert=True,
                )
                return

        o_name = _display_name(
            callback.from_user.id,
            callback.from_user.username,
            callback.from_user.first_name,
        )
        accept_game(game, callback.from_user.id, o_name)

        # Сразу показываем доску — ход X
        board_text = TTT_TEXT.board(
            game_x=game.player_x_name,
            game_o=o_name,
            turn_name=game.player_x_name,
            bet=game.bet,
            currency=currency,
        )
        await callback.message.edit_text(  # type: ignore[union-attr]
            board_text,
            reply_markup=build_ttt_board(game.board, game.game_id, finished=False),
            parse_mode="HTML",
        )
        await callback.answer()

    # ── Отказ / отмена вызова ──────────────────────────────────────────────

    @router.callback_query(F.data.startswith("ttt:decline:"))
    async def handle_ttt_decline(callback: CallbackQuery) -> None:
        if callback.from_user is None:
            await callback.answer()
            return
        game_id = callback.data.split(":", 2)[2]  # type: ignore[union-attr]
        game = get_game(game_id)
        if game and callback.from_user.id != game.player_x_id:
            await callback.answer()
            return
        if game:
            finish_game(game, None)
        await callback.message.edit_text(TTT_TEXT.CANCEL, parse_mode="HTML")  # type: ignore[union-attr]
        await callback.answer()

    # ── Ход ───────────────────────────────────────────────────────────────

    @router.callback_query(F.data.startswith("ttt:move:"))
    async def handle_ttt_move(callback: CallbackQuery) -> None:
        if callback.from_user is None:
            await callback.answer()
            return

        parts = (callback.data or "").split(":")  # ttt:move:{game_id}:{cell}
        if len(parts) != 4:
            await callback.answer()
            return

        game_id = parts[2]
        try:
            cell = int(parts[3])
        except ValueError:
            await callback.answer()
            return

        game = get_game(game_id)
        if game is None:
            await callback.answer(TTT_TEXT.GAME_NOT_FOUND, show_alert=True)
            return

        player_id = callback.from_user.id
        if player_id not in (game.player_x_id, game.player_o_id):
            await callback.answer(TTT_TEXT.NOT_A_PLAYER, show_alert=True)
            return
        if game.current_turn_id != player_id:
            await callback.answer(TTT_TEXT.NOT_YOUR_TURN, show_alert=True)
            return

        if not make_move(game, cell, player_id):
            await callback.answer()
            return

        currency = container.user_service.wallet_currency

        # Проверяем победителя
        winner_symbol = check_winner(game.board)
        draw = is_draw(game.board)

        if winner_symbol or draw:
            finish_game(game, winner_symbol)

            if winner_symbol and game.bet > 0:
                winner_id = game.winner_id
                loser_id = game.player_o_id if winner_id == game.player_x_id else game.player_x_id
                try:
                    # Списываем со счёта проигравшего, зачисляем победителю
                    await container.user_service.debit(loser_id, game.bet, "ttt_loss")
                    await container.user_service.credit(winner_id, game.bet * 2, "ttt_win")
                    winner_profile = await container.user_service.get_profile(winner_id)
                    new_balance = winner_profile.balance if winner_profile else Decimal("0")
                except InsufficientBalanceError:
                    new_balance = Decimal("0")
                    logger.warning("Недостаточно средств при завершении TTT game_id=%s", game_id)
            else:
                new_balance = Decimal("0")

            winner_name = (
                game.player_x_name if game.winner_id == game.player_x_id else game.player_o_name
            ) if game.winner_id else None

            if winner_name:
                result_text = TTT_TEXT.win(winner_name, game.bet, currency, new_balance)
            else:
                result_text = TTT_TEXT.DRAW

            await callback.message.edit_text(  # type: ignore[union-attr]
                result_text,
                reply_markup=build_ttt_board(game.board, game_id, finished=True),
                parse_mode="HTML",
            )
        else:
            next_turn(game)
            turn_name = (
                game.player_x_name if game.current_turn_id == game.player_x_id else game.player_o_name or ""
            )
            board_text = TTT_TEXT.board(
                game_x=game.player_x_name,
                game_o=game.player_o_name or "",
                turn_name=turn_name,
                bet=game.bet,
                currency=currency,
            )
            await callback.message.edit_text(  # type: ignore[union-attr]
                board_text,
                reply_markup=build_ttt_board(game.board, game.game_id, finished=False),
                parse_mode="HTML",
            )

        await callback.answer()

    # ── Заглушка для нажатия на занятую ячейку ─────────────────────────────

    @router.callback_query(F.data == "ttt:noop")
    async def handle_ttt_noop(callback: CallbackQuery) -> None:
        await callback.answer()

    return router
