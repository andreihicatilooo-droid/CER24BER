"""Обработчик команды /start в личных сообщениях CEER Bot.

Регистрирует пользователя в CERBER БД, отправляет главное меню.
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from ceer_bot.container import AppContainer
from ceer_bot.keyboards.main_menu import (
    CEER_BALANCE_ACTION,
    CEER_HOME_ACTION,
    CEER_PROFILE_ACTION,
    CEER_RULES_ACTION,
    build_back_to_menu,
    build_main_menu,
)
from ceer_bot.texts import BALANCE_TEXT, PROFILE_TEXT, RULES_TEXT, START_TEXT


def build_start_router(container: AppContainer) -> Router:
    router = Router(name="ceer_start")

    @router.message(CommandStart(), F.chat.type == "private")
    async def handle_start(message: Message, state: FSMContext) -> None:
        if message.from_user is None:
            await message.answer(START_TEXT.TELEGRAM_USER_NOT_FOUND)
            return

        await state.clear()
        _, created = await container.user_service.register_or_update(message.from_user)
        caption = START_TEXT.welcome_caption(created)
        await message.answer(
            caption,
            reply_markup=build_main_menu(
                container.settings.support_url,
                container.bot_username,
            ),
            parse_mode="HTML",
        )

    @router.callback_query(F.data == CEER_HOME_ACTION)
    async def handle_home(callback: CallbackQuery, state: FSMContext) -> None:
        await state.clear()
        if callback.from_user is None:
            await callback.answer()
            return
        await callback.answer()
        await callback.message.edit_text(  # type: ignore[union-attr]
            text=START_TEXT.BASE_CAPTION,
            reply_markup=build_main_menu(
                container.settings.support_url,
                container.bot_username,
            ),
            parse_mode="HTML",
        )

    @router.callback_query(F.data == CEER_PROFILE_ACTION)
    async def handle_profile(callback: CallbackQuery) -> None:
        await callback.answer()
        if callback.from_user is None:
            return
        profile = await container.user_service.get_profile(callback.from_user.id)
        if profile is None:
            await callback.message.edit_text(PROFILE_TEXT.NO_PROFILE, reply_markup=build_back_to_menu())  # type: ignore[union-attr]
            return
        text = PROFILE_TEXT.format(
            username=profile.username,
            first_name=profile.first_name,
            balance=profile.balance,
            currency=profile.currency,
        )
        await callback.message.edit_text(text, reply_markup=build_back_to_menu(), parse_mode="HTML")  # type: ignore[union-attr]

    @router.callback_query(F.data == CEER_BALANCE_ACTION)
    async def handle_balance(callback: CallbackQuery) -> None:
        await callback.answer()
        if callback.from_user is None:
            return
        profile = await container.user_service.get_profile(callback.from_user.id)
        if profile is None:
            await callback.message.edit_text(BALANCE_TEXT.NO_PROFILE, reply_markup=build_back_to_menu())  # type: ignore[union-attr]
            return
        text = BALANCE_TEXT.format(balance=profile.balance, currency=profile.currency)
        await callback.message.edit_text(text, reply_markup=build_back_to_menu(), parse_mode="HTML")  # type: ignore[union-attr]

    @router.callback_query(F.data == CEER_RULES_ACTION)
    async def handle_rules(callback: CallbackQuery) -> None:
        await callback.answer()
        await callback.message.edit_text(RULES_TEXT.BODY, reply_markup=build_back_to_menu(), parse_mode="HTML")  # type: ignore[union-attr]

    return router
