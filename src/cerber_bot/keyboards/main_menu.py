from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from cerber_bot.config import Settings
from cerber_bot.keyboards.storefront import STORE_HOME_ACTION, STORE_ORDERS_ACTION, STORE_REFRESH_ACTION, STORE_SEARCH_PROMPT_ACTION, STORE_WALLET_ACTION
from cerber_bot.keyboards.tgaccounts import TGACC_HOME_ACTION

DEAL_HOME_ACTION = "deal:home"
from cerber_bot.keyboards.deals import OFFER_NEW_ACTION
from cerber_bot.texts import ACCOUNT_TEXT, FAQ_TEXT, MAIN_MENU_TEXT, OFFER_TEXT, REFERRAL_TEXT, REVIEW_TEXT, SEARCH_TEXT


MAIN_MENU_ACTION = "menu:main"
PROFILE_ACTION = "menu:profile"
REPUTATION_ACTION = "menu:reputation"
REFRESH_ACTION = STORE_REFRESH_ACTION  # реэкспорт для обратной совместимости хэндлеров
SUPPORT_ACTION = "menu:support"
FAQ_ACTION = "menu:faq"
FAQ_SECTION_PREFIX = "menu:faq:"
CERBER_TRADE_ACTION = "menu:cerber_trade"
MY_REVIEWS_ACTION = "menu:myreviews"
CHANGE_NAME_ACTION = "menu:changename"
REFERRALS_ACTION = "menu:referrals"
USER_SEARCH_ACTION = "menu:usersearch"


def build_main_menu(settings: Settings) -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton(text=MAIN_MENU_TEXT.STORE, callback_data=STORE_HOME_ACTION),
        ],
        [
            InlineKeyboardButton(text=MAIN_MENU_TEXT.WALLET, callback_data=STORE_WALLET_ACTION),
        ],
        [
            InlineKeyboardButton(text=MAIN_MENU_TEXT.CERBER_TRADE, callback_data=CERBER_TRADE_ACTION),
        ],
        [
            InlineKeyboardButton(text=MAIN_MENU_TEXT.ORDERS, callback_data=STORE_ORDERS_ACTION),
            InlineKeyboardButton(text=MAIN_MENU_TEXT.PROFILE, callback_data=PROFILE_ACTION),
        ],
        [
            InlineKeyboardButton(text=MAIN_MENU_TEXT.REPUTATION, callback_data=REPUTATION_ACTION),
        ],
        [
            InlineKeyboardButton(text=MAIN_MENU_TEXT.TG_ACCOUNTS, callback_data=TGACC_HOME_ACTION),
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


def build_cerber_trade_menu(settings: Settings | None = None) -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton(text=MAIN_MENU_TEXT.DEALS, callback_data=DEAL_HOME_ACTION)],
        [InlineKeyboardButton(text=OFFER_TEXT.BTN_CREATE_TEMPLATE, callback_data=OFFER_NEW_ACTION)],
        [
            InlineKeyboardButton(text=MAIN_MENU_TEXT.WALLET, callback_data=STORE_WALLET_ACTION),
            InlineKeyboardButton(text=REVIEW_TEXT.MY_REVIEWS_BTN, callback_data=MY_REVIEWS_ACTION),
        ],
        [
            InlineKeyboardButton(text=REFERRAL_TEXT.BTN_INVITE, callback_data=REFERRALS_ACTION),
            InlineKeyboardButton(text=SEARCH_TEXT.BTN_SEARCH, callback_data=USER_SEARCH_ACTION),
        ],
    ]
    if settings is not None and settings.web_base_url:
        keyboard.append([
            InlineKeyboardButton(
                text=MAIN_MENU_TEXT.WALLET_MINI_APP,
                web_app=WebAppInfo(url=settings.web_base_url.rstrip("/") + "/wallet"),
            ),
        ])
    keyboard.append([InlineKeyboardButton(text=MAIN_MENU_TEXT.HOME, callback_data=MAIN_MENU_ACTION)])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def build_profile_keyboard(*, name_change_available: bool) -> InlineKeyboardMarkup:
    keyboard: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(text=REVIEW_TEXT.MY_REVIEWS_BTN, callback_data=MY_REVIEWS_ACTION),
            InlineKeyboardButton(text=REFERRAL_TEXT.BTN_INVITE, callback_data=REFERRALS_ACTION),
        ],
    ]
    if name_change_available:
        keyboard.append([InlineKeyboardButton(text=ACCOUNT_TEXT.BTN_CHANGE_NAME, callback_data=CHANGE_NAME_ACTION)])
    keyboard.append([InlineKeyboardButton(text=MAIN_MENU_TEXT.HOME, callback_data=MAIN_MENU_ACTION)])
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