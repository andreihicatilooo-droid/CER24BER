from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from cerber_bot.texts import GIFTAPI_MENU_TEXT


GIFTAPI_MENU_ACTION = "giftapi:menu"
GIFTAPI_OVERVIEW_ACTION = "giftapi:overview"
GIFTAPI_CATEGORIES_ACTION = "giftapi:categories"
GIFTAPI_PRODUCTS_ACTION = "giftapi:products"
GIFTAPI_PRODUCT_LOOKUP_ACTION = "giftapi:product_lookup"
GIFTAPI_ORDERS_ACTION = "giftapi:orders"
GIFTAPI_ORDER_LOOKUP_ACTION = "giftapi:order_lookup"
GIFTAPI_CREATE_ORDER_ACTION = "giftapi:create_order"
GIFTAPI_ESIM_ACTION = "giftapi:esim"
GIFTAPI_BACK_ACTION = "giftapi:back"


def build_giftapi_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=GIFTAPI_MENU_TEXT.OVERVIEW, callback_data=GIFTAPI_OVERVIEW_ACTION),
                InlineKeyboardButton(text=GIFTAPI_MENU_TEXT.CATEGORIES, callback_data=GIFTAPI_CATEGORIES_ACTION),
            ],
            [
                InlineKeyboardButton(text=GIFTAPI_MENU_TEXT.PRODUCTS, callback_data=GIFTAPI_PRODUCTS_ACTION),
                InlineKeyboardButton(text=GIFTAPI_MENU_TEXT.PRODUCT_LOOKUP, callback_data=GIFTAPI_PRODUCT_LOOKUP_ACTION),
            ],
            [
                InlineKeyboardButton(text=GIFTAPI_MENU_TEXT.ORDERS, callback_data=GIFTAPI_ORDERS_ACTION),
                InlineKeyboardButton(text=GIFTAPI_MENU_TEXT.ORDER_LOOKUP, callback_data=GIFTAPI_ORDER_LOOKUP_ACTION),
            ],
            [
                InlineKeyboardButton(text=GIFTAPI_MENU_TEXT.CREATE_ORDER, callback_data=GIFTAPI_CREATE_ORDER_ACTION),
                InlineKeyboardButton(text=GIFTAPI_MENU_TEXT.ESIM_STATUS, callback_data=GIFTAPI_ESIM_ACTION),
            ],
            [InlineKeyboardButton(text=GIFTAPI_MENU_TEXT.BACK, callback_data=GIFTAPI_BACK_ACTION)],
        ]
    )