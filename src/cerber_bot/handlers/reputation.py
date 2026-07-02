"""Обработчик раздела репутации пользователя."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from cerber_bot.container import AppContainer
from cerber_bot.keyboards.main_menu import REPUTATION_ACTION, build_main_menu
from cerber_bot.texts import MENU_TEXT


def build_reputation_router(container: AppContainer) -> Router:
    router = Router(name="reputation")

    @router.callback_query(F.data == REPUTATION_ACTION)
    async def handle_reputation(callback: CallbackQuery, state: FSMContext) -> None:
        message = extract_message(callback)
        if message is None or callback.from_user is None:
            await callback.answer()
            return

        await state.clear()
        profile = await container.user_service.get_profile(callback.from_user.id)
        if profile is None:
            await message.answer(MENU_TEXT.PROFILE_NOT_FOUND)
            await callback.answer()
            return

        reputation = await container.reputation_service.get_user_reputation(callback.from_user.id)
        deals_dashboard = await container.deal_service.get_dashboard(callback.from_user.id)
        await message.answer(
            render_reputation(profile.telegram_id, reputation.score, reputation.dispute_losses, deals_dashboard.statistics.completed_deals),
            reply_markup=build_main_menu(container.settings),
        )
        await callback.answer(MENU_TEXT.REPUTATION_OPENED)

    return router


def extract_message(callback: CallbackQuery) -> Message | None:
    if isinstance(callback.message, Message):
        return callback.message
    return None


def render_reputation(telegram_id: int, score: int, dispute_losses: int, completed_deals: int) -> str:
    return "\n".join(
        [
            MENU_TEXT.REPUTATION_TITLE,
            MENU_TEXT.PROFILE_TELEGRAM_ID.format(telegram_id=telegram_id),
            MENU_TEXT.REPUTATION_SCORE.format(score=score),
            MENU_TEXT.REPUTATION_LOSSES.format(count=dispute_losses),
            MENU_TEXT.REPUTATION_DEALS.format(count=completed_deals),
            MENU_TEXT.REPUTATION_HINT,
        ]
    )