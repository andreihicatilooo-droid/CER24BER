"""Обработчики профиля, каталога, гарант-сделок и вывода USDT.

Объединяет build_menu_router (профиль, обновление каталога, поддержка)
и build_deals_router (весь escrow/withdrawal workflow).
"""

import logging
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from html import escape

from aiogram import F, Router
from aiogram.exceptions import AiogramError, TelegramBadRequest, TelegramNetworkError
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from cerber_bot.container import AppContainer
from cerber_bot.db.models import TelegramUser
from cerber_bot.integrations.giftapi import GiftApiError
from cerber_bot.keyboards.deals import (
    DEAL_ACCEPT_PREFIX,
    DEAL_CANCEL_PREFIX,
    DEAL_DECLINE_PREFIX,
    DEAL_DISPUTE_PREFIX,
    DEAL_HOME_ACTION,
    DEAL_LIST_ACTION,
    DEAL_MESSAGE_PREFIX,
    DEAL_MODERATION_PREFIX,
    DEAL_MODERATOR_PREFIX,
    DEAL_NEW_ACTION,
    DEAL_OPEN_PREFIX,
    DEAL_PAGE_PREFIX,
    DEAL_SUCCESS_PREFIX,
    DEAL_WITHDRAW_ACTION,
    DEAL_WITHDRAW_CANCEL_PREFIX,
    DEAL_WITHDRAW_MODERATION_PREFIX,
    DEAL_WITHDRAW_NETWORK_PREFIX,
    build_deal_detail_keyboard,
    build_deal_home_keyboard,
    build_deal_invite_keyboard,
    build_deal_open_keyboard,
    build_deals_keyboard,
    build_moderator_deal_keyboard,
    build_moderator_withdrawal_keyboard,
    build_withdrawal_network_keyboard,
)
from cerber_bot.keyboards.main_menu import MAIN_MENU_ACTION, PROFILE_ACTION, REFRESH_ACTION, SUPPORT_ACTION, FAQ_ACTION, FAQ_SECTION_PREFIX, build_faq_keyboard, build_faq_back_keyboard, build_main_menu
from cerber_bot.services.deals import DealCard, DealDashboard, DealMessageRelayResult, DealModerationResult, DealServiceError, DealView, WithdrawalRequestView
from cerber_bot.services.store import PageInfo, StoreServiceError, format_money
from cerber_bot.texts import DEAL_HANDLER_TEXT, FAQ_TEXT, MENU_TEXT


logger = logging.getLogger(__name__)



def build_menu_router(container: AppContainer) -> Router:
    router = Router(name="menu")

    @router.callback_query(F.data == MAIN_MENU_ACTION)
    async def handle_main_menu(callback: CallbackQuery, state: FSMContext) -> None:
        message = extract_message(callback)
        if message is None:
            await callback.answer()
            return

        await state.clear()
        await message.answer(
            MENU_TEXT.MAIN_MENU_TITLE,
            reply_markup=build_main_menu(container.settings),
        )
        await callback.answer()

    @router.callback_query(F.data == PROFILE_ACTION)
    async def handle_profile(callback: CallbackQuery, state: FSMContext) -> None:
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

        wallet = await container.store_service.get_wallet_snapshot(callback.from_user.id)
        deals_dashboard = await container.deal_service.get_dashboard(callback.from_user.id)
        await message.answer(
            render_profile(profile, wallet, deals_dashboard),
        )
        await callback.answer(MENU_TEXT.PROFILE_OPENED)

    @router.callback_query(F.data == REFRESH_ACTION)
    async def handle_refresh(callback: CallbackQuery, state: FSMContext) -> None:
        message = extract_message(callback)
        if message is None:
            await answer_callback_safely(callback)
            return

        await answer_callback_safely(callback, MENU_TEXT.CATALOG_REFRESHING)
        await state.clear()
        try:
            snapshot = await container.store_service.refresh_catalog()
        except GiftApiError as error:
            await message.answer(MENU_TEXT.catalog_not_refreshed(escape(str(error))))
            return
        await message.answer(render_refresh_report(len(snapshot.categories), len(snapshot.products)))

    @router.callback_query(F.data == SUPPORT_ACTION)
    async def handle_support(callback: CallbackQuery, state: FSMContext) -> None:
        message = extract_message(callback)
        if message is None:
            await callback.answer()
            return

        await state.clear()
        support_url = container.settings.support_url or MENU_TEXT.SUPPORT_CONTACT_MISSING
        await message.answer(MENU_TEXT.support_contact(escape(support_url)))
        await callback.answer(MENU_TEXT.CONTACTS_SENT)

    @router.callback_query(F.data == FAQ_ACTION)
    async def handle_faq(callback: CallbackQuery, state: FSMContext) -> None:
        message = extract_message(callback)
        if message is None:
            await callback.answer()
            return

        await state.clear()
        await message.answer(FAQ_TEXT.TITLE, reply_markup=build_faq_keyboard())
        await callback.answer()

    _FAQ_SECTIONS: dict[str, str] = {
        "store": FAQ_TEXT.STORE,
        "wallet": FAQ_TEXT.WALLET,
        "deals": FAQ_TEXT.DEALS,
        "security": FAQ_TEXT.SECURITY,
    }

    @router.callback_query(F.data.startswith(FAQ_SECTION_PREFIX))
    async def handle_faq_section(callback: CallbackQuery, state: FSMContext) -> None:
        message = extract_message(callback)
        if message is None:
            await callback.answer()
            return

        section = callback.data[len(FAQ_SECTION_PREFIX):]  # type: ignore[index]
        text = _FAQ_SECTIONS.get(section)
        if text is None:
            await callback.answer()
            return

        await message.answer(text, reply_markup=build_faq_back_keyboard())
        await callback.answer()

    return router


def extract_message(callback: CallbackQuery) -> Message | None:
    if isinstance(callback.message, Message):
        return callback.message
    return None


async def answer_callback_safely(callback: CallbackQuery, text: str | None = None) -> None:
    try:
        if text is None:
            await callback.answer()
        else:
            await callback.answer(text)
    except TelegramBadRequest as error:
        lowered = str(error).lower()
        if "query is too old" not in lowered and "query id is invalid" not in lowered:
            raise
        logger.warning("Skipped expired callback answer for %s", callback.data)


def render_profile(profile: TelegramUser, wallet, deals_dashboard) -> str:
    created_at = profile.created_at.astimezone(timezone.utc).strftime("%d.%m.%Y %H:%M UTC")
    last_seen = profile.last_seen_at.astimezone(timezone.utc).strftime("%d.%m.%Y %H:%M UTC")
    username = f"@{profile.username}" if profile.username else MENU_TEXT.PROFILE_USERNAME_UNKNOWN
    stats = deals_dashboard.statistics

    return "\n".join(
        [
            MENU_TEXT.PROFILE_TITLE,
            MENU_TEXT.PROFILE_TELEGRAM_ID.format(telegram_id=profile.telegram_id),
            MENU_TEXT.PROFILE_USERNAME.format(username=escape(username)),
            MENU_TEXT.PROFILE_FIRST_NAME.format(first_name=escape(profile.first_name or MENU_TEXT.PROFILE_FIRST_NAME_UNKNOWN)),
            MENU_TEXT.PROFILE_LAST_NAME.format(last_name=escape(profile.last_name or MENU_TEXT.PROFILE_LAST_NAME_UNKNOWN)),
            MENU_TEXT.PROFILE_LANGUAGE.format(language=escape(profile.language_code or MENU_TEXT.PROFILE_LANGUAGE_UNKNOWN)),
            MENU_TEXT.PROFILE_AVAILABLE.format(amount=escape(format_profile_money(wallet.balance, wallet.currency))),
            MENU_TEXT.PROFILE_HELD.format(amount=escape(format_profile_money(wallet.held_balance, wallet.currency))),
            MENU_TEXT.PROFILE_TOTAL.format(amount=escape(format_profile_money(wallet.total_balance, wallet.currency))),
            MENU_TEXT.PROFILE_EQUIVALENT.format(
                usdt_amount=escape(format_profile_money(wallet.total_quote.usdt_amount, 'USDT')),
                rub_amount=escape(format_profile_money(wallet.total_quote.rub_amount, 'RUB')),
            ),
            MENU_TEXT.PROFILE_ORDER_COUNT.format(count=wallet.order_count),
            MENU_TEXT.PROFILE_TOTAL_DEALS.format(count=stats.total_deals),
            MENU_TEXT.PROFILE_OPEN_DEALS.format(count=stats.open_deals),
            MENU_TEXT.PROFILE_DEALS_VOLUME.format(amount=escape(format_profile_money(stats.total_volume, stats.currency))),
            MENU_TEXT.PROFILE_PENDING_WITHDRAWALS.format(count=stats.pending_withdrawals),
            MENU_TEXT.PROFILE_CREATED.format(created_at=created_at),
            MENU_TEXT.PROFILE_LAST_SEEN.format(last_seen=last_seen),
        ]
    )


def render_refresh_report(category_count: int, product_count: int) -> str:
    return "\n".join(
        [
            MENU_TEXT.REFRESH_REPORT_TITLE,
            MENU_TEXT.REFRESH_REPORT_CATEGORIES.format(count=category_count),
            MENU_TEXT.REFRESH_REPORT_PRODUCTS.format(count=product_count),
            MENU_TEXT.REFRESH_REPORT_HINT,
        ]
    )


def format_profile_money(amount, currency: str) -> str:
    value = str(amount.quantize(amount.__class__("0.01")) if hasattr(amount, "quantize") else amount)
    if "." in value:
        value = value.rstrip("0").rstrip(".")
    return f"{value} {currency}"



def shorten_text(value: str, limit: int = 120) -> str:
    normalized = " ".join(value.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 1].rstrip() + "…"


class DealStates(StatesGroup):
    waiting_for_partner = State()
    waiting_for_amount = State()
    waiting_for_terms = State()
    waiting_for_chat_message = State()
    waiting_for_withdrawal_amount = State()
    waiting_for_withdrawal_address = State()


DEALS_PER_PAGE = 6


def build_deals_router(container: AppContainer) -> Router:
    router = Router(name="deals")

    @router.callback_query(F.data == DEAL_HOME_ACTION)
    async def handle_deal_home(callback: CallbackQuery, state: FSMContext) -> None:
        message = extract_message(callback)
        if message is None or callback.from_user is None:
            await callback.answer()
            return

        await container.user_service.register_or_update(callback.from_user)
        await state.set_state(None)
        await render_deal_dashboard_screen(message, state, container, telegram_id=callback.from_user.id, callback=callback)
        await callback.answer(DEAL_HANDLER_TEXT.CALLBACK_MENU)

    @router.callback_query(F.data == DEAL_NEW_ACTION)
    async def handle_new_deal_prompt(callback: CallbackQuery, state: FSMContext) -> None:
        message = extract_message(callback)
        if message is None:
            await callback.answer()
            return

        await state.clear()
        await state.set_state(DealStates.waiting_for_partner)
        await message.answer(
            DEAL_HANDLER_TEXT.NEW_DEAL_PARTNER_PROMPT,
            reply_markup=build_deal_home_keyboard(),
        )
        await callback.answer(DEAL_HANDLER_TEXT.CALLBACK_WAIT_USER)

    @router.message(DealStates.waiting_for_partner)
    async def handle_new_deal_partner(message: Message, state: FSMContext) -> None:
        if should_cancel(message.text):
            await cancel_state_flow(message, state)
            return

        partner_identifier = (message.text or "").strip()
        if not partner_identifier:
            await message.answer(DEAL_HANDLER_TEXT.ENTER_PARTNER)
            return

        await state.update_data(deal_partner_identifier=partner_identifier)
        await state.set_state(DealStates.waiting_for_amount)
        await message.answer(DEAL_HANDLER_TEXT.ENTER_DEAL_AMOUNT)

    @router.message(DealStates.waiting_for_amount)
    async def handle_new_deal_amount(message: Message, state: FSMContext) -> None:
        if should_cancel(message.text):
            await cancel_state_flow(message, state)
            return

        try:
            amount = parse_deal_decimal(message.text or "")
        except ValueError as error:
            await message.answer(str(error))
            return

        await state.update_data(deal_amount=str(amount))
        await state.set_state(DealStates.waiting_for_terms)
        await message.answer(DEAL_HANDLER_TEXT.ENTER_DEAL_TERMS)

    @router.message(DealStates.waiting_for_terms)
    async def handle_new_deal_terms(message: Message, state: FSMContext) -> None:
        if message.from_user is None:
            return
        if should_cancel(message.text):
            await cancel_state_flow(message, state)
            return

        data = await state.get_data()
        partner_identifier = str(data.get("deal_partner_identifier") or "").strip()
        amount = parse_deal_decimal(str(data.get("deal_amount") or "0"))
        terms = (message.text or "").strip()

        try:
            result = await container.deal_service.create_deal_request(
                message.from_user,
                seller_identifier=partner_identifier,
                amount=amount,
                terms=terms,
            )
        except DealServiceError as error:
            await message.answer(render_deal_error(error), reply_markup=build_deal_home_keyboard())
            return

        await state.clear()
        await message.answer(render_deal_view(result.deal), reply_markup=build_deal_detail_keyboard(result.deal))
        await notify_user_safe(
            message.bot,
            result.counterparty.telegram_id,
            render_deal_invitation(result.deal),
            reply_markup=build_deal_invite_keyboard(result.deal.deal_id),
        )

    @router.callback_query(F.data == DEAL_LIST_ACTION)
    async def handle_deal_list(callback: CallbackQuery, state: FSMContext) -> None:
        message = extract_message(callback)
        if message is None or callback.from_user is None:
            await callback.answer()
            return

        await state.set_state(None)
        await render_deals_page_screen(message, state, container, telegram_id=callback.from_user.id, page=1, callback=callback)
        await callback.answer(DEAL_HANDLER_TEXT.CALLBACK_MY_DEALS)

    @router.callback_query(F.data.startswith(DEAL_PAGE_PREFIX))
    async def handle_deal_list_page(callback: CallbackQuery, state: FSMContext) -> None:
        message = extract_message(callback)
        if message is None or callback.from_user is None:
            await callback.answer()
            return

        page = parse_int_suffix(callback.data or "", DEAL_PAGE_PREFIX, 1)
        await state.set_state(None)
        await render_deals_page_screen(message, state, container, telegram_id=callback.from_user.id, page=page, callback=callback)
        await callback.answer()

    @router.callback_query(F.data.startswith(DEAL_OPEN_PREFIX))
    async def handle_open_deal(callback: CallbackQuery, state: FSMContext) -> None:
        message = extract_message(callback)
        if message is None or callback.from_user is None:
            await callback.answer()
            return

        deal_id = parse_int_suffix(callback.data or "", DEAL_OPEN_PREFIX)
        deal = await container.deal_service.get_deal_view(callback.from_user.id, deal_id)
        if deal is None:
            await callback.answer(DEAL_HANDLER_TEXT.CALLBACK_DEAL_UNAVAILABLE)
            return

        await state.set_state(None)
        await send_screen(message, render_deal_view(deal), build_deal_detail_keyboard(deal), callback=callback)
        await callback.answer(DEAL_HANDLER_TEXT.CALLBACK_DEAL_OPENED)

    @router.callback_query(F.data.startswith(DEAL_ACCEPT_PREFIX))
    async def handle_accept_deal(callback: CallbackQuery, state: FSMContext) -> None:
        message = extract_message(callback)
        if message is None or callback.from_user is None:
            await callback.answer()
            return

        deal_id = parse_int_suffix(callback.data or "", DEAL_ACCEPT_PREFIX)
        try:
            result = await container.deal_service.accept_deal(callback.from_user.id, deal_id)
        except DealServiceError as error:
            await send_screen(message, render_deal_error(error), build_deal_home_keyboard(), callback=callback)
            await callback.answer(DEAL_HANDLER_TEXT.CALLBACK_ACCEPT_FAILED)
            return

        await state.set_state(None)
        await send_screen(message, render_deal_view(result.deal), build_deal_detail_keyboard(result.deal), callback=callback)
        if result.counterparty_id is not None:
            await notify_user_safe(
                callback.bot,
                result.counterparty_id,
                render_deal_status_notification(result.deal, DEAL_HANDLER_TEXT.DEAL_ACCEPTED_NOTIFICATION),
                reply_markup=build_deal_open_keyboard(result.deal.deal_id),
            )
        await callback.answer(DEAL_HANDLER_TEXT.CALLBACK_DEAL_ACCEPTED)

    @router.callback_query(F.data.startswith(DEAL_DECLINE_PREFIX))
    async def handle_decline_deal(callback: CallbackQuery, state: FSMContext) -> None:
        await handle_close_pending_deal(callback, state, container, DEAL_DECLINE_PREFIX)

    @router.callback_query(F.data.startswith(DEAL_CANCEL_PREFIX))
    async def handle_cancel_deal(callback: CallbackQuery, state: FSMContext) -> None:
        await handle_close_pending_deal(callback, state, container, DEAL_CANCEL_PREFIX)

    @router.callback_query(F.data.startswith(DEAL_MESSAGE_PREFIX))
    async def handle_deal_message_prompt(callback: CallbackQuery, state: FSMContext) -> None:
        message = extract_message(callback)
        if message is None:
            await callback.answer()
            return

        deal_id = parse_int_suffix(callback.data or "", DEAL_MESSAGE_PREFIX)
        await state.update_data(chat_deal_id=deal_id)
        await state.set_state(DealStates.waiting_for_chat_message)
        await message.answer(
            DEAL_HANDLER_TEXT.CHAT_PROMPT,
            reply_markup=build_deal_open_keyboard(deal_id),
        )
        await callback.answer(DEAL_HANDLER_TEXT.CALLBACK_WAIT_MESSAGE)

    @router.message(DealStates.waiting_for_chat_message)
    async def handle_deal_chat_message(message: Message, state: FSMContext) -> None:
        if message.from_user is None:
            return

        data = await state.get_data()
        deal_id = int(data.get("chat_deal_id", 0))
        if should_cancel(message.text):
            await state.clear()
            if deal_id:
                deal = await container.deal_service.get_deal_view(message.from_user.id, deal_id)
                if deal is not None:
                    await message.answer(render_deal_view(deal), reply_markup=build_deal_detail_keyboard(deal))
                    return
            await message.answer(DEAL_HANDLER_TEXT.CHAT_CANCELED, reply_markup=build_deal_home_keyboard())
            return

        if not deal_id:
            await state.clear()
            await message.answer(DEAL_HANDLER_TEXT.DEAL_CONTEXT_LOST, reply_markup=build_deal_home_keyboard())
            return

        content_type, summary = summarize_user_message(message)

        # Для фото — загружаем на nbox.me ДО сохранения в БД,
        # чтобы ссылка попала в тело сообщения и историю чата сделки.
        nbox_url: str | None = None
        if content_type == "photo" and message.photo and message.bot is not None:
            photo_size = message.photo[-1]
            bio = await message.bot.download(photo_size)
            if bio is not None:
                filename = f"deal_{deal_id}_{photo_size.file_id[:8]}.jpg"
                nbox_url = await container.nbox_service.upload_photo(bio, filename=filename)

        # Если nbox загрузил фото — используем ссылку как тело; иначе — описание
        body = nbox_url if nbox_url else summary

        try:
            relay = await container.deal_service.record_chat_message(
                message.from_user.id,
                deal_id=deal_id,
                content_type=content_type,
                body=body,
            )
        except DealServiceError as error:
            await message.answer(render_deal_error(error), reply_markup=build_deal_open_keyboard(deal_id))
            return

        await state.clear()

        notification_text = render_deal_message_notification(relay, nbox_url=nbox_url)
        await notify_user_safe(
            message.bot,
            relay.recipient_id,
            notification_text,
            reply_markup=build_deal_open_keyboard(deal_id),
        )
        # Пересылаем вложение только если nbox не загрузил фото
        if nbox_url is None:
            try:
                await message.copy_to(relay.recipient_id)
            except (TelegramBadRequest, TelegramNetworkError):
                await notify_user_safe(
                    message.bot,
                    relay.recipient_id,
                    DEAL_HANDLER_TEXT.attachment_forward_failed(escape(relay.preview)),
                    reply_markup=build_deal_open_keyboard(deal_id),
                )
        await message.answer(render_deal_view(relay.deal), reply_markup=build_deal_detail_keyboard(relay.deal))

    @router.callback_query(F.data.startswith(DEAL_SUCCESS_PREFIX))
    async def handle_deal_success(callback: CallbackQuery, state: FSMContext) -> None:
        message = extract_message(callback)
        if message is None or callback.from_user is None:
            await callback.answer()
            return

        deal_id = parse_int_suffix(callback.data or "", DEAL_SUCCESS_PREFIX)
        try:
            result = await container.deal_service.confirm_success(callback.from_user.id, deal_id)
        except DealServiceError as error:
            await send_screen(message, render_deal_error(error), build_deal_home_keyboard(), callback=callback)
            await callback.answer(DEAL_HANDLER_TEXT.CALLBACK_COMPLETE_FAILED)
            return

        await state.set_state(None)
        await send_screen(message, render_deal_view(result.deal), build_deal_detail_keyboard(result.deal), callback=callback)
        if result.counterparty_id is not None:
            await notify_user_safe(
                callback.bot,
                result.counterparty_id,
                render_deal_status_notification(result.deal, DEAL_HANDLER_TEXT.DEAL_COMPLETED_NOTIFICATION),
                reply_markup=build_deal_open_keyboard(result.deal.deal_id),
            )
        await callback.answer(DEAL_HANDLER_TEXT.CALLBACK_DEAL_COMPLETED)

    @router.callback_query(F.data.startswith(DEAL_DISPUTE_PREFIX))
    async def handle_open_dispute(callback: CallbackQuery, state: FSMContext) -> None:
        message = extract_message(callback)
        if message is None or callback.from_user is None:
            await callback.answer()
            return

        deal_id = parse_int_suffix(callback.data or "", DEAL_DISPUTE_PREFIX)
        try:
            result = await container.deal_service.open_dispute(callback.from_user.id, deal_id)
        except DealServiceError as error:
            await send_screen(message, render_deal_error(error), build_deal_home_keyboard(), callback=callback)
            await callback.answer(DEAL_HANDLER_TEXT.CALLBACK_DISPUTE_FAILED)
            return

        await state.set_state(None)
        await send_screen(message, render_deal_view(result.deal), build_deal_detail_keyboard(result.deal), callback=callback)
        if result.counterparty_id is not None:
            await notify_user_safe(
                callback.bot,
                result.counterparty_id,
                render_deal_status_notification(result.deal, DEAL_HANDLER_TEXT.DISPUTE_OPENED_NOTIFICATION),
                reply_markup=build_deal_open_keyboard(result.deal.deal_id),
            )
        await notify_moderators_about_deal(callback.bot, container, result.deal, reason=DEAL_HANDLER_TEXT.MODERATOR_REASON_DISPUTE)
        await maybe_warn_about_missing_moderators(message, container)
        await callback.answer(DEAL_HANDLER_TEXT.CALLBACK_DISPUTE_OPENED)

    @router.callback_query(F.data.startswith(DEAL_MODERATOR_PREFIX))
    async def handle_request_moderator(callback: CallbackQuery, state: FSMContext) -> None:
        message = extract_message(callback)
        if message is None or callback.from_user is None:
            await callback.answer()
            return

        deal_id = parse_int_suffix(callback.data or "", DEAL_MODERATOR_PREFIX)
        try:
            result = await container.deal_service.request_moderator(callback.from_user.id, deal_id)
        except DealServiceError as error:
            await send_screen(message, render_deal_error(error), build_deal_home_keyboard(), callback=callback)
            await callback.answer(DEAL_HANDLER_TEXT.CALLBACK_MODERATOR_FAILED)
            return

        await state.set_state(None)
        await send_screen(message, render_deal_view(result.deal), build_deal_detail_keyboard(result.deal), callback=callback)
        if result.counterparty_id is not None:
            await notify_user_safe(
                callback.bot,
                result.counterparty_id,
                render_deal_status_notification(result.deal, DEAL_HANDLER_TEXT.MODERATOR_REQUESTED_NOTIFICATION),
                reply_markup=build_deal_open_keyboard(result.deal.deal_id),
            )
        await notify_moderators_about_deal(callback.bot, container, result.deal, reason=DEAL_HANDLER_TEXT.MODERATOR_REASON_REQUESTED)
        await maybe_warn_about_missing_moderators(message, container)
        await callback.answer(DEAL_HANDLER_TEXT.CALLBACK_MODERATOR_REQUESTED)

    @router.callback_query(F.data.startswith(DEAL_MODERATION_PREFIX))
    async def handle_moderation(callback: CallbackQuery) -> None:
        message = extract_message(callback)
        if message is None or callback.from_user is None:
            await callback.answer()
            return

        try:
            deal_id, resolution = parse_action_suffix(callback.data or "", DEAL_MODERATION_PREFIX)
            result = await container.deal_service.resolve_dispute(callback.from_user.id, deal_id, resolution)
        except DealServiceError as error:
            await send_screen(message, render_deal_error(error), build_deal_home_keyboard(), callback=callback)
            await callback.answer(DEAL_HANDLER_TEXT.CALLBACK_MODERATION_FAILED)
            return

        await send_screen(message, render_moderation_result(result), build_deal_home_keyboard(), callback=callback)
        await notify_user_safe(
            callback.bot,
            result.buyer_telegram_id,
            render_moderation_result_notification(result),
            reply_markup=build_deal_open_keyboard(result.deal_id),
        )
        await notify_user_safe(
            callback.bot,
            result.seller_telegram_id,
            render_moderation_result_notification(result),
            reply_markup=build_deal_open_keyboard(result.deal_id),
        )
        await callback.answer(DEAL_HANDLER_TEXT.CALLBACK_MODERATION_APPLIED)

    @router.callback_query(F.data == DEAL_WITHDRAW_ACTION)
    async def handle_withdraw_prompt(callback: CallbackQuery, state: FSMContext) -> None:
        message = extract_message(callback)
        if message is None:
            await callback.answer()
            return

        await state.clear()
        await state.set_state(DealStates.waiting_for_withdrawal_amount)
        await message.answer(
            DEAL_HANDLER_TEXT.WITHDRAW_PROMPT,
            reply_markup=build_deal_home_keyboard(),
        )
        await callback.answer(DEAL_HANDLER_TEXT.CALLBACK_WAIT_AMOUNT)

    @router.message(DealStates.waiting_for_withdrawal_amount)
    async def handle_withdraw_amount(message: Message, state: FSMContext) -> None:
        if should_cancel(message.text):
            await cancel_state_flow(message, state)
            return

        try:
            amount = parse_deal_decimal(message.text or "")
        except ValueError as error:
            await message.answer(str(error))
            return

        await state.update_data(withdraw_amount_usdt=str(amount))
        await state.set_state(None)
        await message.answer(
            DEAL_HANDLER_TEXT.WITHDRAW_NETWORK_PROMPT,
            reply_markup=build_withdrawal_network_keyboard(container.deal_service.withdrawal_networks),
        )

    @router.callback_query(F.data.startswith(DEAL_WITHDRAW_NETWORK_PREFIX))
    async def handle_withdraw_network(callback: CallbackQuery, state: FSMContext) -> None:
        message = extract_message(callback)
        if message is None:
            await callback.answer()
            return

        data = await state.get_data()
        amount_text = str(data.get("withdraw_amount_usdt") or "").strip()
        if not amount_text:
            await callback.answer(DEAL_HANDLER_TEXT.CALLBACK_ENTER_WITHDRAW_AMOUNT_FIRST)
            return

        network = (callback.data or "").removeprefix(DEAL_WITHDRAW_NETWORK_PREFIX)
        await state.update_data(withdraw_network=network)
        await state.set_state(DealStates.waiting_for_withdrawal_address)
        await message.answer(
            DEAL_HANDLER_TEXT.withdraw_address_prompt(escape(network)),
            reply_markup=build_deal_home_keyboard(),
        )
        await callback.answer(DEAL_HANDLER_TEXT.CALLBACK_WAIT_ADDRESS)

    @router.message(DealStates.waiting_for_withdrawal_address)
    async def handle_withdraw_address(message: Message, state: FSMContext) -> None:
        if message.from_user is None:
            return
        if should_cancel(message.text):
            await cancel_state_flow(message, state)
            return

        data = await state.get_data()
        amount = parse_deal_decimal(str(data.get("withdraw_amount_usdt") or "0"))
        network = str(data.get("withdraw_network") or "").strip().upper()
        address = (message.text or "").strip()
        try:
            result = await container.deal_service.create_withdrawal_request(
                message.from_user,
                amount_usdt=amount,
                network=network,
                address=address,
            )
        except DealServiceError as error:
            await message.answer(render_deal_error(error), reply_markup=build_deal_home_keyboard())
            return

        await state.clear()
        await message.answer(
            render_withdrawal_request(result.request),
            reply_markup=build_deal_home_keyboard(open_withdrawal_request_id=result.request.request_id),
        )
        await notify_moderators_about_withdrawal(bot=message.bot, container=container, request=result.request)
        await maybe_warn_about_missing_moderators(message, container)

    @router.callback_query(F.data.startswith(DEAL_WITHDRAW_CANCEL_PREFIX))
    async def handle_withdraw_cancel(callback: CallbackQuery, state: FSMContext) -> None:
        message = extract_message(callback)
        if message is None or callback.from_user is None:
            await callback.answer()
            return

        request_id = parse_int_suffix(callback.data or "", DEAL_WITHDRAW_CANCEL_PREFIX)
        try:
            await container.deal_service.cancel_withdrawal_request(callback.from_user.id, request_id)
        except DealServiceError as error:
            await send_screen(message, render_deal_error(error), build_deal_home_keyboard(), callback=callback)
            await callback.answer(DEAL_HANDLER_TEXT.CALLBACK_WITHDRAW_CANCEL_FAILED)
            return

        await state.set_state(None)
        await render_deal_dashboard_screen(message, state, container, telegram_id=callback.from_user.id, callback=callback)
        await callback.answer(DEAL_HANDLER_TEXT.CALLBACK_WITHDRAW_CANCELED)

    @router.callback_query(F.data.startswith(DEAL_WITHDRAW_MODERATION_PREFIX))
    async def handle_withdraw_moderation(callback: CallbackQuery) -> None:
        message = extract_message(callback)
        if message is None or callback.from_user is None:
            await callback.answer()
            return

        try:
            request_id, action = parse_action_suffix(callback.data or "", DEAL_WITHDRAW_MODERATION_PREFIX)
            result = await container.deal_service.moderate_withdrawal_request(callback.from_user.id, request_id, action)
        except DealServiceError as error:
            await send_screen(message, render_deal_error(error), build_deal_home_keyboard(), callback=callback)
            await callback.answer(DEAL_HANDLER_TEXT.CALLBACK_WITHDRAW_PROCESS_FAILED)
            return

        await send_screen(message, render_withdrawal_request(result.request), build_deal_home_keyboard(), callback=callback)
        await notify_user_safe(
            callback.bot,
            result.owner_telegram_id,
            render_withdrawal_status_notification(result.request),
            reply_markup=build_deal_home_keyboard(),
        )
        await callback.answer(DEAL_HANDLER_TEXT.CALLBACK_WITHDRAW_PROCESSED)

    return router


async def handle_close_pending_deal(callback: CallbackQuery, state: FSMContext, container: AppContainer, prefix: str) -> None:
    message = extract_message(callback)
    if message is None or callback.from_user is None:
        await callback.answer()
        return

    deal_id = parse_int_suffix(callback.data or "", prefix)
    try:
        result = await container.deal_service.decline_deal(callback.from_user.id, deal_id)
    except DealServiceError as error:
        await send_screen(message, render_deal_error(error), build_deal_home_keyboard(), callback=callback)
        await callback.answer(DEAL_HANDLER_TEXT.CALLBACK_CLOSE_FAILED)
        return

    await state.set_state(None)
    await send_screen(message, render_deal_view(result.deal), build_deal_detail_keyboard(result.deal), callback=callback)
    if result.counterparty_id is not None:
        await notify_user_safe(
            callback.bot,
            result.counterparty_id,
            render_deal_status_notification(result.deal, DEAL_HANDLER_TEXT.DEAL_CLOSED_NOTIFICATION),
            reply_markup=build_deal_open_keyboard(result.deal.deal_id),
        )
    await callback.answer(DEAL_HANDLER_TEXT.CALLBACK_STATUS_UPDATED)


async def render_deal_dashboard_screen(
    message: Message,
    state: FSMContext,
    container: AppContainer,
    *,
    telegram_id: int,
    callback: CallbackQuery | None = None,
) -> None:
    dashboard = await container.deal_service.get_dashboard(telegram_id)
    await state.update_data(current_view_type="deals_home")
    await send_screen(
        message,
        render_deal_dashboard(dashboard, container),
        build_deal_home_keyboard(open_withdrawal_request_id=dashboard.open_withdrawal.request_id if dashboard.open_withdrawal else None),
        callback=callback,
    )


async def render_deals_page_screen(
    message: Message,
    state: FSMContext,
    container: AppContainer,
    *,
    telegram_id: int,
    page: int,
    callback: CallbackQuery | None = None,
) -> None:
    cards, page_info = await container.deal_service.get_deals_page(telegram_id, page=page, per_page=DEALS_PER_PAGE)
    await state.update_data(current_view_type="deals_list", deals_page=page_info.page)
    await send_screen(message, render_deals_page(cards, page_info), build_deals_keyboard(cards, page_info), callback=callback)


async def send_screen(
    message: Message,
    text: str,
    reply_markup: InlineKeyboardMarkup,
    *,
    callback: CallbackQuery | None = None,
) -> None:
    if callback is not None and isinstance(callback.message, Message) and callback.message.text:
        try:
            await callback.message.edit_text(text, reply_markup=reply_markup)
            return
        except TelegramBadRequest:
            pass
    await message.answer(text, reply_markup=reply_markup)


async def notify_user_safe(bot, telegram_id: int, text: str, reply_markup: InlineKeyboardMarkup) -> None:
    try:
        await bot.send_message(telegram_id, text, parse_mode="HTML", reply_markup=reply_markup)
    except AiogramError:
        return


async def notify_moderators_about_deal(bot, container: AppContainer, deal: DealView, *, reason: str) -> None:
    if not container.deal_service.has_moderators:
        return
    text = render_moderator_deal_alert(deal, reason)
    if container.settings.admin_bot_token:
        await container.admin_event_service.enqueue_deal_alert(
            text=text,
            deal_id=deal.deal_id,
            disputed=deal.status == "disputed",
        )
        return
    markup = build_moderator_deal_keyboard(deal.deal_id) if deal.status == "disputed" else build_deal_home_keyboard()
    for moderator_id in container.deal_service.moderator_ids:
        await notify_user_safe(bot, moderator_id, text, reply_markup=markup)


async def notify_moderators_about_withdrawal(*, bot, container: AppContainer, request: WithdrawalRequestView) -> None:
    if not container.deal_service.has_moderators:
        return
    text = render_moderator_withdrawal_alert(request)
    if container.settings.admin_bot_token:
        await container.admin_event_service.enqueue_withdrawal_alert(
            text=text,
            request_id=request.request_id,
        )
        return
    for moderator_id in container.deal_service.moderator_ids:
        await notify_user_safe(bot, moderator_id, text, reply_markup=build_moderator_withdrawal_keyboard(request.request_id))


async def maybe_warn_about_missing_moderators(message: Message, container: AppContainer) -> None:
    if container.deal_service.has_moderators:
        return
    support = container.settings.support_url or MENU_TEXT.SUPPORT_CONTACT_MISSING
    await message.answer(DEAL_HANDLER_TEXT.missing_moderators(escape(support)))


def render_deal_dashboard(dashboard: DealDashboard, container: AppContainer) -> str:
    balance = dashboard.balance
    stats = dashboard.statistics
    lines = [DEAL_HANDLER_TEXT.DASHBOARD_TITLE]
    lines.append(DEAL_HANDLER_TEXT.DASHBOARD_AVAILABLE.format(amount=escape(format_money(balance.available, balance.currency))))
    lines.append(DEAL_HANDLER_TEXT.DASHBOARD_HELD.format(amount=escape(format_money(balance.held, balance.currency))))
    lines.append(DEAL_HANDLER_TEXT.DASHBOARD_TOTAL.format(amount=escape(format_money(balance.total, balance.currency))))
    lines.append(
        DEAL_HANDLER_TEXT.DASHBOARD_EQUIVALENT.format(
            usdt_amount=escape(format_money(balance.total_quote.usdt_amount, 'USDT')),
            rub_amount=escape(format_money(balance.total_quote.rub_amount, 'RUB')),
        )
    )
    lines.append("")
    lines.append(DEAL_HANDLER_TEXT.DASHBOARD_STATS_TITLE)
    lines.append(DEAL_HANDLER_TEXT.DASHBOARD_TOTAL_DEALS.format(count=stats.total_deals))
    lines.append(DEAL_HANDLER_TEXT.DASHBOARD_OPEN_DEALS.format(count=stats.open_deals))
    lines.append(DEAL_HANDLER_TEXT.DASHBOARD_COMPLETED_DEALS.format(count=stats.completed_deals))
    lines.append(DEAL_HANDLER_TEXT.DASHBOARD_DISPUTES.format(count=stats.disputed_deals))
    lines.append(
        DEAL_HANDLER_TEXT.DASHBOARD_TURNOVER.format(
            amount=escape(format_money(stats.total_volume, stats.currency)),
            usdt_amount=escape(format_money(stats.total_volume_quote.usdt_amount, 'USDT')),
        )
    )
    lines.append(DEAL_HANDLER_TEXT.DASHBOARD_WITHDRAWALS.format(count=stats.pending_withdrawals))
    if dashboard.open_withdrawal is not None:
        lines.append("")
        lines.append(DEAL_HANDLER_TEXT.DASHBOARD_OPEN_WITHDRAWAL_TITLE)
        lines.append(
            DEAL_HANDLER_TEXT.DASHBOARD_OPEN_WITHDRAWAL.format(
                request_id=dashboard.open_withdrawal.request_id,
                amount=escape(format_money(dashboard.open_withdrawal.amount_usdt, 'USDT')),
                network=escape(dashboard.open_withdrawal.network),
            )
        )
        lines.append(escape(shorten_text(dashboard.open_withdrawal.address, 42)))
    if not container.deal_service.has_moderators:
        lines.append("")
        lines.append(DEAL_HANDLER_TEXT.DASHBOARD_NO_MODERATORS)
    return "\n".join(lines)


def render_deals_page(cards: tuple[DealCard, ...], page_info: PageInfo) -> str:
    lines = [DEAL_HANDLER_TEXT.DEALS_PAGE_TITLE, DEAL_HANDLER_TEXT.PAGE_OF.format(page=page_info.page, total_pages=page_info.total_pages)]
    if not cards:
        lines.append(DEAL_HANDLER_TEXT.DEALS_EMPTY)
        return "\n".join(lines)

    for card in cards:
        lines.append("")
        lines.append(DEAL_HANDLER_TEXT.DEAL_CARD_TITLE.format(deal_id=card.deal_id, counterpart=escape(card.counterpart_display)))
        lines.append(DEAL_HANDLER_TEXT.DEAL_CARD_ROLE.format(role=escape(format_role(card.viewer_role))))
        lines.append(DEAL_HANDLER_TEXT.DEAL_CARD_STATUS.format(status=escape(format_deal_status(card.status))))
        lines.append(DEAL_HANDLER_TEXT.DEAL_CARD_AMOUNT.format(amount=escape(format_money(card.amount, card.currency))))
        lines.append(DEAL_HANDLER_TEXT.DEAL_CARD_UPDATED.format(updated_at=escape(format_timestamp(card.updated_at, short=True))))
    return "\n".join(lines)


def render_deal_view(deal: DealView) -> str:
    lines = [DEAL_HANDLER_TEXT.DEAL_VIEW_TITLE.format(deal_id=deal.deal_id)]
    if deal.viewer_role is not None:
        lines.append(DEAL_HANDLER_TEXT.DEAL_VIEW_MY_ROLE.format(role=escape(format_role(deal.viewer_role))))
    lines.append(DEAL_HANDLER_TEXT.DEAL_VIEW_STATUS.format(status=escape(format_deal_status(deal.status))))
    lines.append(DEAL_HANDLER_TEXT.DEAL_VIEW_BUYER.format(buyer=escape(deal.buyer.display_name)))
    lines.append(DEAL_HANDLER_TEXT.DEAL_VIEW_SELLER.format(seller=escape(deal.seller.display_name)))
    lines.append(DEAL_HANDLER_TEXT.DEAL_VIEW_AMOUNT.format(amount=escape(format_money(deal.amount, deal.currency))))
    lines.append(
        DEAL_HANDLER_TEXT.DEAL_VIEW_EQUIVALENT.format(
            usdt_amount=escape(format_money(deal.amount_quote.usdt_amount, 'USDT')),
            rub_amount=escape(format_money(deal.amount_quote.rub_amount, 'RUB')),
        )
    )
    lines.append(DEAL_HANDLER_TEXT.DEAL_VIEW_CREATED.format(created_at=escape(format_timestamp(deal.created_at))))
    if deal.accepted_at is not None:
        lines.append(DEAL_HANDLER_TEXT.DEAL_VIEW_ACCEPTED.format(accepted_at=escape(format_timestamp(deal.accepted_at))))
    if deal.disputed_at is not None:
        lines.append(DEAL_HANDLER_TEXT.DEAL_VIEW_DISPUTED.format(disputed_at=escape(format_timestamp(deal.disputed_at))))
    if deal.completed_at is not None:
        lines.append(DEAL_HANDLER_TEXT.DEAL_VIEW_COMPLETED.format(completed_at=escape(format_timestamp(deal.completed_at))))
    if deal.resolution is not None:
        lines.append(DEAL_HANDLER_TEXT.DEAL_VIEW_RESOLUTION.format(resolution=escape(deal.resolution)))
    lines.append("")
    lines.append(DEAL_HANDLER_TEXT.DEAL_VIEW_TERMS_TITLE)
    lines.append(escape(deal.terms))
    lines.append("")
    lines.append(DEAL_HANDLER_TEXT.DEAL_VIEW_MESSAGES_TITLE)
    if not deal.messages:
        lines.append(DEAL_HANDLER_TEXT.DEAL_VIEW_NO_MESSAGES)
    else:
        for item in deal.messages[-6:]:
            lines.append(
                DEAL_HANDLER_TEXT.DEAL_VIEW_MESSAGE_ROW.format(
                    created_at=escape(format_timestamp(item.created_at, short=True)),
                    sender=escape(item.sender_display),
                    body=escape(item.body),
                )
            )
    return "\n".join(lines)


def render_deal_invitation(deal: DealView) -> str:
    lines = [DEAL_HANDLER_TEXT.DEAL_INVITATION_TITLE]
    lines.append(DEAL_HANDLER_TEXT.DEAL_INVITATION_BUYER.format(buyer=escape(deal.buyer.display_name)))
    lines.append(DEAL_HANDLER_TEXT.DEAL_INVITATION_AMOUNT.format(amount=escape(format_money(deal.amount, deal.currency))))
    lines.append("")
    lines.append(DEAL_HANDLER_TEXT.DEAL_INVITATION_TERMS_TITLE)
    lines.append(escape(deal.terms))
    lines.append("")
    lines.append(DEAL_HANDLER_TEXT.DEAL_INVITATION_HINT)
    return "\n".join(lines)


def render_deal_status_notification(deal: DealView, description: str) -> str:
    return "\n".join(
        [
            DEAL_HANDLER_TEXT.deal_status_notification_title(deal.deal_id),
            DEAL_HANDLER_TEXT.DEAL_STATUS_NOTIFICATION_STATUS.format(status=escape(format_deal_status(deal.status))),
            escape(description),
        ]
    )


def render_deal_message_notification(relay: DealMessageRelayResult, *, nbox_url: str | None = None) -> str:
    lines = [
        DEAL_HANDLER_TEXT.deal_message_notification_title(relay.deal.deal_id),
        DEAL_HANDLER_TEXT.DEAL_MESSAGE_NOTIFICATION_FROM.format(sender=escape(relay.sender_display)),
        escape(relay.preview),
    ]
    if nbox_url:
        lines.append(DEAL_HANDLER_TEXT.nbox_photo_link(nbox_url))
    return "\n".join(lines)


def render_withdrawal_request(request: WithdrawalRequestView) -> str:
    lines = [DEAL_HANDLER_TEXT.WITHDRAW_REQUEST_TITLE.format(request_id=request.request_id)]
    lines.append(DEAL_HANDLER_TEXT.WITHDRAW_REQUEST_STATUS.format(status=escape(format_withdrawal_status(request.status))))
    lines.append(DEAL_HANDLER_TEXT.WITHDRAW_REQUEST_AMOUNT_USDT.format(amount=escape(format_money(request.amount_usdt, 'USDT'))))
    lines.append(DEAL_HANDLER_TEXT.WITHDRAW_REQUEST_HELD.format(amount=escape(format_money(request.amount, request.currency))))
    lines.append(DEAL_HANDLER_TEXT.WITHDRAW_REQUEST_NETWORK.format(network=escape(request.network)))
    lines.append(DEAL_HANDLER_TEXT.WITHDRAW_REQUEST_ADDRESS.format(address=escape(request.address)))
    lines.append(DEAL_HANDLER_TEXT.WITHDRAW_REQUEST_CREATED.format(created_at=escape(format_timestamp(request.created_at))))
    if request.resolution_note:
        lines.append(DEAL_HANDLER_TEXT.WITHDRAW_REQUEST_COMMENT.format(comment=escape(request.resolution_note)))
    return "\n".join(lines)


def render_withdrawal_status_notification(request: WithdrawalRequestView) -> str:
    return "\n".join(
        [
            DEAL_HANDLER_TEXT.WITHDRAW_STATUS_NOTIFICATION_TITLE.format(request_id=request.request_id),
            DEAL_HANDLER_TEXT.WITHDRAW_STATUS_NOTIFICATION_STATUS.format(status=escape(format_withdrawal_status(request.status))),
            DEAL_HANDLER_TEXT.WITHDRAW_STATUS_NOTIFICATION_AMOUNT.format(amount=escape(format_money(request.amount_usdt, 'USDT'))),
        ]
    )


def render_moderator_deal_alert(deal: DealView, reason: str) -> str:
    lines = [DEAL_HANDLER_TEXT.MODERATOR_ALERT_TITLE]
    lines.append(escape(reason))
    lines.append(DEAL_HANDLER_TEXT.MODERATOR_ALERT_DEAL.format(deal_id=deal.deal_id))
    lines.append(DEAL_HANDLER_TEXT.MODERATOR_ALERT_BUYER.format(buyer=escape(deal.buyer.display_name)))
    lines.append(DEAL_HANDLER_TEXT.MODERATOR_ALERT_SELLER.format(seller=escape(deal.seller.display_name)))
    lines.append(DEAL_HANDLER_TEXT.MODERATOR_ALERT_AMOUNT.format(amount=escape(format_money(deal.amount, deal.currency))))
    lines.append(DEAL_HANDLER_TEXT.MODERATOR_ALERT_STATUS.format(status=escape(format_deal_status(deal.status))))
    lines.append(escape(shorten_text(deal.terms, 220)))
    return "\n".join(lines)


def render_moderator_withdrawal_alert(request: WithdrawalRequestView) -> str:
    return "\n".join(
        [
            DEAL_HANDLER_TEXT.MODERATOR_WITHDRAW_TITLE,
            DEAL_HANDLER_TEXT.MODERATOR_WITHDRAW_ID.format(request_id=request.request_id),
            DEAL_HANDLER_TEXT.MODERATOR_WITHDRAW_USER.format(telegram_id=request.telegram_id),
            DEAL_HANDLER_TEXT.MODERATOR_WITHDRAW_AMOUNT.format(amount=escape(format_money(request.amount_usdt, 'USDT'))),
            DEAL_HANDLER_TEXT.MODERATOR_WITHDRAW_NETWORK.format(network=escape(request.network)),
            DEAL_HANDLER_TEXT.MODERATOR_WITHDRAW_ADDRESS.format(address=escape(request.address)),
        ]
    )


def render_moderation_result(result: DealModerationResult) -> str:
    return "\n".join(
        [
            DEAL_HANDLER_TEXT.MODERATION_RESULT_TITLE,
            DEAL_HANDLER_TEXT.MODERATION_RESULT_DEAL.format(deal_id=result.deal_id),
            DEAL_HANDLER_TEXT.MODERATION_RESULT_STATUS.format(status=escape(format_deal_status(result.status))),
            DEAL_HANDLER_TEXT.MODERATION_RESULT_RESOLUTION.format(resolution=escape(result.resolution or DEAL_HANDLER_TEXT.RESOLUTION_UNSPECIFIED)),
        ]
    )


def render_moderation_result_notification(result: DealModerationResult) -> str:
    return "\n".join(
        [
            DEAL_HANDLER_TEXT.moderator_notification_title(result.deal_id),
            DEAL_HANDLER_TEXT.MODERATION_RESULT_STATUS.format(status=escape(format_deal_status(result.status))),
            DEAL_HANDLER_TEXT.MODERATION_RESULT_RESOLUTION.format(resolution=escape(result.resolution or DEAL_HANDLER_TEXT.RESOLUTION_UNSPECIFIED)),
        ]
    )


def render_deal_error(error: Exception) -> str:
    return DEAL_HANDLER_TEXT.deal_error(escape(str(error)))


def parse_deal_decimal(value: str) -> Decimal:
    normalized = value.replace(",", ".").strip()
    if not normalized:
        raise ValueError(DEAL_HANDLER_TEXT.ENTER_AMOUNT_NUMERIC)
    try:
        amount = Decimal(normalized)
    except InvalidOperation as error:
        raise ValueError(DEAL_HANDLER_TEXT.INVALID_AMOUNT) from error
    return amount.quantize(Decimal("0.01"))


def parse_int_suffix(value: str, prefix: str, default: int | None = None) -> int:
    raw = value.removeprefix(prefix)
    try:
        return int(raw)
    except ValueError:
        if default is None:
            raise
        return default


def parse_action_suffix(value: str, prefix: str) -> tuple[int, str]:
    raw = value.removeprefix(prefix)
    numeric_part, action = raw.split(":", 1)
    return int(numeric_part), action


def format_role(value: str) -> str:
    return DEAL_HANDLER_TEXT.ROLE_BUYER if value == "buyer" else DEAL_HANDLER_TEXT.ROLE_SELLER


def format_deal_status(value: str) -> str:
    return DEAL_HANDLER_TEXT.deal_status_label(value)


def format_withdrawal_status(value: str) -> str:
    return DEAL_HANDLER_TEXT.withdrawal_status_label(value)


def format_timestamp(value: object, *, short: bool = False) -> str:
    if not isinstance(value, datetime):
        return str(value)
    pattern = "%d.%m %H:%M UTC" if short else "%d.%m.%Y %H:%M UTC"
    return value.astimezone(timezone.utc).strftime(pattern)


def summarize_user_message(message: Message) -> tuple[str, str]:
    # aiogram 3: message.content_type — StrEnum, .value даёт «photo», «document» и т.д.
    content_type: str = getattr(message.content_type, "value", str(message.content_type))
    if message.text:
        return content_type, shorten_text(message.text, 280)
    if message.caption:
        return content_type, DEAL_HANDLER_TEXT.content_with_caption(content_type, shorten_text(message.caption, 240))
    return content_type, DEAL_HANDLER_TEXT.CONTENT_SUMMARIES.get(content_type, DEAL_HANDLER_TEXT.content_empty(content_type))


def should_cancel(text: str | None) -> bool:
    normalized = (text or "").strip().lower()
    return normalized in DEAL_HANDLER_TEXT.CANCEL_COMMANDS


async def cancel_state_flow(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(DEAL_HANDLER_TEXT.ACTION_CANCELED, reply_markup=build_deal_home_keyboard())
