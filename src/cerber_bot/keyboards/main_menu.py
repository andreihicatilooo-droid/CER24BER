from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from cerber_bot.config import Settings
from cerber_bot.keyboards.storefront import STORE_HOME_ACTION, STORE_ORDERS_ACTION, STORE_REFRESH_ACTION, STORE_SEARCH_PROMPT_ACTION, STORE_WALLET_ACTION

DEAL_HOME_ACTION = "deal:home"
from cerber_bot.texts import FAQ_TEXT, MAIN_MENU_TEXT


MAIN_MENU_ACTION = "menu:main"
PROFILE_ACTION = "menu:profile"
REFRESH_ACTION = STORE_REFRESH_ACTION  # реэкспорт для обратной совместимости хэндлеров
SUPPORT_ACTION = "menu:support"
FAQ_ACTION = "menu:faq"
FAQ_SECTION_PREFIX = "menu:faq:"


def build_main_menu(settings: Settings) -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton(text=MAIN_MENU_TEXT.STORE, callback_data=STORE_HOME_ACTION),
        ],
        [
            InlineKeyboardButton(text=MAIN_MENU_TEXT.WALLET, callback_data=STORE_WALLET_ACTION),
            InlineKeyboardButton(text=MAIN_MENU_TEXT.DEALS, callback_data=DEAL_HOME_ACTION),
        ],
        [
            InlineKeyboardButton(text=MAIN_MENU_TEXT.ORDERS, callback_data=STORE_ORDERS_ACTION),
            InlineKeyboardButton(text=MAIN_MENU_TEXT.PROFILE, callback_data=PROFILE_ACTION),
        ],
    ]

    keyboard.append([
        InlineKeyboardButton(text=MAIN_MENU_TEXT.FAQ, callback_data=FAQ_ACTION),
    ])

    if settings.web_base_url:
        keyboard.append([
            InlineKeyboardButton(
                text=MAIN_MENU_TEXT.WEB_APP,
                web_app=WebAppInfo(url=settings.web_base_url),
            ),
        ])

    if settings.support_url:
        keyboard.append([InlineKeyboardButton(text=MAIN_MENU_TEXT.SUPPORT, url=settings.support_url)])
    else:
        keyboard.append([InlineKeyboardButton(text=MAIN_MENU_TEXT.SUPPORT, callback_data=SUPPORT_ACTION)])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def build_faq_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=FAQ_TEXT.BTN_STORE, callback_data=FAQ_SECTION_PREFIX + "store")],
        [InlineKeyboardButton(text=FAQ_TEXT.BTN_WALLET, callback_data=FAQ_SECTION_PREFIX + "wallet")],
        [InlineKeyboardButton(text=FAQ_TEXT.BTN_DEALS, callback_data=FAQ_SECTION_PREFIX + "deals")],
        [InlineKeyboardButton(text=FAQ_TEXT.BTN_SECURITY, callback_data=FAQ_SECTION_PREFIX + "security")],
    ])


def build_faq_back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=FAQ_TEXT.BTN_BACK, callback_data=FAQ_ACTION)],
    ])