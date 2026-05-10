"""Клавиатуры для раздела Telegram-аккаунтов."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from cerber_bot.services.tgaccounts import TgCatalogPage, TgCountryDetails
from cerber_bot.db.models import TgAccountPurchase
from cerber_bot.texts import TG_ACCOUNTS_KEYBOARD_TEXT, MAIN_MENU_TEXT
from cerber_bot.services.store import PageInfo, format_money

# Префиксы callback_data (≤8 символов)
TGACC_HOME_ACTION = "tgacc:home"
TGACC_COUNTRIES_PAGE_PREFIX = "tgacc:cp:"  # + номер страницы
TGACC_COUNTRY_DETAIL_PREFIX = "tgacc:cd:"  # + country_code
TGACC_BUY_PREFIX = "tgacc:buy:"  # + country_code
TGACC_CONFIRM_BUY_PREFIX = "tgacc:ok:"  # + country_code
TGACC_CANCEL_BUY_ACTION = "tgacc:cancel"
TGACC_MY_PURCHASES_ACTION = "tgacc:myp"
TGACC_MY_PURCHASES_PAGE_PREFIX = "tgacc:pp:"  # + номер страницы
TGACC_PURCHASE_DETAIL_PREFIX = "tgacc:pd:"  # + purchase_id
TGACC_REQUEST_CODE_PREFIX = "tgacc:rc:"  # + purchase_id
TGACC_REFUND_PREFIX = "tgacc:ref:"  # + purchase_id


def build_home_keyboard() -> InlineKeyboardMarkup:
    """Главное меню раздела Telegram-аккаунтов."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=TG_ACCOUNTS_KEYBOARD_TEXT.COUNTRIES,
                    callback_data=TGACC_COUNTRIES_PAGE_PREFIX + "1",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=TG_ACCOUNTS_KEYBOARD_TEXT.MY_PURCHASES,
                    callback_data=TGACC_MY_PURCHASES_ACTION,
                ),
            ],
            [
                InlineKeyboardButton(
                    text=MAIN_MENU_TEXT.FAQ,
                    callback_data="menu:faq",  # Уточню позже, но это примерный callback
                ),
                InlineKeyboardButton(
                    text=MAIN_MENU_TEXT.PROFILE,
                    callback_data="menu:profile",
                ),
            ],
        ]
    )


def build_countries_keyboard(catalog: TgCatalogPage) -> InlineKeyboardMarkup:
    """Клавиатура со списком стран и пагинацией."""
    rows: list[list[InlineKeyboardButton]] = []
    
    for country in catalog.items:
        price_label = format_money(country.amount, country.currency)
        button_text = truncate_text(
            TG_ACCOUNTS_KEYBOARD_TEXT.country_card(
                country.emoji,
                country.display_name,
                price_label,
                country.available,
            ),
            40,
        )
        rows.append(
            [
                InlineKeyboardButton(
                    text=button_text,
                    callback_data=f"{TGACC_COUNTRY_DETAIL_PREFIX}{country.country_code}",
                )
            ]
        )
    
    # Пагинация
    nav_row = build_pagination_row(
        previous_callback=f"{TGACC_COUNTRIES_PAGE_PREFIX}{catalog.page - 1}" if catalog.has_previous else None,
        next_callback=f"{TGACC_COUNTRIES_PAGE_PREFIX}{catalog.page + 1}" if catalog.has_next else None,
        page=catalog.page,
        total_pages=catalog.total_pages,
    )
    if nav_row:
        rows.append(nav_row)
    
    rows.append(
        [
            InlineKeyboardButton(text=TG_ACCOUNTS_KEYBOARD_TEXT.BACK, callback_data=TGACC_HOME_ACTION),
            InlineKeyboardButton(text=MAIN_MENU_TEXT.HOME, callback_data="menu:main"),
        ]
    )
    
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_country_detail_keyboard(country_code: str, available: bool, *, back_page: int = 1) -> InlineKeyboardMarkup:
    """Клавиатура карточки страны с кнопкой "Купить"."""
    rows: list[list[InlineKeyboardButton]] = []
    
    if available:
        rows.append(
            [
                InlineKeyboardButton(
                    text=TG_ACCOUNTS_KEYBOARD_TEXT.BUY,
                    callback_data=f"{TGACC_BUY_PREFIX}{country_code}",
                )
            ]
        )
    
    rows.append(
        [
            InlineKeyboardButton(text=TG_ACCOUNTS_KEYBOARD_TEXT.BACK, callback_data=f"{TGACC_COUNTRIES_PAGE_PREFIX}{back_page}"),
            InlineKeyboardButton(text=MAIN_MENU_TEXT.HOME, callback_data="menu:main"),
        ]
    )
    
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_buy_confirmation_keyboard(country_code: str) -> InlineKeyboardMarkup:
    """Клавиатура подтверждения покупки аккаунта."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=TG_ACCOUNTS_KEYBOARD_TEXT.CONFIRM,
                    callback_data=f"{TGACC_CONFIRM_BUY_PREFIX}{country_code}",
                ),
                InlineKeyboardButton(
                    text=TG_ACCOUNTS_KEYBOARD_TEXT.CANCEL,
                    callback_data=TGACC_CANCEL_BUY_ACTION,
                ),
            ],
        ]
    )


def build_my_purchases_keyboard(purchases: tuple[TgAccountPurchase, ...], page_info: PageInfo) -> InlineKeyboardMarkup:
    """Клавиатура со списком купленных аккаунтов и пагинацией."""
    rows: list[list[InlineKeyboardButton]] = []
    
    for purchase in purchases:
        button_text = truncate_text(
            TG_ACCOUNTS_KEYBOARD_TEXT.purchase_card(
                purchase.phone_number,
                purchase.country_code.upper(),
                purchase.status,
            ),
            40,
        )
        rows.append(
            [
                InlineKeyboardButton(
                    text=button_text,
                    callback_data=f"{TGACC_PURCHASE_DETAIL_PREFIX}{purchase.id}",
                )
            ]
        )
    
    # Пагинация
    nav_row = build_pagination_row(
        previous_callback=f"{TGACC_MY_PURCHASES_PAGE_PREFIX}{page_info.page - 1}" if page_info.has_previous else None,
        next_callback=f"{TGACC_MY_PURCHASES_PAGE_PREFIX}{page_info.page + 1}" if page_info.has_next else None,
        page=page_info.page,
        total_pages=page_info.total_pages,
    )
    if nav_row:
        rows.append(nav_row)
    
    rows.append(
        [
            InlineKeyboardButton(text=TG_ACCOUNTS_KEYBOARD_TEXT.BACK, callback_data=TGACC_HOME_ACTION),
            InlineKeyboardButton(text=MAIN_MENU_TEXT.HOME, callback_data="menu:main"),
        ]
    )
    
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_purchase_detail_keyboard(purchase: TgAccountPurchase) -> InlineKeyboardMarkup:
    """Клавиатура карточки покупки с кнопками действий."""
    rows: list[list[InlineKeyboardButton]] = []
    
    # Кнопка получить код (доступна, если статус PENDING, DELIVERED или ACTIVE)
    if purchase.status in ("PENDING", "DELIVERED", "ACTIVE", "SUCCESS"):
        rows.append(
            [
                InlineKeyboardButton(
                    text=TG_ACCOUNTS_KEYBOARD_TEXT.GET_CODE,
                    callback_data=f"{TGACC_REQUEST_CODE_PREFIX}{purchase.id}",
                )
            ]
        )
    
    # Кнопка возврата (доступна, если статус не REFUND)
    if purchase.status != "REFUND":
        rows.append(
            [
                InlineKeyboardButton(
                    text=TG_ACCOUNTS_KEYBOARD_TEXT.REFUND,
                    callback_data=f"{TGACC_REFUND_PREFIX}{purchase.id}",
                )
            ]
        )
    
    rows.append(
        [
            InlineKeyboardButton(text=TG_ACCOUNTS_KEYBOARD_TEXT.BACK, callback_data=TGACC_MY_PURCHASES_ACTION),
            InlineKeyboardButton(text=MAIN_MENU_TEXT.HOME, callback_data="menu:main"),
        ]
    )
    
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_pagination_row(
    *,
    previous_callback: str | None,
    next_callback: str | None,
    page: int,
    total_pages: int,
) -> list[InlineKeyboardButton] | None:
    """Построить строку пагинации."""
    if not previous_callback and not next_callback:
        return None
    
    row = [
        InlineKeyboardButton(
            text=TG_ACCOUNTS_KEYBOARD_TEXT.PAGINATION_PREVIOUS,
            callback_data=previous_callback or "noop",
        ) if previous_callback else InlineKeyboardButton(
            text=TG_ACCOUNTS_KEYBOARD_TEXT.PAGINATION_PLACEHOLDER,
            callback_data="noop",
        ),
        InlineKeyboardButton(
            text=TG_ACCOUNTS_KEYBOARD_TEXT.page_info(page, total_pages),
            callback_data="noop",
        ),
        InlineKeyboardButton(
            text=TG_ACCOUNTS_KEYBOARD_TEXT.PAGINATION_NEXT,
            callback_data=next_callback or "noop",
        ) if next_callback else InlineKeyboardButton(
            text=TG_ACCOUNTS_KEYBOARD_TEXT.PAGINATION_PLACEHOLDER,
            callback_data="noop",
        ),
    ]
    return row


def truncate_text(value: str, limit: int) -> str:
    """Обрезать текст, если он превышает лимит."""
    normalized = " ".join(value.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 1].rstrip() + "…"
