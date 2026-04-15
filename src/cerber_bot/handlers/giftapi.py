"""Обработчики раздела GiftAPI.

Отдельный раздел для прямой работы с партнёрским сервисом GiftAPI:
профиль, категории, товары, заказы, eSIM-статус.
"""

from __future__ import annotations

import json
import re
from datetime import timezone
from decimal import Decimal
from html import escape

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from cerber_bot.container import AppContainer
from cerber_bot.handlers.menu import extract_message, shorten_text
from cerber_bot.integrations.giftapi import (
    GiftApiConfigurationError,
    GiftApiError,
    GiftCategory,
    GiftEsimStatus,
    GiftOrder,
    GiftPartner,
    GiftProductDetail,
    GiftProductSummary,
)
from cerber_bot.keyboards.giftapi_menu import (
    GIFTAPI_BACK_ACTION,
    GIFTAPI_CATEGORIES_ACTION,
    GIFTAPI_CREATE_ORDER_ACTION,
    GIFTAPI_ESIM_ACTION,
    GIFTAPI_MENU_ACTION,
    GIFTAPI_ORDER_LOOKUP_ACTION,
    GIFTAPI_ORDERS_ACTION,
    GIFTAPI_OVERVIEW_ACTION,
    GIFTAPI_PRODUCT_LOOKUP_ACTION,
    GIFTAPI_PRODUCTS_ACTION,
    build_giftapi_menu,
)
from cerber_bot.keyboards.main_menu import build_main_menu
from cerber_bot.services.store import format_money
from cerber_bot.texts import COMMON_TEXT, GIFTAPI_TEXT


HTML_TAG_RE = re.compile(r"<[^>]+>")


class GiftApiStates(StatesGroup):
    waiting_for_product_uuid = State()
    waiting_for_order_uuid = State()
    waiting_for_esim_iccid = State()
    waiting_for_order_payload = State()


def build_giftapi_router(container: AppContainer) -> Router:
    router = Router(name="giftapi")

    @router.callback_query(F.data == GIFTAPI_MENU_ACTION)
    async def handle_menu(callback: CallbackQuery, state: FSMContext) -> None:
        message = extract_message(callback)
        if message is None:
            await callback.answer()
            return

        await state.clear()
        await message.answer(render_menu_intro(container), reply_markup=build_giftapi_menu())
        await callback.answer(GIFTAPI_TEXT.CALLBACK_OPENED)

    @router.callback_query(F.data == GIFTAPI_OVERVIEW_ACTION)
    async def handle_overview(callback: CallbackQuery, state: FSMContext) -> None:
        message = extract_message(callback)
        if message is None:
            await callback.answer()
            return

        await state.clear()
        if not await ensure_configured(message, container, callback):
            return

        try:
            overview = await container.gift_api_service.get_overview()
        except GiftApiError as error:
            await answer_giftapi_error(message, error)
            await callback.answer(GIFTAPI_TEXT.CALLBACK_ERROR)
            return

        await message.answer(render_overview(overview.partner, overview.recent_transactions), reply_markup=build_giftapi_menu())
        await callback.answer(GIFTAPI_TEXT.CALLBACK_OVERVIEW_LOADED)

    @router.callback_query(F.data == GIFTAPI_CATEGORIES_ACTION)
    async def handle_categories(callback: CallbackQuery, state: FSMContext) -> None:
        message = extract_message(callback)
        if message is None:
            await callback.answer()
            return

        await state.clear()
        if not await ensure_configured(message, container, callback):
            return

        try:
            categories = await container.gift_api_service.get_categories()
        except GiftApiError as error:
            await answer_giftapi_error(message, error)
            await callback.answer(GIFTAPI_TEXT.CALLBACK_ERROR)
            return

        await message.answer(render_categories(categories), reply_markup=build_giftapi_menu())
        await callback.answer(GIFTAPI_TEXT.CALLBACK_CATEGORIES_LOADED)

    @router.callback_query(F.data == GIFTAPI_PRODUCTS_ACTION)
    async def handle_products(callback: CallbackQuery, state: FSMContext) -> None:
        message = extract_message(callback)
        if message is None:
            await callback.answer()
            return

        await state.clear()
        if not await ensure_configured(message, container, callback):
            return

        try:
            products, meta = await container.gift_api_service.get_products()
        except GiftApiError as error:
            await answer_giftapi_error(message, error)
            await callback.answer(GIFTAPI_TEXT.CALLBACK_ERROR)
            return

        await message.answer(render_products(products, has_more=meta.next_cursor is not None), reply_markup=build_giftapi_menu())
        await callback.answer(GIFTAPI_TEXT.CALLBACK_PRODUCTS_LOADED)

    @router.callback_query(F.data == GIFTAPI_PRODUCT_LOOKUP_ACTION)
    async def handle_product_lookup(callback: CallbackQuery, state: FSMContext) -> None:
        message = extract_message(callback)
        if message is None:
            await callback.answer()
            return

        await state.set_state(GiftApiStates.waiting_for_product_uuid)
        await message.answer(
            GIFTAPI_TEXT.PRODUCT_LOOKUP_PROMPT,
            reply_markup=build_giftapi_menu(),
        )
        await callback.answer(GIFTAPI_TEXT.CALLBACK_PRODUCT_UUID_READY)

    @router.callback_query(F.data == GIFTAPI_ORDERS_ACTION)
    async def handle_orders(callback: CallbackQuery, state: FSMContext) -> None:
        message = extract_message(callback)
        if message is None:
            await callback.answer()
            return

        await state.clear()
        if not await ensure_configured(message, container, callback):
            return

        try:
            orders, meta = await container.gift_api_service.get_orders()
        except GiftApiError as error:
            await answer_giftapi_error(message, error)
            await callback.answer(GIFTAPI_TEXT.CALLBACK_ERROR)
            return

        await message.answer(render_orders(orders, has_more=meta.next_cursor is not None), reply_markup=build_giftapi_menu())
        await callback.answer(GIFTAPI_TEXT.CALLBACK_ORDERS_LOADED)

    @router.callback_query(F.data == GIFTAPI_ORDER_LOOKUP_ACTION)
    async def handle_order_lookup(callback: CallbackQuery, state: FSMContext) -> None:
        message = extract_message(callback)
        if message is None:
            await callback.answer()
            return

        await state.set_state(GiftApiStates.waiting_for_order_uuid)
        await message.answer(
            GIFTAPI_TEXT.ORDER_LOOKUP_PROMPT,
            reply_markup=build_giftapi_menu(),
        )
        await callback.answer(GIFTAPI_TEXT.CALLBACK_ORDER_UUID_READY)

    @router.callback_query(F.data == GIFTAPI_CREATE_ORDER_ACTION)
    async def handle_create_order(callback: CallbackQuery, state: FSMContext) -> None:
        message = extract_message(callback)
        if message is None:
            await callback.answer()
            return

        await state.set_state(GiftApiStates.waiting_for_order_payload)
        await message.answer(render_order_creation_prompt(), reply_markup=build_giftapi_menu())
        await callback.answer(GIFTAPI_TEXT.CALLBACK_ORDER_JSON_READY)

    @router.callback_query(F.data == GIFTAPI_ESIM_ACTION)
    async def handle_esim_prompt(callback: CallbackQuery, state: FSMContext) -> None:
        message = extract_message(callback)
        if message is None:
            await callback.answer()
            return

        await state.set_state(GiftApiStates.waiting_for_esim_iccid)
        await message.answer(
            GIFTAPI_TEXT.ESIM_PROMPT,
            reply_markup=build_giftapi_menu(),
        )
        await callback.answer(GIFTAPI_TEXT.CALLBACK_ESIM_READY)

    @router.callback_query(F.data == GIFTAPI_BACK_ACTION)
    async def handle_back(callback: CallbackQuery, state: FSMContext) -> None:
        message = extract_message(callback)
        if message is None:
            await callback.answer()
            return

        await state.clear()
        await message.answer(GIFTAPI_TEXT.MAIN_MENU_TITLE, reply_markup=build_main_menu(container.settings))
        await callback.answer(GIFTAPI_TEXT.CALLBACK_MAIN_MENU)

    @router.message(GiftApiStates.waiting_for_product_uuid)
    async def handle_product_uuid(message: Message, state: FSMContext) -> None:
        if not await ensure_configured(message, container):
            await state.clear()
            return
        if is_cancel_message(message):
            await state.clear()
            await message.answer(GIFTAPI_TEXT.ACTION_CANCELED, reply_markup=build_giftapi_menu())
            return

        product_uuid = (message.text or "").strip()
        if not product_uuid:
            await message.answer(GIFTAPI_TEXT.PRODUCT_UUID_INVALID, reply_markup=build_giftapi_menu())
            return

        try:
            product = await container.gift_api_service.get_product_detail(product_uuid)
        except GiftApiError as error:
            await answer_giftapi_error(message, error)
            return

        await state.clear()
        await message.answer(render_product_detail(product), reply_markup=build_giftapi_menu())

    @router.message(GiftApiStates.waiting_for_order_uuid)
    async def handle_order_uuid(message: Message, state: FSMContext) -> None:
        if not await ensure_configured(message, container):
            await state.clear()
            return
        if is_cancel_message(message):
            await state.clear()
            await message.answer(GIFTAPI_TEXT.ACTION_CANCELED, reply_markup=build_giftapi_menu())
            return

        order_uuid = (message.text or "").strip()
        if not order_uuid:
            await message.answer(GIFTAPI_TEXT.ORDER_UUID_INVALID, reply_markup=build_giftapi_menu())
            return

        try:
            order = await container.gift_api_service.get_order(order_uuid)
        except GiftApiError as error:
            await answer_giftapi_error(message, error)
            return

        await state.clear()
        await message.answer(render_order(order), reply_markup=build_giftapi_menu())

    @router.message(GiftApiStates.waiting_for_esim_iccid)
    async def handle_esim_iccid(message: Message, state: FSMContext) -> None:
        if not await ensure_configured(message, container):
            await state.clear()
            return
        if is_cancel_message(message):
            await state.clear()
            await message.answer(GIFTAPI_TEXT.ACTION_CANCELED, reply_markup=build_giftapi_menu())
            return

        iccid = (message.text or "").strip()
        if not iccid:
            await message.answer(GIFTAPI_TEXT.ESIM_ICCID_INVALID, reply_markup=build_giftapi_menu())
            return

        try:
            esim_status = await container.gift_api_service.get_esim_status(iccid)
        except GiftApiError as error:
            await answer_giftapi_error(message, error)
            return

        await state.clear()
        await message.answer(render_esim_status(esim_status), reply_markup=build_giftapi_menu())

    @router.message(GiftApiStates.waiting_for_order_payload)
    async def handle_order_payload(message: Message, state: FSMContext) -> None:
        if not await ensure_configured(message, container, require_secret=True):
            await state.clear()
            return
        if is_cancel_message(message):
            await state.clear()
            await message.answer(GIFTAPI_TEXT.ACTION_CANCELED, reply_markup=build_giftapi_menu())
            return

        raw_text = message.text or ""
        try:
            draft = container.gift_api_service.parse_order_payload(raw_text)
            order = await container.gift_api_service.create_order(draft)
        except ValueError as error:
            await message.answer(GIFTAPI_TEXT.order_json_retry(escape(str(error))), reply_markup=build_giftapi_menu())
            return
        except GiftApiError as error:
            await answer_giftapi_error(message, error)
            return

        await state.clear()
        await message.answer(render_created_order(order), reply_markup=build_giftapi_menu())

    return router


async def ensure_configured(
    message: Message,
    container: AppContainer,
    callback: CallbackQuery | None = None,
    require_secret: bool = False,
) -> bool:
    try:
        container.gift_api_service.ensure_configured(require_secret=require_secret)
        return True
    except GiftApiConfigurationError:
        await message.answer(container.gift_api_service.configuration_message(require_secret=require_secret), reply_markup=build_giftapi_menu())
        if callback is not None:
            await callback.answer(GIFTAPI_TEXT.CALLBACK_NOT_CONFIGURED)
        return False


async def answer_giftapi_error(message: Message, error: GiftApiError) -> None:
    await message.answer(GIFTAPI_TEXT.giftapi_error(escape(str(error))), reply_markup=build_giftapi_menu())


def render_menu_intro(container: AppContainer) -> str:
    status = GIFTAPI_TEXT.MENU_STATUS_CONNECTED if container.gift_api_service.is_configured else GIFTAPI_TEXT.MENU_STATUS_NOT_CONFIGURED
    return GIFTAPI_TEXT.menu_intro(escape(status))


def render_overview(partner: GiftPartner, transactions: tuple[object, ...]) -> str:
    lines = [GIFTAPI_TEXT.OVERVIEW_TITLE]
    lines.append(GIFTAPI_TEXT.UUID.format(value=escape(partner.uuid)))
    lines.append(GIFTAPI_TEXT.NAME.format(value=escape(partner.name)))
    lines.append(GIFTAPI_TEXT.EMAIL.format(value=escape(partner.email)))
    lines.append(GIFTAPI_TEXT.CURRENCY.format(value=escape(partner.currency)))
    lines.append(
        GIFTAPI_TEXT.STATUS.format(
            value=GIFTAPI_TEXT.STATUS_ACTIVE if partner.is_active else GIFTAPI_TEXT.STATUS_INACTIVE
        )
    )

    if partner.balance is not None:
        lines.append("")
        lines.append(GIFTAPI_TEXT.BALANCE_TITLE)
        lines.append(GIFTAPI_TEXT.BALANCE_CURRENT.format(amount=escape(format_money(partner.balance.balance, partner.balance.currency))))
        lines.append(GIFTAPI_TEXT.BALANCE_AVAILABLE.format(amount=escape(format_money(partner.balance.available_balance, partner.balance.currency))))
        lines.append(GIFTAPI_TEXT.BALANCE_RESERVED.format(amount=escape(format_money(partner.balance.reserved_amount, partner.balance.currency))))
        lines.append(GIFTAPI_TEXT.BALANCE_OVERDRAFT.format(value=COMMON_TEXT.YES_RU if partner.balance.allow_overdraft else COMMON_TEXT.NO_RU))
        lines.append(GIFTAPI_TEXT.BALANCE_OVERDRAFT_LIMIT.format(amount=escape(format_money(partner.balance.overdraft_limit, partner.balance.currency))))

    if transactions:
        lines.append("")
        lines.append(GIFTAPI_TEXT.RECENT_TRANSACTIONS_TITLE)
        for item in transactions[:5]:
            created_at = format_datetime(item.created_at)
            lines.append(
                GIFTAPI_TEXT.RECENT_TRANSACTION.format(
                    created_at=escape(created_at),
                    transaction_type=escape(item.transaction_type),
                    amount=escape(format_money(item.amount, item.currency)),
                    balance_after=escape(format_money(item.balance_after, item.currency)),
                )
            )

    return "\n".join(lines)


def render_categories(categories: tuple[GiftCategory, ...], limit: int = 12) -> str:
    lines = [GIFTAPI_TEXT.CATEGORIES_TITLE, GIFTAPI_TEXT.CATEGORIES_TOTAL.format(count=len(categories))]
    if not categories:
        lines.append(GIFTAPI_TEXT.CATEGORIES_EMPTY)
        return "\n".join(lines)

    for category in categories[:limit]:
        suffix = GIFTAPI_TEXT.CATEGORY_PARENT_SUFFIX.format(parent_id=category.parent_id) if category.parent_id is not None else ""
        lines.append(
            GIFTAPI_TEXT.CATEGORY_ROW.format(
                category_id=category.category_id,
                name=escape(category.name),
                attributes_count=len(category.attributes),
                suffix=suffix,
            )
        )

    if len(categories) > limit:
        lines.append(GIFTAPI_TEXT.CATEGORIES_LIMIT.format(limit=limit))

    return "\n".join(lines)


def render_products(products: tuple[GiftProductSummary, ...], has_more: bool, limit: int = 8) -> str:
    lines = [GIFTAPI_TEXT.PRODUCTS_TITLE, GIFTAPI_TEXT.PRODUCTS_LOADED.format(count=len(products))]
    if not products:
        lines.append(GIFTAPI_TEXT.PRODUCTS_EMPTY)
        return "\n".join(lines)

    for product in products[:limit]:
        lines.append("")
        lines.append(f"<b>{escape(product.name)}</b>")
        lines.append(GIFTAPI_TEXT.UUID.format(value=escape(product.product_id)))
        lines.append(GIFTAPI_TEXT.TYPE.format(value=escape(product.product_type)))
        if product.category_name:
            lines.append(GIFTAPI_TEXT.CATEGORY.format(value=escape(product.category_name)))
        if product.denomination_type:
            lines.append(GIFTAPI_TEXT.DENOMINATION.format(value=escape(product.denomination_type)))
        if product.skus:
            sku_preview = ", ".join(
                escape(f"{sku.name} [{sku.sku_id[:8]}]") for sku in product.skus[:3]
            )
            lines.append(GIFTAPI_TEXT.SKU_PREVIEW.format(preview=sku_preview))
        if product.description:
            lines.append(escape(shorten_text(strip_html(product.description), 150)))

    if has_more:
        lines.append("")
        lines.append(GIFTAPI_TEXT.PRODUCTS_HAS_MORE)

    lines.append("")
    lines.append(GIFTAPI_TEXT.PRODUCTS_DETAIL_HINT)
    return "\n".join(lines)


def render_product_detail(product: GiftProductDetail, sku_limit: int = 8) -> str:
    lines = [f"<b>GiftAPI: {escape(product.name)}</b>"]
    lines.append(GIFTAPI_TEXT.UUID.format(value=escape(product.product_id)))
    lines.append(GIFTAPI_TEXT.TYPE.format(value=escape(product.product_type)))
    if product.category_name:
        lines.append(GIFTAPI_TEXT.CATEGORY.format(value=escape(product.category_name)))
    if product.denomination_type:
        lines.append(GIFTAPI_TEXT.DENOMINATION.format(value=escape(product.denomination_type)))
    if product.description:
        lines.append(escape(shorten_text(strip_html(product.description), 240)))

    if product.required_fields:
        lines.append("")
        lines.append(GIFTAPI_TEXT.REQUIRED_FIELDS_TITLE)
        for field in product.required_fields[:6]:
            validation = render_validation(field.validation)
            lines.append(
                GIFTAPI_TEXT.REQUIRED_FIELD.format(
                    code=escape(field.code),
                    name=escape(field.name),
                    field_type=escape(field.field_type),
                    required=COMMON_TEXT.YES_EN if field.required else COMMON_TEXT.NO_EN,
                    validation=validation,
                )
            )

    if product.skus:
        lines.append("")
        lines.append(GIFTAPI_TEXT.SKU_TITLE)
        for sku in product.skus[:sku_limit]:
            price_text = format_money(sku.price, sku.currency) if sku.price is not None else render_custom_pricing(sku)
            lines.append(
                GIFTAPI_TEXT.SKU_ROW.format(
                    sku_id=escape(sku.sku_id),
                    name=escape(sku.name),
                    price_text=escape(price_text),
                    stock=sku.stock,
                )
            )
        if len(product.skus) > sku_limit:
            lines.append(GIFTAPI_TEXT.SKU_LIMIT.format(limit=sku_limit))

    return "\n".join(lines)


def render_orders(orders: tuple[GiftOrder, ...], has_more: bool, limit: int = 6) -> str:
    lines = [GIFTAPI_TEXT.ORDERS_TITLE, GIFTAPI_TEXT.ORDERS_LOADED.format(count=len(orders))]
    if not orders:
        lines.append(GIFTAPI_TEXT.ORDERS_EMPTY)
        return "\n".join(lines)

    for order in orders[:limit]:
        lines.append("")
        lines.append(GIFTAPI_TEXT.ORDER_TITLE.format(external_id=escape(order.external_id)))
        lines.append(GIFTAPI_TEXT.UUID.format(value=escape(order.order_id)))
        lines.append(GIFTAPI_TEXT.ORDER_STATUS.format(value=escape(order.status)))
        lines.append(GIFTAPI_TEXT.ORDER_TOTAL.format(amount=escape(format_money(order.total_amount, order.currency))))
        lines.append(GIFTAPI_TEXT.ORDER_CREATED.format(created_at=escape(format_datetime(order.created_at))))
        lines.append(GIFTAPI_TEXT.ORDER_ITEMS_COUNT.format(count=len(order.items)))

    if has_more:
        lines.append("")
        lines.append(GIFTAPI_TEXT.ORDERS_HAS_MORE)

    lines.append("")
    lines.append(GIFTAPI_TEXT.ORDERS_DETAIL_HINT)
    return "\n".join(lines)


def render_order(order: GiftOrder) -> str:
    lines = [GIFTAPI_TEXT.ORDER_DETAIL_TITLE.format(external_id=escape(order.external_id))]
    lines.append(GIFTAPI_TEXT.UUID.format(value=escape(order.order_id)))
    lines.append(GIFTAPI_TEXT.ORDER_STATUS.format(value=escape(order.status)))
    lines.append(GIFTAPI_TEXT.ORDER_TOTAL.format(amount=escape(format_money(order.total_amount, order.currency))))
    lines.append(GIFTAPI_TEXT.ORDER_CREATED.format(created_at=escape(format_datetime(order.created_at))))

    if order.items:
        lines.append("")
        lines.append(GIFTAPI_TEXT.ORDER_ITEMS_TITLE)
        for item in order.items[:4]:
            lines.append(
                GIFTAPI_TEXT.ORDER_ITEM.format(
                    sku_name=escape(item.sku_name),
                    quantity=item.quantity,
                    status=escape(item.status),
                    price_text=escape(format_money(item.price, item.currency)) if item.price is not None else COMMON_TEXT.CUSTOM_PRICE,
                )
            )
            if item.delivery_data:
                lines.append(escape(shorten_text(compact_json(item.delivery_data), 320)))
            if item.error_message:
                lines.append(GIFTAPI_TEXT.ORDER_ITEM_ERROR.format(error_message=escape(item.error_message)))

    return "\n".join(lines)


def render_created_order(order: GiftOrder) -> str:
    lines = [GIFTAPI_TEXT.CREATED_ORDER_TITLE]
    lines.append(GIFTAPI_TEXT.CREATED_ORDER_EXTERNAL_ID.format(external_id=escape(order.external_id)))
    lines.append(GIFTAPI_TEXT.UUID.format(value=escape(order.order_id)))
    lines.append(GIFTAPI_TEXT.ORDER_STATUS.format(value=escape(order.status)))
    lines.append(GIFTAPI_TEXT.ORDER_TOTAL.format(amount=escape(format_money(order.total_amount, order.currency))))
    if order.items:
        first_item = order.items[0]
        if first_item.delivery_data:
            lines.append(GIFTAPI_TEXT.DELIVERY_DATA_TITLE)
            lines.append(f"<pre>{escape(compact_json(first_item.delivery_data))}</pre>")
    return "\n".join(lines)


def render_esim_status(status: GiftEsimStatus) -> str:
    lines = [GIFTAPI_TEXT.ESIM_TITLE]
    lines.append(GIFTAPI_TEXT.ESIM_ICCID.format(iccid=escape(status.iccid)))
    lines.append(GIFTAPI_TEXT.STATUS.format(value=escape(status.status)))
    lines.append(GIFTAPI_TEXT.ESIM_RENEWABLE.format(value=COMMON_TEXT.YES_RU if status.can_renew else COMMON_TEXT.NO_RU))
    if status.last_bundle:
        lines.append(GIFTAPI_TEXT.ESIM_LAST_BUNDLE.format(value=escape(status.last_bundle)))
    if status.total_gb is not None or status.remaining_gb is not None:
        lines.append(GIFTAPI_TEXT.ESIM_TRAFFIC.format(value=escape(format_data_balance(status.remaining_gb, status.total_gb, status.unit))))
    if status.qr_code:
        lines.append(GIFTAPI_TEXT.ESIM_QR.format(value=escape(shorten_text(status.qr_code, 160))))
    if status.universal_link:
        lines.append(GIFTAPI_TEXT.ESIM_LINK.format(value=escape(status.universal_link)))
    if status.active_packages:
        lines.append("")
        lines.append(GIFTAPI_TEXT.ESIM_ACTIVE_PACKAGES_TITLE)
        for package in status.active_packages[:3]:
            lines.append(
                GIFTAPI_TEXT.ESIM_ACTIVE_PACKAGE.format(
                    package_name=escape(package.name or package.package_id or COMMON_TEXT.PACKAGE_PLACEHOLDER),
                    balance=escape(format_data_balance(package.data_remaining, package.data_total, package.data_unit)),
                )
            )
    if status.coverage:
        lines.append("")
        lines.append(GIFTAPI_TEXT.ESIM_COVERAGE_TITLE)
        for coverage in status.coverage[:4]:
            country = coverage.country_name or coverage.country_code or COMMON_TEXT.UNKNOWN
            network = coverage.network_name or COMMON_TEXT.NETWORK_NOT_AVAILABLE
            lines.append(GIFTAPI_TEXT.ESIM_COVERAGE_ROW.format(country=escape(country), network=escape(network)))
    return "\n".join(lines)


def render_order_creation_prompt() -> str:
    template = {
        "external_id": "CERBER-1001",
        "item": {
            "sku_id": "019bc0dd-8562-7173-afd9-a5cc534fafb7",
            "fields": {
                "quantity": 1
            },
        },
        "metadata": {
            "source": "telegram",
            "store": "cerber",
        },
    }
    return (
        f"{GIFTAPI_TEXT.ORDER_CREATION_TITLE}\n"
        f"{GIFTAPI_TEXT.ORDER_CREATION_BODY}\n\n"
        f"<pre>{escape(json.dumps(template, ensure_ascii=False, indent=2))}</pre>\n"
        f"{GIFTAPI_TEXT.ORDER_CREATION_CANCEL}"
    )


def format_datetime(value: object) -> str:
    if value is None:
        return COMMON_TEXT.NOT_AVAILABLE
    return value.astimezone(timezone.utc).strftime("%d.%m.%Y %H:%M UTC")


def format_data_balance(remaining: Decimal | None, total: Decimal | None, unit: str | None) -> str:
    balance_unit = unit or "GB"
    if remaining is None and total is None:
        return f"{COMMON_TEXT.NOT_AVAILABLE} {balance_unit}"
    if remaining is None:
        return f"{COMMON_TEXT.NOT_AVAILABLE} / {format_decimal(total)} {balance_unit}"
    if total is None:
        return f"{format_decimal(remaining)} {balance_unit}"
    return f"{format_decimal(remaining)} / {format_decimal(total)} {balance_unit}"


def format_decimal(value: Decimal | None) -> str:
    if value is None:
        return COMMON_TEXT.NOT_AVAILABLE
    return format(value.normalize(), "f").rstrip("0").rstrip(".") or "0"


def render_custom_pricing(sku: object) -> str:
    markup_parts = []
    if sku.markup_percent is not None:
        markup_parts.append(f"+{format_decimal(sku.markup_percent)}%")
    if sku.markup_fixed is not None:
        markup_parts.append(f"+{format_decimal(sku.markup_fixed)} {sku.currency}")
    return GIFTAPI_TEXT.custom_amount(", ".join(markup_parts) if markup_parts else GIFTAPI_TEXT.CUSTOM_AMOUNT_MARKUP)


def render_validation(validation: dict[str, object]) -> str:
    if not validation:
        return ""
    parts = []
    if "min" in validation:
        parts.append(GIFTAPI_TEXT.VALIDATION_MIN.format(value=validation["min"]))
    if "max" in validation:
        parts.append(GIFTAPI_TEXT.VALIDATION_MAX.format(value=validation["max"]))
    if "regex" in validation:
        parts.append(GIFTAPI_TEXT.VALIDATION_REGEX.format(value=validation["regex"]))
    if "list" in validation and isinstance(validation["list"], list):
        parts.append(GIFTAPI_TEXT.VALIDATION_OPTIONS.format(count=len(validation["list"])))
    return GIFTAPI_TEXT.validation_text(GIFTAPI_TEXT.VALIDATION_SEPARATOR.join(parts)) if parts else ""


def compact_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ": "))


def strip_html(value: str) -> str:
    return " ".join(HTML_TAG_RE.sub(" ", value).split())


def is_cancel_message(message: Message) -> bool:
    return (message.text or "").strip().lower() in GIFTAPI_TEXT.CANCEL_COMMANDS