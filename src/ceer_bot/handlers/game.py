"""Обработчики игровых команд: /game, покер-дуэль с вводом ставки через FSM.

/game доступна только в чатах (не в ЛС).
Покер-дуэль: пользователь вводит ставку → разыгрывается дуэль →
баланс обновляется через CeerUserService.
"""

from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from ceer_bot.container import AppContainer
from ceer_bot.games.poker import PokerResult, play_duel
from ceer_bot.keyboards.game_menu import (
    GAME_MENU_ACTION,
    GAME_POKER_ACTION,
    build_cancel_game,
    build_game_menu,
)
from ceer_bot.services.users import InsufficientBalanceError
from ceer_bot.texts import GAME_TEXT, POKER_TEXT

logger = logging.getLogger(__name__)


class PokerFSM(StatesGroup):
    waiting_bet = State()


def build_game_router(container: AppContainer) -> Router:
    router = Router(name="ceer_game")

    # ── /game — только в группах ───────────────────────────────────────────

    @router.message(Command("game"), ~F.chat.type.in_({"private"}))
    async def handle_game_command(message: Message) -> None:
        await message.answer(GAME_TEXT.CHOOSE, reply_markup=build_game_menu(), parse_mode="HTML")

    @router.message(Command("game"), F.chat.type == "private")
    async def handle_game_private(message: Message) -> None:
        await message.answer(GAME_TEXT.PRIVATE_ONLY)

    # ── Меню игры (callback из чата) ──────────────────────────────────────

    @router.callback_query(F.data == GAME_MENU_ACTION)
    async def handle_game_menu(callback: CallbackQuery, state: FSMContext) -> None:
        await state.clear()
        await callback.answer()
        await callback.message.edit_text(  # type: ignore[union-attr]
            GAME_TEXT.CHOOSE,
            reply_markup=build_game_menu(),
            parse_mode="HTML",
        )

    # ── Покер-дуэль: начало ───────────────────────────────────────────────

    @router.callback_query(F.data == GAME_POKER_ACTION)
    async def handle_poker_start(callback: CallbackQuery, state: FSMContext) -> None:
        await callback.answer()
        await state.set_state(PokerFSM.waiting_bet)
        await callback.message.answer(  # type: ignore[union-attr]
            POKER_TEXT.RULES,
            reply_markup=build_cancel_game(),
            parse_mode="HTML",
        )

    # ── Отмена игры ───────────────────────────────────────────────────────

    @router.callback_query(F.data == "game:cancel")
    async def handle_cancel(callback: CallbackQuery, state: FSMContext) -> None:
        await state.clear()
        await callback.answer()
        await callback.message.answer(POKER_TEXT.CANCEL)  # type: ignore[union-attr]

    # ── Ввод ставки (текстовое сообщение в состоянии waiting_bet) ─────────

    @router.message(PokerFSM.waiting_bet)
    async def handle_bet_input(message: Message, state: FSMContext) -> None:
        if message.from_user is None:
            return

        # Парсим ставку
        raw = (message.text or "").strip().replace(",", ".")
        try:
            bet = Decimal(raw)
            if bet <= 0:
                raise ValueError("ставка <= 0")
        except (InvalidOperation, ValueError):
            await message.answer(POKER_TEXT.INVALID_BET, parse_mode="HTML")
            return

        settings = container.settings
        min_bet = Decimal(settings.game_min_bet)
        max_bet = Decimal(settings.game_max_bet)

        if bet < min_bet:
            await message.answer(
                POKER_TEXT.BET_TOO_LOW.format(min_bet=min_bet, currency=settings.wallet_currency),
                parse_mode="HTML",
            )
            return

        if max_bet > 0 and bet > max_bet:
            await message.answer(
                POKER_TEXT.BET_TOO_HIGH.format(max_bet=max_bet, currency=settings.wallet_currency),
                parse_mode="HTML",
            )
            return

        # Проверяем баланс и списываем ставку
        telegram_id = message.from_user.id
        try:
            await container.user_service.debit(
                telegram_id=telegram_id,
                amount=bet,
                description=f"Покер-дуэль: ставка {bet} {settings.wallet_currency}",
                reference="poker_duel",
            )
        except InsufficientBalanceError as exc:
            await message.answer(
                POKER_TEXT.INSUFFICIENT.format(balance=exc.available, currency=settings.wallet_currency),
                parse_mode="HTML",
            )
            return

        # Разыгрываем дуэль
        outcome = play_duel()

        if outcome.result == PokerResult.WIN:
            # Возвращаем ставку + выигрыш
            winnings = bet * Decimal("2")
            new_balance = await container.user_service.credit(
                telegram_id=telegram_id,
                amount=winnings,
                description=f"Покер-дуэль: выигрыш {winnings} {settings.wallet_currency}",
                reference="poker_duel",
            )
            text = POKER_TEXT.result_win(
                player_card=outcome.player_card,
                bot_card=outcome.bot_card,
                amount=bet,
                new_balance=new_balance,
                currency=settings.wallet_currency,
            )

        elif outcome.result == PokerResult.LOSE:
            profile = await container.user_service.get_profile(telegram_id)
            new_balance = profile.balance if profile else Decimal("0")
            text = POKER_TEXT.result_lose(
                player_card=outcome.player_card,
                bot_card=outcome.bot_card,
                amount=bet,
                new_balance=new_balance,
                currency=settings.wallet_currency,
            )

        else:  # DRAW — возвращаем ставку
            new_balance = await container.user_service.credit(
                telegram_id=telegram_id,
                amount=bet,
                description=f"Покер-дуэль: возврат при ничьей {bet} {settings.wallet_currency}",
                reference="poker_duel",
            )
            text = POKER_TEXT.result_draw(
                player_card=outcome.player_card,
                bot_card=outcome.bot_card,
                currency=settings.wallet_currency,
            )

        await state.clear()
        await message.answer(text, reply_markup=build_game_menu(), parse_mode="HTML")

    return router
