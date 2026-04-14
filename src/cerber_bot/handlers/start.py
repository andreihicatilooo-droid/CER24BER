"""Обработчик команды /start.

Регистрирует пользователя в БД, отправляет START.jpg и inline-меню.
"""

from pathlib import Path

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import FSInputFile, InlineKeyboardMarkup, Message

from cerber_bot.container import AppContainer
from cerber_bot.keyboards.main_menu import build_main_menu
from cerber_bot.texts import START_TEXT


def build_start_router(container: AppContainer) -> Router:
    router = Router(name="start")

    @router.message(CommandStart())
    async def handle_start(message: Message, state: FSMContext) -> None:
        if message.from_user is None:
            await message.answer(START_TEXT.TELEGRAM_USER_NOT_FOUND)
            return

        await state.clear()
        _, created = await container.build_user_service().register_or_update(message.from_user)
        caption = START_TEXT.welcome_caption(created)
        await send_welcome_message(
            message=message,
            image_path=container.settings.start_image_path,
            caption=caption,
            reply_markup=build_main_menu(container.settings),
        )

    return router


async def send_welcome_message(
    message: Message,
    image_path: Path,
    caption: str,
    reply_markup: InlineKeyboardMarkup,
) -> None:
    if image_path.exists():
        await message.answer_photo(
            photo=FSInputFile(image_path),
            caption=caption,
            reply_markup=reply_markup,
        )
        return

    await message.answer(caption, reply_markup=reply_markup)