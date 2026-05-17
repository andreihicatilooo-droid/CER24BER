"""Обработчики раздела Telegram-аккаунтов GetMyTG."""

from __future__ import annotations

from datetime import timezone
from html import escape

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from cerber_bot.container import AppContainer
from cerber_bot.db.models import TgAccountPurchase
from cerber_bot.handlers.menu import answer_callback_safely, extract_message
from cerber_bot.integrations.getmytg import GetMyTGClient
from cerber_bot.keyboards.tgaccounts import (
    TGACC_BUY_PREFIX,
    TGACC_CANCEL_BUY_ACTION,
    TGACC_CONFIRM_BUY_PREFIX,
    TGACC_COUNTRIES_PAGE_PREFIX,
    TGACC_COUNTRY_DETAIL_PREFIX,
    TGACC_HOME_ACTION,
    TGACC_MY_PURCHASES_ACTION,
    TGACC_MY_PURCHASES_PAGE_PREFIX,
    TGACC_PURCHASE_DETAIL_PREFIX,
    TGACC_REFUND_PREFIX,
    TGACC_REQUEST_CODE_PREFIX,
    build_buy_confirmation_keyboard,
    build_country_detail_keyboard,
    build_countries_keyboard,
    build_home_keyboard,
    build_my_purchases_keyboard,
    build_purchase_detail_keyboard,
)
from cerber_bot.services.store import PageInfo, build_page_info, format_money
from cerber_bot.services.tgaccounts import (
    TgAccountInsufficientBalanceError,
    TgAccountNotFoundError,
    TgAccountService,
    TgAccountServiceError,
    TgCatalogPage,
    TgCountryDetails,
)
from cerber_bot.texts import TG_ACCOUNTS_TEXT


PURCHASES_PER_PAGE = 6


class TgAccountsStates(StatesGroup):
    waiting_for_buy_confirmation = State()


def build_tgaccounts_router(container: AppContainer) -> Router:
    router = Router(name="tgaccounts")

    @router.callback_query(F.data == TGACC_HOME_ACTION)
    async def handle_home(callback: CallbackQuery, state: FSMContext) -> None:
        message = extract_message(callback)
        if message is None or callback.from_user is None:
            await callback.answer()
            return

        await container.user_service.register_or_update(callback.from_user)
        await state.clear()
        await send_screen(
            message,
            render_home_screen(_service(container).is_configured),
            build_home_keyboard(),
            callback=callback,
        )
        await answer_callback_safely(callback, TG_ACCOUNTS_TEXT.CALLBACK_HOME)

    @router.callback_query(F.data.startswith(TGACC_COUNTRIES_PAGE_PREFIX))
    async def handle_countries(callback: CallbackQuery, state: FSMContext) -> None:
        message = extract_message(callback)
        if message is None:
            await callback.answer()
            return

        service = _service(container)
        page = parse_int_suffix(callback.data, TGACC_COUNTRIES_PAGE_PREFIX, 1)
        await answer_callback_safely(callback, TG_ACCOUNTS_TEXT.CALLBACK_COUNTRIES)
        await state.set_state(None)
        try:
            catalog = await service.get_catalog(page=page)
        except TgAccountServiceError as error:
            await send_screen(message, render_error_screen(error), build_home_keyboard(), callback=callback)
            return

        await state.update_data(tgacc_countries_page=catalog.page)
        await send_screen(
            message,
            render_catalog_screen(catalog),
            build_countries_keyboard(catalog),
            callback=callback,
        )

    @router.callback_query(F.data.startswith(TGACC_COUNTRY_DETAIL_PREFIX))
    async def handle_country_detail(callback: CallbackQuery, state: FSMContext) -> None:
        message = extract_message(callback)
        if message is None:
            await callback.answer()
            return

        service = _service(container)
        if not service.is_configured:
            await answer_callback_safely(callback, TG_ACCOUNTS_TEXT.CALLBACK_UNAVAILABLE)
            await send_screen(message, TG_ACCOUNTS_TEXT.NOT_CONFIGURED, build_home_keyboard(), callback=callback)
            return

        data = await state.get_data()
        countries_page = int(data.get("tgacc_countries_page", 1))
        country_code = parse_code_suffix(callback.data, TGACC_COUNTRY_DETAIL_PREFIX)
        await answer_callback_safely(callback, TG_ACCOUNTS_TEXT.CALLBACK_COUNTRY)
        await state.set_state(None)
        try:
            details = await service.get_country_details(country_code)
        except TgAccountServiceError as error:
            await send_screen(message, render_error_screen(error), build_home_keyboard(), callback=callback)
            return

        await state.update_data(tgacc_countries_page=countries_page, tgacc_selected_country=details.country_code)
        await send_screen(
            message,
            render_country_detail_screen(details),
            build_country_detail_keyboard(details.country_code, details.available, back_page=countries_page),
            callback=callback,
        )

    @router.callback_query(F.data.startswith(TGACC_BUY_PREFIX))
    async def handle_buy_prompt(callback: CallbackQuery, state: FSMContext) -> None:
        message = extract_message(callback)
        if message is None or callback.from_user is None:
            await callback.answer()
            return

        service = _service(container)
        if not service.is_configured:
            await answer_callback_safely(callback, TG_ACCOUNTS_TEXT.CALLBACK_UNAVAILABLE)
            await send_screen(message, TG_ACCOUNTS_TEXT.NOT_CONFIGURED, build_home_keyboard(), callback=callback)
            return

        country_code = parse_code_suffix(callback.data, TGACC_BUY_PREFIX)
        await answer_callback_safely(callback, TG_ACCOUNTS_TEXT.CALLBACK_CONFIRM)
        try:
            details = await service.get_country_details(country_code)
        except TgAccountServiceError as error:
            await send_screen(message, render_error_screen(error), build_home_keyboard(), callback=callback)
            return

        data = await state.get_data()
        await state.set_state(TgAccountsStates.waiting_for_buy_confirmation)
        await state.update_data(
            tgacc_buy_country=details.country_code,
            tgacc_countries_page=int(data.get("tgacc_countries_page", 1)),
        )
        await send_screen(
            message,
            render_buy_confirmation_screen(details),
            build_buy_confirmation_keyboard(details.country_code),
            callback=callback,
        )

    @router.callback_query(F.data.startswith(TGACC_CONFIRM_BUY_PREFIX))
    async def handle_buy_confirm(callback: CallbackQuery, state: FSMContext) -> None:
        message = extract_message(callback)
        if message is None or callback.from_user is None:
            await callback.answer()
            return

        service = _service(container)
        state_data = await state.get_data()
        expected_country = str(state_data.get("tgacc_buy_country") or "").upper()
        country_code = parse_code_suffix(callback.data, TGACC_CONFIRM_BUY_PREFIX)
        if await state.get_state() != TgAccountsStates.waiting_for_buy_confirmation.state or expected_country != country_code:
            await state.clear()
            await answer_callback_safely(callback, TG_ACCOUNTS_TEXT.CALLBACK_UNAVAILABLE)
            await send_screen(message, TG_ACCOUNTS_TEXT.BUY_CONTEXT_LOST, build_home_keyboard(), callback=callback)
            return

        await answer_callback_safely(callback, TG_ACCOUNTS_TEXT.CALLBACK_BUY_PROCESSING)
        try:
            purchase = await service.buy_account(callback.from_user.id, country_code)
        except TgAccountInsufficientBalanceError as error:
            await state.clear()
            await send_screen(message, render_error_screen(error), build_home_keyboard(), callback=callback)
            return
        except TgAccountServiceError as error:
            await state.clear()
            await send_screen(message, render_error_screen(error), build_home_keyboard(), callback=callback)
            return

        await state.clear()
        await send_screen(
            message,
            render_purchase_detail_screen(purchase),
            build_purchase_detail_keyboard(purchase),
            callback=callback,
        )

    @router.callback_query(F.data == TGACC_CANCEL_BUY_ACTION)
    async def handle_buy_cancel(callback: CallbackQuery, state: FSMContext) -> None:
        message = extract_message(callback)
        if message is None:
            await callback.answer()
            return

        service = _service(container)
        state_data = await state.get_data()
        country_code = str(state_data.get("tgacc_buy_country") or "").upper()
        countries_page = int(state_data.get("tgacc_countries_page", 1))
        await state.clear()
        await answer_callback_safely(callback, TG_ACCOUNTS_TEXT.BUY_CANCELED)
        if country_code and service.is_configured:
            try:
                details = await service.get_country_details(country_code)
            except TgAccountServiceError:
                await send_screen(message, render_home_screen(service.is_configured), build_home_keyboard(), callback=callback)
                return
            await send_screen(
                message,
                render_country_detail_screen(details),
                build_country_detail_keyboard(details.country_code, details.available, back_page=countries_page),
                callback=callback,
            )
            return

        await send_screen(message, render_home_screen(service.is_configured), build_home_keyboard(), callback=callback)

    @router.callback_query(F.data == TGACC_MY_PURCHASES_ACTION)
    async def handle_my_purchases(callback: CallbackQuery, state: FSMContext) -> None:
        await render_my_purchases(callback, state, container, page=1)

    @router.callback_query(F.data.startswith(TGACC_MY_PURCHASES_PAGE_PREFIX))
    async def handle_my_purchases_page(callback: CallbackQuery, state: FSMContext) -> None:
        page = parse_int_suffix(callback.data, TGACC_MY_PURCHASES_PAGE_PREFIX, 1)
        await render_my_purchases(callback, state, container, page=page)

    @router.callback_query(F.data.startswith(TGACC_PURCHASE_DETAIL_PREFIX))
    async def handle_purchase_detail(callback: CallbackQuery, state: FSMContext) -> None:
        message = extract_message(callback)
        if message is None or callback.from_user is None:
            await callback.answer()
            return

        service = _service(container)
        purchase_id = parse_int_suffix(callback.data, TGACC_PURCHASE_DETAIL_PREFIX)
        await answer_callback_safely(callback, TG_ACCOUNTS_TEXT.CALLBACK_PURCHASE)
        await state.set_state(None)
        try:
            purchase = await service.get_purchase(callback.from_user.id, purchase_id)
        except TgAccountServiceError as error:
            await send_screen(message, render_error_screen(error), build_home_keyboard(), callback=callback)
            return

        await send_screen(
            message,
            render_purchase_detail_screen(purchase),
            build_purchase_detail_keyboard(purchase),
            callback=callback,
        )

    @router.callback_query(F.data.startswith(TGACC_REQUEST_CODE_PREFIX))
    async def handle_request_code(callback: CallbackQuery, state: FSMContext) -> None:
        message = extract_message(callback)
        if message is None or callback.from_user is None:
            await callback.answer()
            return

        service = _service(container)
        if not service.is_configured:
            await answer_callback_safely(callback, TG_ACCOUNTS_TEXT.CALLBACK_UNAVAILABLE)
            await send_screen(message, TG_ACCOUNTS_TEXT.NOT_CONFIGURED, build_home_keyboard(), callback=callback)
            return

        purchase_id = parse_int_suffix(callback.data, TGACC_REQUEST_CODE_PREFIX)
        try:
            current_purchase = await service.get_purchase(callback.from_user.id, purchase_id)
        except TgAccountServiceError as error:
            await answer_callback_safely(callback, TG_ACCOUNTS_TEXT.CALLBACK_UNAVAILABLE)
            await send_screen(message, render_error_screen(error), build_home_keyboard(), callback=callback)
            return

        await answer_callback_safely(callback, TG_ACCOUNTS_TEXT.CALLBACK_REQUEST_CODE)
        await send_screen(message, TG_ACCOUNTS_TEXT.REQUESTING_CODE, build_purchase_detail_keyboard(current_purchase), callback=callback)
        try:
            purchase = await service.request_verification(
                callback.from_user.id,
                purchase_id,
                callback_url=build_getmytg_callback_url(container),
            )
        except TgAccountServiceError as error:
            await send_screen(message, render_error_screen(error), build_purchase_detail_keyboard(current_purchase), callback=callback)
            return

        await send_screen(
            message,
            render_purchase_detail_screen(purchase),
            build_purchase_detail_keyboard(purchase),
            callback=callback,
        )

    @router.callback_query(F.data.startswith(TGACC_REFUND_PREFIX))
    async def handle_refund(callback: CallbackQuery, state: FSMContext) -> None:
        message = extract_message(callback)
        if message is None or callback.from_user is None:
            await callback.answer()
            return

        service = _service(container)
        if not service.is_configured:
            await answer_callback_safely(callback, TG_ACCOUNTS_TEXT.CALLBACK_UNAVAILABLE)
            await send_screen(message, TG_ACCOUNTS_TEXT.NOT_CONFIGURED, build_home_keyboard(), callback=callback)
            return

        purchase_id = parse_int_suffix(callback.data, TGACC_REFUND_PREFIX)
        try:
            current_purchase = await service.get_purchase(callback.from_user.id, purchase_id)
        except TgAccountServiceError as error:
            await answer_callback_safely(callback, TG_ACCOUNTS_TEXT.CALLBACK_UNAVAILABLE)
            await send_screen(message, render_error_screen(error), build_home_keyboard(), callback=callback)
            return

        await answer_callback_safely(callback, TG_ACCOUNTS_TEXT.CALLBACK_REFUND)
        await send_screen(message, TG_ACCOUNTS_TEXT.REFUNDING, build_purchase_detail_keyboard(current_purchase), callback=callback)
        try:
            purchase = await service.refund(callback.from_user.id, purchase_id)
        except TgAccountServiceError as error:
            await send_screen(message, render_error_screen(error), build_purchase_detail_keyboard(current_purchase), callback=callback)
            return

        await send_screen(
            message,
            render_purchase_detail_screen(purchase),
            build_purchase_detail_keyboard(purchase),
            callback=callback,
        )

    @router.callback_query(F.data == "noop")
    async def handle_noop(callback: CallbackQuery) -> None:
        await answer_callback_safely(callback)

    return router


async def render_my_purchases(
    callback: CallbackQuery,
    state: FSMContext,
    container: AppContainer,
    *,
    page: int,
) -> None:
    message = extract_message(callback)
    if message is None or callback.from_user is None:
        await callback.answer()
        return

    service = _service(container)
    await answer_callback_safely(callback, TG_ACCOUNTS_TEXT.CALLBACK_PURCHASES)
    await state.set_state(None)
    try:
        purchases = await service.get_my_purchases(callback.from_user.id)
    except TgAccountServiceError as error:
        await send_screen(message, render_error_screen(error), build_home_keyboard(), callback=callback)
        return

    items, page_info = paginate_purchases(purchases, page=page, per_page=PURCHASES_PER_PAGE)
    await state.update_data(tgacc_purchases_page=page_info.page)
    await send_screen(
        message,
        render_purchases_screen(items, page_info),
        build_my_purchases_keyboard(items, page_info),
        callback=callback,
    )


def _service(container: AppContainer) -> TgAccountService:
    if container.tgaccounts_service is None:
        raise RuntimeError("TgAccountService не инициализирован.")
    return container.tgaccounts_service


def build_getmytg_callback_url(container: AppContainer) -> str | None:
    base_url = (container.settings.web_base_url or "").rstrip("/")
    if not base_url:
        return None
    path = (container.settings.getmytg_webhook_path or "/webhooks/getmytg").strip() or "/webhooks/getmytg"
    normalized_path = path if path.startswith("/") else f"/{path}"
    callback_url = f"{base_url}{normalized_path}"
    secret = (container.settings.getmytg_webhook_secret or "").strip()
    if not secret:
        return callback_url
    return GetMyTGClient.sign_webhook_url(callback_url, secret)


async def send_screen(
    message: Message,
    text: str,
    reply_markup: InlineKeyboardMarkup,
    *,
    callback: CallbackQuery | None = None,
) -> None:
    if callback is not None and callback.message is not None and callback.message.text:
        try:
            await callback.message.edit_text(text, reply_markup=reply_markup, parse_mode="HTML")
            return
        except TelegramBadRequest:
            pass

    await message.answer(text, reply_markup=reply_markup, parse_mode="HTML")


def render_home_screen(configured: bool) -> str:
    return "\n".join(
        [
            TG_ACCOUNTS_TEXT.TITLE,
            TG_ACCOUNTS_TEXT.DESCRIPTION,
            "",
            TG_ACCOUNTS_TEXT.configured_hint(configured),
        ]
    )


def render_catalog_screen(catalog: TgCatalogPage) -> str:
    lines = [
        TG_ACCOUNTS_TEXT.COUNTRIES_TITLE,
        TG_ACCOUNTS_TEXT.countries_page(catalog.page, catalog.total_pages),
    ]
    if not catalog.items:
        lines.append(TG_ACCOUNTS_TEXT.COUNTRIES_EMPTY)
        return "\n".join(lines)

    lines.extend(["", TG_ACCOUNTS_TEXT.COUNTRIES_HINT])
    return "\n".join(lines)


def render_country_detail_screen(details: TgCountryDetails) -> str:
    emoji = escape(details.emoji or "🌍")
    lines = [
        TG_ACCOUNTS_TEXT.country_title(emoji, escape(details.display_name)),
        TG_ACCOUNTS_TEXT.COUNTRY_CODE.format(code=escape(details.country_code.upper())),
        TG_ACCOUNTS_TEXT.COUNTRY_PRICE.format(amount=escape(format_money(details.amount, details.currency))),
        TG_ACCOUNTS_TEXT.COUNTRY_AVAILABLE.format(
            value=escape("доступно" if details.available else "нет в наличии")
        ),
    ]
    if details.base_price is not None:
        lines.append(
            TG_ACCOUNTS_TEXT.COUNTRY_BASE_PRICE.format(
                amount=escape(format_money(details.base_price, details.currency))
            )
        )
    if details.discount_percent is not None:
        lines.append(TG_ACCOUNTS_TEXT.COUNTRY_DISCOUNT.format(percent=details.discount_percent))
    if details.available_count is not None:
        lines.append(TG_ACCOUNTS_TEXT.COUNTRY_AVAILABLE_COUNT.format(count=details.available_count))
    lines.extend(["", TG_ACCOUNTS_TEXT.COUNTRY_BUY_HINT if details.available else TG_ACCOUNTS_TEXT.COUNTRY_UNAVAILABLE_HINT])
    return "\n".join(lines)


def render_buy_confirmation_screen(details: TgCountryDetails) -> str:
    return "\n".join(
        [
            TG_ACCOUNTS_TEXT.BUY_CONFIRM_TITLE,
            TG_ACCOUNTS_TEXT.BUY_CONFIRM_COUNTRY.format(country=escape(details.display_name)),
            TG_ACCOUNTS_TEXT.BUY_CONFIRM_PRICE.format(amount=escape(format_money(details.amount, details.currency))),
            "",
            TG_ACCOUNTS_TEXT.BUY_CONFIRM_HINT,
        ]
    )


def render_purchases_screen(purchases: tuple[TgAccountPurchase, ...], page_info: PageInfo) -> str:
    lines = [
        TG_ACCOUNTS_TEXT.PURCHASES_TITLE,
        TG_ACCOUNTS_TEXT.purchases_page(page_info.page, page_info.total_pages),
    ]
    if not purchases:
        lines.append(TG_ACCOUNTS_TEXT.PURCHASES_EMPTY)
        return "\n".join(lines)

    lines.extend(["", TG_ACCOUNTS_TEXT.PURCHASES_HINT])
    return "\n".join(lines)


def render_purchase_detail_screen(purchase: TgAccountPurchase) -> str:
    updated_at = purchase.updated_at.astimezone(timezone.utc).strftime("%d.%m.%Y %H:%M UTC")
    lines = [
        TG_ACCOUNTS_TEXT.PURCHASE_TITLE.format(purchase_id=purchase.id),
        TG_ACCOUNTS_TEXT.PURCHASE_COUNTRY.format(country=escape(purchase.country_code.upper())),
        TG_ACCOUNTS_TEXT.PURCHASE_PHONE.format(phone=escape(purchase.phone_number or "не получен")),
        TG_ACCOUNTS_TEXT.PURCHASE_STATUS.format(status=escape(TG_ACCOUNTS_TEXT.status_label(purchase.status))),
        TG_ACCOUNTS_TEXT.PURCHASE_AMOUNT.format(
            amount=escape(format_money(purchase.amount, purchase.currency))
        ),
        TG_ACCOUNTS_TEXT.PURCHASE_TYPE.format(purchase_type=escape(purchase.purchase_type)),
        TG_ACCOUNTS_TEXT.PURCHASE_UPDATED.format(updated_at=updated_at),
    ]
    if purchase.verification_code:
        lines.append(TG_ACCOUNTS_TEXT.PURCHASE_CODE.format(code=escape(purchase.verification_code)))
    if purchase.verification_password:
        lines.append(
            TG_ACCOUNTS_TEXT.PURCHASE_PASSWORD.format(password=escape(purchase.verification_password))
        )
    if not purchase.verification_code:
        lines.extend(["", TG_ACCOUNTS_TEXT.PURCHASE_CODE_PENDING])
    lines.extend(["", TG_ACCOUNTS_TEXT.PURCHASE_HINT])
    return "\n".join(lines)


def render_error_screen(error: Exception) -> str:
    message = escape(str(error).strip() or TG_ACCOUNTS_TEXT.CALLBACK_UNAVAILABLE)
    return f"<b>Ошибка раздела</b>\n{message}"


def paginate_purchases(
    purchases: tuple[TgAccountPurchase, ...],
    *,
    page: int,
    per_page: int,
) -> tuple[tuple[TgAccountPurchase, ...], PageInfo]:
    page_info = build_page_info(total_items=len(purchases), page=page, per_page=per_page)
    start = (page_info.page - 1) * page_info.per_page
    end = start + page_info.per_page
    return purchases[start:end], page_info


def parse_int_suffix(data: str | None, prefix: str, default: int | None = None) -> int:
    raw = (data or "")[len(prefix):].strip()
    try:
        return int(raw)
    except ValueError:
        if default is not None:
            return default
        raise


def parse_code_suffix(data: str | None, prefix: str) -> str:
    return (data or "")[len(prefix):].strip().upper()
