"""Обработчики витрины магазина.

Категории, товары, поиск, кошелёк, пополнение через NicePay,
покупка SKU и пользовательские заказы.
"""

from __future__ import annotations

import json
from datetime import timezone
from decimal import Decimal, InvalidOperation
from html import escape

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from cerber_bot.container import AppContainer
from cerber_bot.handlers.menu import extract_message
from cerber_bot.integrations.giftapi import GiftApiError
from cerber_bot.keyboards.main_menu import build_main_menu
from cerber_bot.keyboards.storefront import (
    STORE_BUY_SKU_PREFIX,
    STORE_CATEGORIES_ACTION,
    STORE_CATEGORIES_PAGE_PREFIX,
    STORE_CATEGORY_OPEN_PREFIX,
    STORE_DETAIL_BACK_ACTION,
    STORE_DETAIL_OFFERS_PAGE_PREFIX,
    STORE_FIELD_CANCEL_ACTION,
    STORE_FIELD_FILL_PREFIX,
    STORE_HOME_ACTION,
    STORE_ORDER_ACTION_PREFIX,
    STORE_ORDERS_ACTION,
    STORE_ORDERS_PAGE_PREFIX,
    STORE_PRODUCT_ACTION_PREFIX,
    STORE_PRODUCTS_PAGE_PREFIX,
    STORE_REFRESH_ACTION,
    STORE_SEARCH_PAGE_PREFIX,
    STORE_SEARCH_PROMPT_ACTION,
    STORE_TOP_UP_CUSTOM_ACTION,
    STORE_TOP_UP_PREFIX,
    STORE_WALLET_ACTION,
    build_categories_keyboard,
    build_field_input_keyboard,
    build_order_detail_keyboard,
    build_orders_keyboard,
    build_product_detail_keyboard,
    build_products_keyboard,
    build_store_home_keyboard,
    build_wallet_keyboard,
)
from cerber_bot.services.store import (
    DEFAULT_WALLET_CURRENCY,
    SUPPORTED_AUTO_FIELDS,
    InsufficientBalanceError,
    PageInfo,
    ProductUnavailableError,
    PurchaseResult,
    SearchQueryError,
    StoreDashboard,
    StoreOrderCard,
    StoreOrderView,
    StoreProductCard,
    StoreProductOffer,
    StoreProductView,
    StoreServiceError,
    WalletSnapshot,
    build_page_info,
    format_money,
)
from cerber_bot.services.payments import PaymentConfigurationError, PaymentFlowError
from cerber_bot.texts import STORE_KEYBOARD_TEXT, STOREFRONT_TEXT


class StorefrontStates(StatesGroup):
    waiting_for_search_query = State()
    waiting_for_top_up_amount = State()
    waiting_for_field_value = State()  # сбор значений required_fields перед покупкой


PRODUCTS_PER_PAGE = 6
CATEGORIES_PER_PAGE = 8
ORDERS_PER_PAGE = 6
OFFERS_PER_PAGE = 5


def build_storefront_router(container: AppContainer) -> Router:
    router = Router(name="storefront")

    @router.callback_query(F.data == STORE_HOME_ACTION)
    async def handle_store_home(callback: CallbackQuery, state: FSMContext) -> None:
        message = extract_message(callback)
        if message is None or callback.from_user is None:
            await callback.answer()
            return

        await container.store_service.ensure_user(callback.from_user)
        await state.set_state(None)
        try:
            await render_store_home(message, state, container, callback=callback)
        except (StoreServiceError, GiftApiError) as error:
            await send_screen(message, render_store_error(error), build_store_home_keyboard(), callback=callback)
            await callback.answer(STOREFRONT_TEXT.CALLBACK_HOME_UNAVAILABLE)
            return
        await callback.answer(STOREFRONT_TEXT.CALLBACK_HOME_OPENED)

    @router.callback_query(F.data == STORE_CATEGORIES_ACTION)
    async def handle_categories(callback: CallbackQuery, state: FSMContext) -> None:
        message = extract_message(callback)
        if message is None:
            await callback.answer()
            return

        await state.set_state(None)
        try:
            await render_categories(message, state, container, callback=callback, page=1)
        except (StoreServiceError, GiftApiError) as error:
            await send_screen(message, render_store_error(error), build_store_home_keyboard(), callback=callback)
            await callback.answer(STOREFRONT_TEXT.CALLBACK_CATEGORIES_UNAVAILABLE)
            return
        await callback.answer(STOREFRONT_TEXT.CALLBACK_CATEGORIES_OPENED)

    @router.callback_query(F.data.startswith(STORE_CATEGORIES_PAGE_PREFIX))
    async def handle_categories_page(callback: CallbackQuery, state: FSMContext) -> None:
        message = extract_message(callback)
        if message is None:
            await callback.answer()
            return

        page = parse_int_suffix(callback.data, STORE_CATEGORIES_PAGE_PREFIX, 1)
        await state.set_state(None)
        try:
            await render_categories(message, state, container, callback=callback, page=page)
        except (StoreServiceError, GiftApiError) as error:
            await send_screen(message, render_store_error(error), build_store_home_keyboard(), callback=callback)
            await callback.answer(STOREFRONT_TEXT.CALLBACK_CATEGORIES_UNAVAILABLE)
            return
        await callback.answer()

    @router.callback_query(F.data.startswith(STORE_CATEGORY_OPEN_PREFIX))
    async def handle_category_products(callback: CallbackQuery, state: FSMContext) -> None:
        message = extract_message(callback)
        if message is None:
            await callback.answer()
            return

        category_id = parse_int_suffix(callback.data, STORE_CATEGORY_OPEN_PREFIX)
        categories_page = (await state.get_data()).get("categories_page", 1)
        await state.set_state(None)
        try:
            await render_products(
                message,
                state,
                container,
                callback=callback,
                page=1,
                category_id=category_id,
                categories_page=int(categories_page),
            )
        except (StoreServiceError, GiftApiError) as error:
            await send_screen(message, render_store_error(error), build_store_home_keyboard(), callback=callback)
            await callback.answer(STOREFRONT_TEXT.CALLBACK_PRODUCTS_UNAVAILABLE)
            return
        await callback.answer(STOREFRONT_TEXT.CALLBACK_CATEGORY_PRODUCTS)

    @router.callback_query(F.data.startswith(STORE_PRODUCTS_PAGE_PREFIX))
    async def handle_products_page(callback: CallbackQuery, state: FSMContext) -> None:
        message = extract_message(callback)
        if message is None:
            await callback.answer()
            return

        page = parse_int_suffix(callback.data, STORE_PRODUCTS_PAGE_PREFIX, 1)
        data = await state.get_data()
        category_id = data.get("current_category_id")
        categories_page = int(data.get("categories_page", 1))
        await state.set_state(None)
        try:
            await render_products(
                message,
                state,
                container,
                callback=callback,
                page=page,
                category_id=int(category_id) if category_id is not None else None,
                categories_page=categories_page,
            )
        except (StoreServiceError, GiftApiError) as error:
            await send_screen(message, render_store_error(error), build_store_home_keyboard(), callback=callback)
            await callback.answer(STOREFRONT_TEXT.CALLBACK_PRODUCTS_UNAVAILABLE)
            return
        await callback.answer()

    @router.callback_query(F.data == STORE_SEARCH_PROMPT_ACTION)
    async def handle_search_prompt(callback: CallbackQuery, state: FSMContext) -> None:
        message = extract_message(callback)
        if message is None:
            await callback.answer()
            return

        await state.set_state(StorefrontStates.waiting_for_search_query)
        await message.answer(
            STOREFRONT_TEXT.SEARCH_PROMPT,
            reply_markup=build_store_home_keyboard(),
        )
        await callback.answer(STOREFRONT_TEXT.CALLBACK_SEARCH_READY)

    @router.message(StorefrontStates.waiting_for_search_query)
    async def handle_search_query(message: Message, state: FSMContext) -> None:
        query = (message.text or "").strip()
        if not query:
            await message.answer(STOREFRONT_TEXT.SEARCH_EMPTY)
            return

        await state.update_data(search_query=query)
        await state.set_state(None)
        try:
            await render_search_results(message, state, container, page=1)
        except (StoreServiceError, GiftApiError) as error:
            await message.answer(render_store_error(error), reply_markup=build_store_home_keyboard())

    @router.callback_query(F.data.startswith(STORE_SEARCH_PAGE_PREFIX))
    async def handle_search_page(callback: CallbackQuery, state: FSMContext) -> None:
        message = extract_message(callback)
        if message is None:
            await callback.answer()
            return

        page = parse_int_suffix(callback.data, STORE_SEARCH_PAGE_PREFIX, 1)
        await state.set_state(None)
        try:
            await render_search_results(message, state, container, callback=callback, page=page)
        except (StoreServiceError, GiftApiError) as error:
            await send_screen(message, render_store_error(error), build_store_home_keyboard(), callback=callback)
            await callback.answer(STOREFRONT_TEXT.CALLBACK_SEARCH_UNAVAILABLE)
            return
        await callback.answer()

    @router.callback_query(F.data.startswith(STORE_PRODUCT_ACTION_PREFIX))
    async def handle_product_detail(callback: CallbackQuery, state: FSMContext) -> None:
        message = extract_message(callback)
        if message is None:
            await callback.answer()
            return

        product_id = callback.data.removeprefix(STORE_PRODUCT_ACTION_PREFIX)
        await state.set_state(None)
        await state.update_data(active_product_id=product_id, active_offer_page=1)
        try:
            await render_product_detail(message, state, container, callback=callback, product_id=product_id, offers_page=1)
        except (StoreServiceError, GiftApiError) as error:
            await send_screen(message, render_store_error(error), build_store_home_keyboard(), callback=callback)
            await callback.answer(STOREFRONT_TEXT.CALLBACK_PRODUCT_UNAVAILABLE)
            return
        await callback.answer(STOREFRONT_TEXT.CALLBACK_PRODUCT_OPENED)

    @router.callback_query(F.data.startswith(STORE_DETAIL_OFFERS_PAGE_PREFIX))
    async def handle_product_offers_page(callback: CallbackQuery, state: FSMContext) -> None:
        message = extract_message(callback)
        if message is None:
            await callback.answer()
            return

        offers_page = parse_int_suffix(callback.data, STORE_DETAIL_OFFERS_PAGE_PREFIX, 1)
        data = await state.get_data()
        product_id = data.get("active_product_id")
        if not product_id:
            await callback.answer(STOREFRONT_TEXT.CALLBACK_REOPEN_PRODUCT)
            return

        try:
            await render_product_detail(message, state, container, callback=callback, product_id=str(product_id), offers_page=offers_page)
        except (StoreServiceError, GiftApiError) as error:
            await send_screen(message, render_store_error(error), build_store_home_keyboard(), callback=callback)
            await callback.answer(STOREFRONT_TEXT.CALLBACK_PRODUCT_UNAVAILABLE)
            return
        await callback.answer()

    @router.callback_query(F.data == STORE_DETAIL_BACK_ACTION)
    async def handle_detail_back(callback: CallbackQuery, state: FSMContext) -> None:
        message = extract_message(callback)
        if message is None:
            await callback.answer()
            return

        context = await state.get_data()
        view_type = context.get("current_view_type")
        await state.set_state(None)

        try:
            if view_type == "search":
                await render_search_results(message, state, container, callback=callback, page=int(context.get("search_page", 1)))
            elif view_type == "category":
                await render_products(
                    message,
                    state,
                    container,
                    callback=callback,
                    page=int(context.get("products_page", 1)),
                    category_id=int(context.get("current_category_id")),
                    categories_page=int(context.get("categories_page", 1)),
                )
            else:
                await render_store_home(message, state, container, callback=callback)
        except (StoreServiceError, GiftApiError) as error:
            await send_screen(message, render_store_error(error), build_store_home_keyboard(), callback=callback)
            await callback.answer(STOREFRONT_TEXT.CALLBACK_SCREEN_UNAVAILABLE)
            return
        await callback.answer()

    @router.callback_query(F.data == STORE_WALLET_ACTION)
    async def handle_wallet(callback: CallbackQuery, state: FSMContext) -> None:
        message = extract_message(callback)
        if message is None or callback.from_user is None:
            await callback.answer()
            return

        await container.store_service.ensure_user(callback.from_user)
        await state.set_state(None)
        await render_wallet_screen(message, state, container, callback=callback, telegram_id=callback.from_user.id)
        await callback.answer(STOREFRONT_TEXT.CALLBACK_WALLET_OPENED)

    @router.callback_query(F.data.startswith(STORE_TOP_UP_PREFIX))
    async def handle_top_up_fixed(callback: CallbackQuery, state: FSMContext) -> None:
        message = extract_message(callback)
        if message is None or callback.from_user is None:
            await callback.answer()
            return

        amount_text = callback.data.removeprefix(STORE_TOP_UP_PREFIX)
        amount = parse_decimal(amount_text)
        await callback.answer(STOREFRONT_TEXT.CALLBACK_PAYMENT_CREATING)
        try:
            payment_link = await container.payment_service.create_top_up_link(callback.from_user, amount)
        except (PaymentFlowError, PaymentConfigurationError, StoreServiceError) as error:
            await send_screen(message, render_store_error(error), build_wallet_keyboard(), callback=callback)
            return

        await state.set_state(None)
        try:
            await send_top_up_link(message, payment_link)
        except (TelegramBadRequest, TelegramNetworkError) as error:
            await send_screen(message, render_store_error(error), build_wallet_keyboard(), callback=callback)
            return

    @router.callback_query(F.data == STORE_TOP_UP_CUSTOM_ACTION)
    async def handle_top_up_custom_prompt(callback: CallbackQuery, state: FSMContext) -> None:
        message = extract_message(callback)
        if message is None:
            await callback.answer()
            return

        await state.set_state(StorefrontStates.waiting_for_top_up_amount)
        await message.answer(
            STOREFRONT_TEXT.TOP_UP_CUSTOM_PROMPT,
            reply_markup=build_wallet_keyboard(),
        )
        await callback.answer(STOREFRONT_TEXT.CALLBACK_TOP_UP_AMOUNT_READY)

    @router.message(StorefrontStates.waiting_for_top_up_amount)
    async def handle_top_up_custom_amount(message: Message, state: FSMContext) -> None:
        if message.from_user is None:
            return

        try:
            amount = parse_decimal(message.text or "")
            payment_link = await container.payment_service.create_top_up_link(message.from_user, amount)
        except (PaymentFlowError, PaymentConfigurationError, StoreServiceError, ValueError) as error:
            await message.answer(render_store_error(error), reply_markup=build_wallet_keyboard())
            return

        await state.set_state(None)
        try:
            await send_top_up_link(message, payment_link)
        except (TelegramBadRequest, TelegramNetworkError) as error:
            await message.answer(render_store_error(error), reply_markup=build_wallet_keyboard())

    @router.callback_query(F.data.startswith(STORE_BUY_SKU_PREFIX))
    async def handle_buy_sku(callback: CallbackQuery, state: FSMContext) -> None:
        message = extract_message(callback)
        if message is None or callback.from_user is None:
            await callback.answer()
            return

        data = await state.get_data()
        product_id = data.get("active_product_id")
        if not product_id:
            await callback.answer(STOREFRONT_TEXT.CALLBACK_REOPEN_PRODUCT)
            return

        sku_id = callback.data.removeprefix(STORE_BUY_SKU_PREFIX)
        try:
            result = await container.store_service.purchase_offer(
                callback.from_user,
                product_id=str(product_id),
                sku_id=sku_id,
            )
        except (StoreServiceError, GiftApiError) as error:
            await send_screen(message, render_store_error(error), build_wallet_keyboard(), callback=callback)
            await callback.answer(STOREFRONT_TEXT.CALLBACK_PURCHASE_FAILED)
            return

        await state.set_state(None)
        await send_screen(
            message,
            render_purchase_result(result),
            build_order_detail_keyboard(),
            callback=callback,
        )
        await callback.answer(STOREFRONT_TEXT.CALLBACK_ORDER_CREATED)

    @router.callback_query(F.data == STORE_ORDERS_ACTION)
    async def handle_orders(callback: CallbackQuery, state: FSMContext) -> None:
        message = extract_message(callback)
        if message is None or callback.from_user is None:
            await callback.answer()
            return

        await state.set_state(None)
        await render_orders(message, state, container, callback=callback, telegram_id=callback.from_user.id, page=1)
        await callback.answer(STOREFRONT_TEXT.CALLBACK_ORDERS_HISTORY)

    @router.callback_query(F.data.startswith(STORE_ORDERS_PAGE_PREFIX))
    async def handle_orders_page(callback: CallbackQuery, state: FSMContext) -> None:
        message = extract_message(callback)
        if message is None or callback.from_user is None:
            await callback.answer()
            return

        page = parse_int_suffix(callback.data, STORE_ORDERS_PAGE_PREFIX, 1)
        await state.set_state(None)
        await render_orders(message, state, container, callback=callback, telegram_id=callback.from_user.id, page=page)
        await callback.answer()

    @router.callback_query(F.data.startswith(STORE_ORDER_ACTION_PREFIX))
    async def handle_order_detail(callback: CallbackQuery, state: FSMContext) -> None:
        message = extract_message(callback)
        if message is None or callback.from_user is None:
            await callback.answer()
            return

        order_id = parse_int_suffix(callback.data, STORE_ORDER_ACTION_PREFIX)
        order = await container.store_service.get_order_view(callback.from_user.id, order_id)
        if order is None:
            await callback.answer(STOREFRONT_TEXT.CALLBACK_ORDER_NOT_FOUND)
            return

        await state.set_state(None)
        await send_screen(message, render_order_detail(order), build_order_detail_keyboard(), callback=callback)
        await callback.answer(STOREFRONT_TEXT.CALLBACK_ORDER_DETAILS)

    @router.callback_query(F.data == "noop")
    async def handle_noop(callback: CallbackQuery) -> None:
        await callback.answer()

    @router.callback_query(F.data.startswith(STORE_FIELD_FILL_PREFIX))
    async def handle_field_fill_start(callback: CallbackQuery, state: FSMContext) -> None:
        """Начало сбора required_fields: запрашиваем первое поле у пользователя."""
        message = extract_message(callback)
        if message is None or callback.from_user is None:
            await callback.answer()
            return

        data = await state.get_data()
        product_id = data.get("active_product_id")
        if not product_id:
            await callback.answer(STOREFRONT_TEXT.CALLBACK_REOPEN_PRODUCT)
            return

        sku_id = callback.data.removeprefix(STORE_FIELD_FILL_PREFIX)
        try:
            product = await container.store_service.get_product_view(str(product_id))
        except (StoreServiceError, GiftApiError) as error:
            await callback.answer(str(error), show_alert=True)
            return

        offer = next((o for o in product.offers if o.sku_id == sku_id), None)
        if offer is None or not offer.buyable:
            await callback.answer(STOREFRONT_TEXT.CALLBACK_REOPEN_PRODUCT)
            return

        # Сериализуем поля для FSM (только не-auto коды)
        pending_fields = [
            {
                "code": getattr(f, "code", ""),
                "name": getattr(f, "name", ""),
                "description": getattr(f, "description", "") or "",
                "required": getattr(f, "required", True),
                "type": getattr(f, "field_type", "string"),
            }
            for f in offer.required_fields
        ]
        if not pending_fields:
            # Нет полей — сразу покупаем
            await callback.answer(STOREFRONT_TEXT.CALLBACK_FIELD_START)
            try:
                result = await container.store_service.purchase_offer(callback.from_user, product_id=str(product_id), sku_id=sku_id)
            except (StoreServiceError, GiftApiError) as error:
                await send_screen(message, render_store_error(error), build_wallet_keyboard(), callback=callback)
                return
            await state.set_state(None)
            await send_screen(message, render_purchase_result(result), build_order_detail_keyboard(), callback=callback)
            return

        await state.update_data(
            field_sku_id=sku_id,
            field_product_id=str(product_id),
            field_pending=pending_fields,
            field_values={},
        )
        await state.set_state(StorefrontStates.waiting_for_field_value)
        first_field = pending_fields[0]
        prompt = _build_field_prompt(first_field, done=0, total=len(pending_fields))
        await callback.answer(STOREFRONT_TEXT.CALLBACK_FIELD_START)
        await message.answer(prompt, reply_markup=build_field_input_keyboard())

    @router.message(StorefrontStates.waiting_for_field_value)
    async def handle_field_value(message: Message, state: FSMContext) -> None:
        """Принять значение поля, спросить следующее или запустить покупку."""
        if message.from_user is None:
            return

        data = await state.get_data()
        pending: list[dict] = list(data.get("field_pending") or [])
        values: dict = dict(data.get("field_values") or {})
        sku_id: str = str(data.get("field_sku_id") or "")
        product_id: str = str(data.get("field_product_id") or "")
        total_fields: int = len(pending)

        if not pending or not sku_id or not product_id:
            await state.clear()
            await message.answer(STOREFRONT_TEXT.CALLBACK_REOPEN_PRODUCT, reply_markup=build_store_home_keyboard())
            return

        current = pending.pop(0)
        raw_value = (message.text or "").strip()

        # «-» пропускает опциональное поле
        if raw_value == "-" and not current.get("required", True):
            pass  # не добавляем в values
        elif not raw_value:
            # Пустой ввод — повторить запрос
            done = total_fields - len(pending) - 1
            await message.answer(_build_field_prompt(current, done=done, total=total_fields), reply_markup=build_field_input_keyboard())
            return
        else:
            # Конвертируем значение в нужный тип (integer поля — числа)
            field_type = current.get("type", "string")
            if field_type == "integer":
                if not raw_value.lstrip("-").isdigit():
                    done = total_fields - len(pending) - 1
                    await message.answer(STOREFRONT_TEXT.FIELD_PROMPT_INTEGER_ERROR + "\n\n" + _build_field_prompt(current, done=done, total=total_fields), reply_markup=build_field_input_keyboard())
                    return
                values[current["code"]] = int(raw_value)
            else:
                values[current["code"]] = raw_value

        if pending:
            # Есть ещё поля
            await state.update_data(field_pending=pending, field_values=values)
            done = total_fields - len(pending)
            next_field = pending[0]
            await message.answer(_build_field_prompt(next_field, done=done, total=total_fields), reply_markup=build_field_input_keyboard())
            return

        # Все поля собраны — делаем покупку
        await state.set_state(None)
        try:
            result = await container.store_service.purchase_offer(
                message.from_user,
                product_id=product_id,
                sku_id=sku_id,
                customer_fields=values,
            )
        except (StoreServiceError, GiftApiError) as error:
            await message.answer(render_store_error(error), reply_markup=build_wallet_keyboard())
            return

        await state.clear()
        await message.answer(render_purchase_result(result), reply_markup=build_order_detail_keyboard())

    @router.callback_query(F.data == STORE_FIELD_CANCEL_ACTION)
    async def handle_field_cancel(callback: CallbackQuery, state: FSMContext) -> None:
        """Отмена ввода required_fields — возврат на карточку товара."""
        message = extract_message(callback)
        if message is None:
            await callback.answer()
            return

        data = await state.get_data()
        product_id = data.get("field_product_id") or data.get("active_product_id")
        await state.clear()
        await callback.answer(STOREFRONT_TEXT.CALLBACK_FIELD_CANCELED)

        if product_id:
            try:
                await render_product_detail(message, state, container, product_id=str(product_id), offers_page=1, callback=callback)
                return
            except (StoreServiceError, GiftApiError):
                pass
        await send_screen(message, STOREFRONT_TEXT.STORE_TITLE, build_store_home_keyboard(), callback=callback)

    return router


async def render_store_home(
    message: Message,
    state: FSMContext,
    container: AppContainer,
    *,
    callback: CallbackQuery | None = None,
) -> None:
    if callback is None or callback.from_user is None:
        telegram_id = message.chat.id
    else:
        telegram_id = callback.from_user.id
    dashboard = await container.store_service.get_dashboard(telegram_id)
    await state.update_data(current_view_type="home")
    await send_screen(message, render_dashboard(dashboard), build_store_home_keyboard(), callback=callback)


async def render_categories(
    message: Message,
    state: FSMContext,
    container: AppContainer,
    *,
    page: int,
    callback: CallbackQuery | None = None,
) -> None:
    categories, page_info = await container.store_service.get_categories_page(page, per_page=CATEGORIES_PER_PAGE)
    await state.update_data(current_view_type="categories", categories_page=page_info.page)
    await send_screen(message, render_categories_screen(categories, page_info), build_categories_keyboard(categories, page_info), callback=callback)


async def render_products(
    message: Message,
    state: FSMContext,
    container: AppContainer,
    *,
    page: int,
    category_id: int | None,
    categories_page: int,
    callback: CallbackQuery | None = None,
) -> None:
    products, page_info = await container.store_service.get_products_page(
        page=page,
        per_page=PRODUCTS_PER_PAGE,
        category_id=category_id,
    )
    await state.update_data(
        current_view_type="category",
        current_category_id=category_id,
        products_page=page_info.page,
        categories_page=categories_page,
    )
    previous_callback = f"{STORE_PRODUCTS_PAGE_PREFIX}{page_info.page - 1}" if page_info.has_previous else None
    next_callback = f"{STORE_PRODUCTS_PAGE_PREFIX}{page_info.page + 1}" if page_info.has_next else None
    back_callback = f"{STORE_CATEGORIES_PAGE_PREFIX}{categories_page}"
    await send_screen(
        message,
        render_products_screen(products, page_info, title=STOREFRONT_TEXT.CATALOG_TITLE),
        build_products_keyboard(
            products,
            page_info,
            previous_callback=previous_callback,
            next_callback=next_callback,
            back_callback=back_callback,
        ),
        callback=callback,
    )


async def render_search_results(
    message: Message,
    state: FSMContext,
    container: AppContainer,
    *,
    page: int,
    callback: CallbackQuery | None = None,
) -> None:
    data = await state.get_data()
    search_query = str(data.get("search_query") or "").strip()
    if not search_query:
        await send_screen(
            message,
            STOREFRONT_TEXT.search_enter_first(),
            build_store_home_keyboard(),
            callback=callback,
        )
        return

    try:
        products, page_info = await container.store_service.get_products_page(
            page=page,
            per_page=PRODUCTS_PER_PAGE,
            search_query=search_query,
        )
    except SearchQueryError as error:
        await send_screen(message, render_store_error(error), build_store_home_keyboard(), callback=callback)
        return

    await state.update_data(current_view_type="search", search_page=page_info.page, search_query=search_query)
    previous_callback = f"{STORE_SEARCH_PAGE_PREFIX}{page_info.page - 1}" if page_info.has_previous else None
    next_callback = f"{STORE_SEARCH_PAGE_PREFIX}{page_info.page + 1}" if page_info.has_next else None
    await send_screen(
        message,
        render_products_screen(products, page_info, title=STOREFRONT_TEXT.PRODUCT_TITLE_PREFIX.format(query=search_query)),
        build_products_keyboard(
            products,
            page_info,
            previous_callback=previous_callback,
            next_callback=next_callback,
            back_callback=STORE_HOME_ACTION,
        ),
        callback=callback,
    )


async def render_product_detail(
    message: Message,
    state: FSMContext,
    container: AppContainer,
    *,
    product_id: str,
    offers_page: int,
    callback: CallbackQuery | None = None,
) -> None:
    product = await container.store_service.get_product_view(product_id)
    offers_subset, page_info = paginate_offers(product.offers, offers_page)
    await state.update_data(active_product_id=product_id, active_offer_page=page_info.page)
    await send_screen(
        message,
        render_product_detail_screen(product, offers_subset, page_info),
        build_product_detail_keyboard(offers_subset, page_info, back_callback=STORE_DETAIL_BACK_ACTION),
        callback=callback,
    )


async def render_wallet_screen(
    message: Message,
    state: FSMContext,
    container: AppContainer,
    *,
    telegram_id: int,
    callback: CallbackQuery | None = None,
) -> None:
    wallet = await container.store_service.get_wallet_snapshot(telegram_id)
    await state.update_data(current_view_type="wallet")
    await send_screen(message, render_wallet_text(wallet), build_wallet_keyboard(), callback=callback)


async def render_orders(
    message: Message,
    state: FSMContext,
    container: AppContainer,
    *,
    telegram_id: int,
    page: int,
    callback: CallbackQuery | None = None,
) -> None:
    orders, page_info = await container.store_service.get_orders_page(telegram_id, page=page, per_page=ORDERS_PER_PAGE)
    await state.update_data(current_view_type="orders", orders_page=page_info.page)
    await send_screen(message, render_orders_screen(orders, page_info), build_orders_keyboard(orders, page_info), callback=callback)


async def send_screen(
    message: Message,
    text: str,
    reply_markup: InlineKeyboardMarkup,
    *,
    callback: CallbackQuery | None = None,
) -> None:
    if callback is not None and callback.message is not None and callback.message.text:
        try:
            await callback.message.edit_text(text, reply_markup=reply_markup)
            return
        except TelegramBadRequest:
            pass

    await message.answer(text, reply_markup=reply_markup)


def render_dashboard(dashboard: StoreDashboard) -> str:
    return "\n".join(
        [
            STOREFRONT_TEXT.STORE_TITLE,
            STOREFRONT_TEXT.STORE_DESCRIPTION,
            "",
            STOREFRONT_TEXT.STORE_CATEGORIES.format(count=dashboard.category_count),
            STOREFRONT_TEXT.STORE_PRODUCTS.format(count=dashboard.product_count),
            STOREFRONT_TEXT.STORE_AVAILABLE.format(amount=escape(format_money(dashboard.balance, dashboard.currency))),
            STOREFRONT_TEXT.STORE_HELD.format(amount=escape(format_money(dashboard.held_balance, dashboard.currency))),
            STOREFRONT_TEXT.STORE_TOTAL.format(amount=escape(format_money(dashboard.total_balance, dashboard.currency))),
            STOREFRONT_TEXT.STORE_EQUIVALENT.format(
                usdt_amount=escape(format_money(dashboard.total_quote.usdt_amount, 'USDT')),
                rub_amount=escape(format_money(dashboard.total_quote.rub_amount, 'RUB')),
            ),
            STOREFRONT_TEXT.STORE_ORDER_COUNT.format(count=dashboard.order_count),
            "",
            STOREFRONT_TEXT.STORE_HINT,
        ]
    )


def render_categories_screen(categories: tuple[object, ...], page_info: PageInfo) -> str:
    lines = [STOREFRONT_TEXT.CATEGORIES_TITLE, STOREFRONT_TEXT.PAGE_OF.format(page=page_info.page, total_pages=page_info.total_pages)]
    if not categories:
        lines.append(STOREFRONT_TEXT.CATEGORIES_EMPTY)
        return "\n".join(lines)

    for category in categories:
        lines.append(STOREFRONT_TEXT.CATEGORY_ROW.format(name=escape(category.name), count=category.product_count))
    return "\n".join(lines)


def render_products_screen(products: tuple[StoreProductCard, ...], page_info: PageInfo, *, title: str) -> str:
    lines = [f"<b>{escape(title)}</b>", STOREFRONT_TEXT.PAGE_OF.format(page=page_info.page, total_pages=page_info.total_pages)]
    if not products:
        lines.append(STOREFRONT_TEXT.PRODUCTS_EMPTY)
        return "\n".join(lines)

    for product in products:
        lines.append("")
        lines.append(f"<b>{escape(product.name)}</b>")
        if product.category_name:
            lines.append(STOREFRONT_TEXT.PRODUCT_CATEGORY.format(value=escape(product.category_name)))
        lines.append(STOREFRONT_TEXT.PRODUCT_TYPE.format(value=escape(product.product_type)))
        lines.append(STOREFRONT_TEXT.PRODUCT_PRICE.format(value=escape(format_price_range(product))))
        lines.append(STOREFRONT_TEXT.PRODUCT_SKU.format(sku_count=product.sku_count, buyable_sku_count=product.buyable_sku_count))
        lines.append(STOREFRONT_TEXT.PRODUCT_STOCK.format(stock=product.total_stock))
        if product.summary:
            lines.append(escape(product.summary))
    return "\n".join(lines)


def render_product_detail_screen(product: StoreProductView, offers: tuple[StoreProductOffer, ...], page_info: PageInfo) -> str:
    lines = [f"<b>{escape(product.name)}</b>"]
    if product.category_name:
        lines.append(STOREFRONT_TEXT.PRODUCT_CATEGORY.format(value=escape(product.category_name)))
    lines.append(STOREFRONT_TEXT.PRODUCT_TYPE.format(value=escape(product.product_type)))
    if product.denomination_type:
        lines.append(STOREFRONT_TEXT.PRODUCT_DENOMINATION.format(value=escape(product.denomination_type)))
    if product.description:
        lines.append("")
        lines.append(escape(product.description))

    # Показываем только те поля, которые нужно запрашивать у пользователя (не auto-заполняемые)
    user_fields = [
        f for f in product.required_fields
        if getattr(f, 'code', None) not in SUPPORTED_AUTO_FIELDS
    ]
    if user_fields:
        lines.append("")
        lines.append(STOREFRONT_TEXT.PRODUCT_FIELDS_TITLE)
        for field in user_fields[:6]:
            req_mark = "*" if getattr(field, 'required', True) else ""
            lines.append(
                STOREFRONT_TEXT.PRODUCT_FIELD.format(
                    name=escape(getattr(field, 'name', getattr(field, 'code', 'field'))) + req_mark,
                    code=escape(getattr(field, 'code', 'field')),
                )
            )

    lines.append("")
    lines.append(STOREFRONT_TEXT.PRODUCT_OFFERS_TITLE.format(page=page_info.page, total_pages=page_info.total_pages))
    if not offers:
        lines.append(STOREFRONT_TEXT.PRODUCT_OFFERS_EMPTY)
        return "\n".join(lines)

    for offer in offers:
        if offer.buyable and offer.required_fields:
            status = STOREFRONT_TEXT.PRODUCT_OFFER_NEED_FIELDS
        elif offer.buyable:
            status = STOREFRONT_TEXT.PRODUCT_OFFER_AVAILABLE
        else:
            status = offer.reason_unavailable or STOREFRONT_TEXT.PRODUCT_OFFER_UNAVAILABLE
        price_text = format_money(offer.price, offer.currency) if offer.price is not None else STORE_KEYBOARD_TEXT.PRICE_ON_REQUEST
        lines.append("")
        lines.append(f"<b>{escape(offer.name)}</b>")
        lines.append(STOREFRONT_TEXT.PRODUCT_OFFER_PRICE.format(value=escape(price_text)))
        lines.append(STOREFRONT_TEXT.PRODUCT_OFFER_STOCK.format(stock=offer.stock))
        if offer.max_per_order is not None:
            lines.append(STOREFRONT_TEXT.PRODUCT_OFFER_MAX.format(value=offer.max_per_order))
        lines.append(STOREFRONT_TEXT.PRODUCT_OFFER_STATUS.format(value=escape(status)))
    return "\n".join(lines)


def render_wallet_text(wallet: WalletSnapshot, title: str = STOREFRONT_TEXT.WALLET_TITLE) -> str:
    lines = [f"<b>{escape(title)}</b>"]
    lines.append(STOREFRONT_TEXT.WALLET_AVAILABLE.format(amount=escape(format_money(wallet.balance, wallet.currency))))
    lines.append(STOREFRONT_TEXT.WALLET_HELD.format(amount=escape(format_money(wallet.held_balance, wallet.currency))))
    lines.append(STOREFRONT_TEXT.WALLET_TOTAL.format(amount=escape(format_money(wallet.total_balance, wallet.currency))))
    lines.append(
        STOREFRONT_TEXT.WALLET_EQUIVALENT.format(
            usdt_amount=escape(format_money(wallet.total_quote.usdt_amount, 'USDT')),
            rub_amount=escape(format_money(wallet.total_quote.rub_amount, 'RUB')),
        )
    )
    lines.append(STOREFRONT_TEXT.WALLET_RATE.format(amount=escape(format_money(wallet.total_quote.usdt_rub_rate, 'RUB'))))
    lines.append(STOREFRONT_TEXT.WALLET_ORDER_COUNT.format(count=wallet.order_count))
    lines.append(STOREFRONT_TEXT.WALLET_NICEPAY_INFO)
    lines.append("")
    lines.append(STOREFRONT_TEXT.WALLET_RECENT_TITLE)

    if not wallet.recent_transactions:
        lines.append(STOREFRONT_TEXT.WALLET_RECENT_EMPTY)
        return "\n".join(lines)

    for transaction in wallet.recent_transactions:
        timestamp = transaction.created_at.astimezone(timezone.utc).strftime("%d.%m %H:%M UTC")
        lines.append(
            STOREFRONT_TEXT.WALLET_TRANSACTION.format(
                created_at=escape(timestamp),
                transaction_type=escape(transaction.transaction_type),
                amount=escape(format_money(transaction.amount, transaction.currency)),
            )
        )
        lines.append(escape(transaction.description))
    return "\n".join(lines)


def render_orders_screen(orders: tuple[StoreOrderCard, ...], page_info: PageInfo) -> str:
    lines = [STOREFRONT_TEXT.ORDERS_TITLE, STOREFRONT_TEXT.PAGE_OF.format(page=page_info.page, total_pages=page_info.total_pages)]
    if not orders:
        lines.append(STOREFRONT_TEXT.ORDERS_EMPTY)
        return "\n".join(lines)

    for order in orders:
        created_at = order.created_at.astimezone(timezone.utc).strftime("%d.%m.%Y %H:%M UTC")
        lines.append("")
        lines.append(STOREFRONT_TEXT.ORDER_TITLE.format(order_id=order.order_id, product_name=escape(order.product_name)))
        lines.append(STOREFRONT_TEXT.ORDER_SKU.format(sku_name=escape(order.sku_name)))
        lines.append(STOREFRONT_TEXT.ORDER_STATUS.format(status=escape(order.status)))
        lines.append(STOREFRONT_TEXT.ORDER_TOTAL.format(amount=escape(format_money(order.total_amount, order.currency))))
        lines.append(STOREFRONT_TEXT.ORDER_CREATED.format(created_at=escape(created_at)))
    return "\n".join(lines)


def render_order_detail(order: StoreOrderView) -> str:
    created_at = order.created_at.astimezone(timezone.utc).strftime("%d.%m.%Y %H:%M UTC")
    lines = [STOREFRONT_TEXT.ORDER_DETAIL_TITLE.format(order_id=order.order_id)]
    lines.append(STOREFRONT_TEXT.ORDER_EXTERNAL_ID.format(external_id=escape(order.external_id)))
    if order.provider_order_id:
        lines.append(STOREFRONT_TEXT.ORDER_PROVIDER_ID.format(provider_order_id=escape(order.provider_order_id)))
    lines.append(STOREFRONT_TEXT.ORDER_PROVIDER.format(provider=escape(order.provider)))
    lines.append(STOREFRONT_TEXT.ORDER_PRODUCT.format(product_name=escape(order.product_name)))
    lines.append(STOREFRONT_TEXT.ORDER_SKU.format(sku_name=escape(order.sku_name)))
    lines.append(STOREFRONT_TEXT.ORDER_STATUS.format(status=escape(order.status)))
    lines.append(STOREFRONT_TEXT.ORDER_TOTAL.format(amount=escape(format_money(order.total_amount, order.currency))))
    lines.append(STOREFRONT_TEXT.ORDER_CREATED.format(created_at=escape(created_at)))
    if order.delivery_payload:
        lines.append("")
        lines.append(STOREFRONT_TEXT.ORDER_DELIVERY_TITLE)
        lines.append(f"<pre>{escape(pretty_json(order.delivery_payload))}</pre>")
    if order.error_message:
        lines.append("")
        lines.append(STOREFRONT_TEXT.ORDER_ERROR.format(error_message=escape(order.error_message)))
    return "\n".join(lines)


def render_purchase_result(result: PurchaseResult) -> str:
    order = result.order
    lines = [STOREFRONT_TEXT.PURCHASE_TITLE]
    lines.append(STOREFRONT_TEXT.PURCHASE_ORDER.format(order_id=order.order_id, status=escape(order.status)))
    lines.append(STOREFRONT_TEXT.PURCHASE_PRODUCT.format(product_name=escape(order.product_name)))
    lines.append(STOREFRONT_TEXT.PURCHASE_SKU.format(sku_name=escape(order.sku_name)))
    lines.append(STOREFRONT_TEXT.PURCHASE_CHARGED.format(amount=escape(format_money(order.total_amount, order.currency))))
    lines.append(STOREFRONT_TEXT.PURCHASE_BALANCE_AFTER.format(amount=escape(format_money(result.balance_after, result.currency))))
    if order.delivery_payload:
        lines.append("")
        lines.append(STOREFRONT_TEXT.PURCHASE_DELIVERY_TITLE)
        lines.append(f"<pre>{escape(pretty_json(order.delivery_payload))}</pre>")
    return "\n".join(lines)


def render_store_error(error: Exception) -> str:
    return STOREFRONT_TEXT.store_error(escape(str(error)))


def format_price_range(product: StoreProductCard) -> str:
    if product.min_price is None or product.currency is None:
        return STORE_KEYBOARD_TEXT.PRICE_ON_REQUEST
    if product.max_price is None or product.max_price == product.min_price:
        return format_money(product.min_price, product.currency)
    return STORE_KEYBOARD_TEXT.price_from(format_money(product.min_price, product.currency))


def paginate_offers(offers: tuple[StoreProductOffer, ...], page: int) -> tuple[tuple[StoreProductOffer, ...], PageInfo]:
    page_info = build_page_info(total_items=len(offers), page=page, per_page=OFFERS_PER_PAGE)
    start = (page_info.page - 1) * page_info.per_page
    end = start + page_info.per_page
    return offers[start:end], page_info


def parse_int_suffix(value: str, prefix: str, default: int | None = None) -> int:
    raw = value.removeprefix(prefix)
    try:
        return int(raw)
    except ValueError:
        if default is None:
            raise
        return default


def parse_decimal(value: str) -> Decimal:
    normalized = value.replace(",", ".").strip()
    if not normalized:
        raise ValueError(STOREFRONT_TEXT.ENTER_TOP_UP_AMOUNT)
    try:
        amount = Decimal(normalized)
    except InvalidOperation as error:
        raise ValueError(STOREFRONT_TEXT.INVALID_TOP_UP_AMOUNT) from error
    return amount.quantize(Decimal("0.01"))


def _build_field_prompt(field: dict, *, done: int, total: int) -> str:
    """Формирует текст запроса значения для одного required_field."""
    name = escape(field.get("name") or field.get("code") or "поле")
    description = field.get("description") or ""
    required = field.get("required", True)
    progress = STOREFRONT_TEXT.FIELD_PROGRESS.format(done=done, total=total)
    lines = [f"{progress}"]
    prompt = STOREFRONT_TEXT.FIELD_PROMPT.format(name=name)
    if not required:
        prompt += STOREFRONT_TEXT.FIELD_PROMPT_OPTIONAL
    lines.append(prompt)
    if description:
        lines.append(STOREFRONT_TEXT.FIELD_PROMPT_DESCRIPTION.format(description=escape(description)))
    return "\n".join(lines)

def pretty_json(raw_payload: str) -> str:
    try:
        payload = json.loads(raw_payload)
    except json.JSONDecodeError:
        return raw_payload
    return json.dumps(payload, ensure_ascii=False, indent=2)


async def send_top_up_link(message: Message, payment_link) -> None:
    expires_at = payment_link.expires_at
    expires_text = STOREFRONT_TEXT.PAYMENT_LINK_EXPIRES_UNKNOWN
    if hasattr(expires_at, "astimezone"):
        expires_text = expires_at.astimezone(timezone.utc).strftime("%d.%m.%Y %H:%M UTC")
    await message.answer(
        "\n".join(
            [
                STOREFRONT_TEXT.PAYMENT_LINK_TITLE,
                STOREFRONT_TEXT.PAYMENT_LINK_AMOUNT.format(amount=escape(format_money(payment_link.amount, payment_link.currency))),
                STOREFRONT_TEXT.PAYMENT_LINK_ESTIMATED.format(amount=escape(format_money(payment_link.estimated_wallet_amount, payment_link.wallet_currency))),
                STOREFRONT_TEXT.PAYMENT_LINK_ID.format(payment_id=escape(payment_link.payment_id)),
                STOREFRONT_TEXT.PAYMENT_LINK_EXPIRES.format(expires_at=escape(expires_text)),
                STOREFRONT_TEXT.PAYMENT_LINK_AUTO_UPDATE,
            ]
        ),
        reply_markup=build_payment_link_keyboard(payment_link.payment_url),
    )


def build_payment_link_keyboard(payment_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=STORE_KEYBOARD_TEXT.PAY_WITH_NICEPAY, url=payment_url)],
            [
                InlineKeyboardButton(text=STORE_KEYBOARD_TEXT.WALLET, callback_data=STORE_WALLET_ACTION),
                InlineKeyboardButton(text=STORE_KEYBOARD_TEXT.HOME, callback_data=STORE_HOME_ACTION),
            ],
        ]
    )