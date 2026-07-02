"""Обработчик команды /start.

Регистрирует пользователя в БД, отправляет START.jpg и inline-меню.
"""

from pathlib import Path

from aiogram import Router
from aiogram.exceptions import AiogramError
from aiogram.filters import CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import FSInputFile, InlineKeyboardMarkup, Message

from cerber_bot.container import AppContainer
from cerber_bot.keyboards.main_menu import build_main_menu
from cerber_bot.texts import REFERRAL_TEXT, START_TEXT


def build_start_router(container: AppContainer) -> Router:
    router = Router(name="start")

    @router.message(CommandStart())
    async def handle_start(message: Message, state: FSMContext, command: CommandObject | None = None) -> None:
        if message.from_user is None:
            await message.answer(START_TEXT.TELEGRAM_USER_NOT_FOUND)
            return

        await state.clear()
        _, created = await container.user_service.register_or_update(message.from_user)
        caption = START_TEXT.welcome_caption(created)

        payload = command.args if command else None

        # Реферальный deep-link: /start ref_<telegram_id>
        referrer_id = container.referral_service.parse_payload(payload)
        if created and referrer_id is not None:
            applied = await container.referral_service.apply_referral(message.from_user.id, referrer_id)
            if applied:
                caption += REFERRAL_TEXT.WELCOME_BY_REFERRAL
                if message.bot is not None:
                    try:
                        await message.bot.send_message(referrer_id, REFERRAL_TEXT.NEW_REFERRAL_NOTIFICATION)
                    except AiogramError:
                        pass

        # Deep-link на сделку: /start deal_<id> (после принятия инлайн-поста)
        if payload and payload.startswith("deal_"):
            raw_deal_id = payload.removeprefix("deal_")
            if raw_deal_id.isdigit():
                from cerber_bot.handlers.menu import render_deal_view
                from cerber_bot.keyboards.deals import build_deal_detail_keyboard

                deal = await container.deal_service.get_deal_view(message.from_user.id, int(raw_deal_id))
                if deal is not None:
                    await message.answer(render_deal_view(deal), reply_markup=build_deal_detail_keyboard(deal))
                    return
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
