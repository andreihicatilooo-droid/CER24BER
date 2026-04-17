from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from cerber_bot.services.store import PageInfo, StoreCategoryCard, StoreOrderCard, StoreProductCard, StoreProductOffer, format_money
from cerber_bot.texts import STORE_KEYBOARD_TEXT

MAIN_MENU_ACTION = "menu:main"


STORE_HOME_ACTION = "store:home"
STORE_REFRESH_ACTION = "menu:refresh"  # та же строка, что REFRESH_ACTION в main_menu
STORE_CATEGORIES_ACTION = "store:cats"
STORE_CATEGORIES_PAGE_PREFIX = "store:cp:"
STORE_CATEGORY_OPEN_PREFIX = "store:c:"
STORE_PRODUCTS_PAGE_PREFIX = "store:p:"
STORE_PRODUCT_ACTION_PREFIX = "store:prod:"
STORE_DETAIL_OFFERS_PAGE_PREFIX = "store:of:"
STORE_DETAIL_BACK_ACTION = "store:db"
STORE_SEARCH_PROMPT_ACTION = "store:search"
STORE_SEARCH_PAGE_PREFIX = "store:sp:"
STORE_WALLET_ACTION = "store:wallet"
STORE_TOP_UP_PREFIX = "store:top:"
STORE_TOP_UP_CUSTOM_ACTION = "store:topcustom"
STORE_ORDERS_ACTION = "store:orders"
STORE_ORDERS_PAGE_PREFIX = "store:op:"
STORE_ORDER_ACTION_PREFIX = "store:o:"
STORE_BUY_SKU_PREFIX = "store:buy:"
STORE_FIELD_FILL_PREFIX = "store:ff:"  # суффикс — sku_id
STORE_FIELD_CANCEL_ACTION = "store:fc"
STORE_GIFTAPI_ACTION = "store:ga"  # открыть каталог GiftAPI


def build_store_home_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=STORE_KEYBOARD_TEXT.GIFTAPI_PROVIDER, callback_data=STORE_GIFTAPI_ACTION),
            ],
            [
                InlineKeyboardButton(text=STORE_KEYBOARD_TEXT.WALLET, callback_data=STORE_WALLET_ACTION),
                InlineKeyboardButton(text=STORE_KEYBOARD_TEXT.ORDERS, callback_data=STORE_ORDERS_ACTION),
            ],
            [
                InlineKeyboardButton(text=STORE_KEYBOARD_TEXT.REFRESH, callback_data=STORE_REFRESH_ACTION),
            ],
        ]
    )


def build_categories_keyboard(categories: tuple[StoreCategoryCard, ...], page_info: PageInfo, *, back_callback: str = STORE_HOME_ACTION) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for category in categories:
        rows.append(
            [
                InlineKeyboardButton(
                    text=truncate_text(STORE_KEYBOARD_TEXT.category_card(category.name, category.product_count), 34),
                    callback_data=f"{STORE_CATEGORY_OPEN_PREFIX}{category.category_id}",
                )
            ]
        )

    nav_row = build_pagination_row(
        previous_callback=f"{STORE_CATEGORIES_PAGE_PREFIX}{page_info.page - 1}" if page_info.has_previous else None,
        next_callback=f"{STORE_CATEGORIES_PAGE_PREFIX}{page_info.page + 1}" if page_info.has_next else None,
        page_info=page_info,
    )
    if nav_row:
        rows.append(nav_row)

    rows.append([
        InlineKeyboardButton(text=STORE_KEYBOARD_TEXT.BACK, callback_data=back_callback),
        InlineKeyboardButton(text=STORE_KEYBOARD_TEXT.HOME, callback_data=STORE_HOME_ACTION),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_products_keyboard(
    products: tuple[StoreProductCard, ...],
    page_info: PageInfo,
    *,
    previous_callback: str | None,
    next_callback: str | None,
    back_callback: str,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for product in products:
        price_label = format_card_price(product)
        rows.append(
            [
                InlineKeyboardButton(
                    text=truncate_text(STORE_KEYBOARD_TEXT.product_card(product.name, price_label), 38),
                    callback_data=f"{STORE_PRODUCT_ACTION_PREFIX}{product.product_id}",
                )
            ]
        )

    nav_row = build_pagination_row(previous_callback=previous_callback, next_callback=next_callback, page_info=page_info)
    if nav_row:
        rows.append(nav_row)

    rows.append(
        [
            InlineKeyboardButton(text=STORE_KEYBOARD_TEXT.BACK, callback_data=back_callback),
            InlineKeyboardButton(text=STORE_KEYBOARD_TEXT.HOME, callback_data=STORE_HOME_ACTION),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_product_detail_keyboard(
    offers: tuple[StoreProductOffer, ...],
    page_info: PageInfo,
    *,
    back_callback: str,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for offer in offers:
        if not offer.buyable:
            continue
        if offer.required_fields:
            # Оффер требует данных покупателя — кнопка заполнения
            rows.append(
                [
                    InlineKeyboardButton(
                        text=truncate_text(
                            STORE_KEYBOARD_TEXT.fill_offer(offer.name),
                            38,
                        ),
                        callback_data=f"{STORE_FIELD_FILL_PREFIX}{offer.sku_id}",
                    )
                ]
            )
        else:
            rows.append(
                [
                    InlineKeyboardButton(
                        text=truncate_text(
                            STORE_KEYBOARD_TEXT.buy_offer(offer.name, format_money(offer.price, offer.currency)),
                            38,
                        ),
                        callback_data=f"{STORE_BUY_SKU_PREFIX}{offer.sku_id}",
                    )
                ]
            )

    nav_row = build_pagination_row(
        previous_callback=f"{STORE_DETAIL_OFFERS_PAGE_PREFIX}{page_info.page - 1}" if page_info.has_previous else None,
        next_callback=f"{STORE_DETAIL_OFFERS_PAGE_PREFIX}{page_info.page + 1}" if page_info.has_next else None,
        page_info=page_info,
    )
    if nav_row:
        rows.append(nav_row)

    rows.append(
        [
            InlineKeyboardButton(text=STORE_KEYBOARD_TEXT.BACK_TO_LIST, callback_data=back_callback),
            InlineKeyboardButton(text=STORE_KEYBOARD_TEXT.WALLET, callback_data=STORE_WALLET_ACTION),
        ]
    )
    rows.append([InlineKeyboardButton(text=STORE_KEYBOARD_TEXT.HOME, callback_data=STORE_HOME_ACTION)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_field_input_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура с кнопкой «Отмена» при вводе обязательных полей."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=STORE_KEYBOARD_TEXT.FIELD_CANCEL, callback_data=STORE_FIELD_CANCEL_ACTION)]
        ]
    )


def build_wallet_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=STORE_KEYBOARD_TEXT.top_up_amount("10"), callback_data=f"{STORE_TOP_UP_PREFIX}10"),
                InlineKeyboardButton(text=STORE_KEYBOARD_TEXT.top_up_amount("25"), callback_data=f"{STORE_TOP_UP_PREFIX}25"),
                InlineKeyboardButton(text=STORE_KEYBOARD_TEXT.top_up_amount("50"), callback_data=f"{STORE_TOP_UP_PREFIX}50"),
                InlineKeyboardButton(text=STORE_KEYBOARD_TEXT.top_up_amount("100"), callback_data=f"{STORE_TOP_UP_PREFIX}100"),
            ],
            [InlineKeyboardButton(text=STORE_KEYBOARD_TEXT.CUSTOM_AMOUNT, callback_data=STORE_TOP_UP_CUSTOM_ACTION)],
            [
                InlineKeyboardButton(text=STORE_KEYBOARD_TEXT.ORDERS, callback_data=STORE_ORDERS_ACTION),
                InlineKeyboardButton(text=STORE_KEYBOARD_TEXT.HOME, callback_data=STORE_HOME_ACTION),
            ],
        ]
    )


def build_orders_keyboard(orders: tuple[StoreOrderCard, ...], page_info: PageInfo) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for order in orders:
        rows.append(
            [
                InlineKeyboardButton(
                    text=truncate_text(STORE_KEYBOARD_TEXT.order_card(order.order_id, order.product_name, format_money(order.total_amount, order.currency)), 38),
                    callback_data=f"{STORE_ORDER_ACTION_PREFIX}{order.order_id}",
                )
            ]
        )

    nav_row = build_pagination_row(
        previous_callback=f"{STORE_ORDERS_PAGE_PREFIX}{page_info.page - 1}" if page_info.has_previous else None,
        next_callback=f"{STORE_ORDERS_PAGE_PREFIX}{page_info.page + 1}" if page_info.has_next else None,
        page_info=page_info,
    )
    if nav_row:
        rows.append(nav_row)

    rows.append(
        [
            InlineKeyboardButton(text=STORE_KEYBOARD_TEXT.WALLET, callback_data=STORE_WALLET_ACTION),
            InlineKeyboardButton(text=STORE_KEYBOARD_TEXT.HOME, callback_data=MAIN_MENU_ACTION),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_order_detail_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=STORE_KEYBOARD_TEXT.ORDERS, callback_data=STORE_ORDERS_ACTION),
                InlineKeyboardButton(text=STORE_KEYBOARD_TEXT.WALLET, callback_data=STORE_WALLET_ACTION),
            ],
            [InlineKeyboardButton(text=STORE_KEYBOARD_TEXT.HOME, callback_data=MAIN_MENU_ACTION)],
        ]
    )


def build_pagination_row(
    *,
    previous_callback: str | None,
    next_callback: str | None,
    page_info: PageInfo,
) -> list[InlineKeyboardButton] | None:
    if not previous_callback and not next_callback:
        return None

    row = [
        InlineKeyboardButton(text=STORE_KEYBOARD_TEXT.PAGINATION_PREVIOUS, callback_data=previous_callback or "noop") if previous_callback else InlineKeyboardButton(text=STORE_KEYBOARD_TEXT.PAGINATION_PLACEHOLDER, callback_data="noop"),
        InlineKeyboardButton(text=STORE_KEYBOARD_TEXT.page_info(page_info.page, page_info.total_pages), callback_data="noop"),
        InlineKeyboardButton(text=STORE_KEYBOARD_TEXT.PAGINATION_NEXT, callback_data=next_callback or "noop") if next_callback else InlineKeyboardButton(text=STORE_KEYBOARD_TEXT.PAGINATION_PLACEHOLDER, callback_data="noop"),
    ]
    return row


def truncate_text(value: str, limit: int) -> str:
    normalized = " ".join(value.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 1].rstrip() + "…"


def format_card_price(product: StoreProductCard) -> str:
    if product.min_price is None or product.currency is None:
        return STORE_KEYBOARD_TEXT.PRICE_ON_REQUEST
    if product.max_price is None or product.max_price == product.min_price:
        return format_money(product.min_price, product.currency)
    return STORE_KEYBOARD_TEXT.price_from(format_money(product.min_price, product.currency))