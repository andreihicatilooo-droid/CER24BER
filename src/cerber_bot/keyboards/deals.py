from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from cerber_bot.keyboards.storefront import STORE_HOME_ACTION, STORE_WALLET_ACTION
from cerber_bot.services.deals import DealCard, DealView
from cerber_bot.services.store import PageInfo, format_money
from cerber_bot.texts import DEAL_KEYBOARD_TEXT


MAIN_MENU_ACTION = "menu:main"

DEAL_HOME_ACTION = "deal:home"
DEAL_NEW_ACTION = "deal:new"
DEAL_LIST_ACTION = "deal:list"
DEAL_PAGE_PREFIX = "deal:page:"
DEAL_OPEN_PREFIX = "deal:open:"
DEAL_ACCEPT_PREFIX = "deal:accept:"
DEAL_DECLINE_PREFIX = "deal:decline:"
DEAL_CANCEL_PREFIX = "deal:cancel:"
DEAL_MESSAGE_PREFIX = "deal:message:"
DEAL_SUCCESS_PREFIX = "deal:success:"
DEAL_DISPUTE_PREFIX = "deal:dispute:"
DEAL_MODERATOR_PREFIX = "deal:moderator:"
DEAL_MODERATION_PREFIX = "deal:moderate:"
DEAL_DELIVERED_PREFIX = "deal:delivered:"
DEAL_WITHDRAW_ACTION = "deal:withdraw"
DEAL_WITHDRAW_CANCEL_PREFIX = "deal:withdraw:cancel:"
DEAL_WITHDRAW_NETWORK_PREFIX = "deal:withdraw:network:"
DEAL_WITHDRAW_MODERATION_PREFIX = "deal:withdraw:moderate:"

REVIEW_START_PREFIX = "review:start:"
REVIEW_RATE_PREFIX = "review:rate:"

OFFER_ACCEPT_PREFIX = "ofr:"
OFFER_NEW_ACTION = "offer:new"
OFFER_ROLE_PREFIX = "offer:role:"

DEAL_CREATE_ACTION = DEAL_NEW_ACTION
DEAL_LIST_PAGE_PREFIX = DEAL_PAGE_PREFIX
DEAL_CONFIRM_PREFIX = DEAL_SUCCESS_PREFIX


def build_deal_home_keyboard(*, open_withdrawal_request_id: int | None = None) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(text=DEAL_KEYBOARD_TEXT.CREATE_DEAL, callback_data=DEAL_NEW_ACTION),
            InlineKeyboardButton(text=DEAL_KEYBOARD_TEXT.MY_DEALS, callback_data=DEAL_LIST_ACTION),
        ],
        [
            InlineKeyboardButton(text=DEAL_KEYBOARD_TEXT.WITHDRAW_USDT, callback_data=DEAL_WITHDRAW_ACTION),
            InlineKeyboardButton(text=DEAL_KEYBOARD_TEXT.WALLET, callback_data=STORE_WALLET_ACTION),
        ],
    ]
    if open_withdrawal_request_id is not None:
        rows.append(
            [
                InlineKeyboardButton(
                    text=DEAL_KEYBOARD_TEXT.cancel_withdraw(open_withdrawal_request_id),
                    callback_data=f"{DEAL_WITHDRAW_CANCEL_PREFIX}{open_withdrawal_request_id}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text=DEAL_KEYBOARD_TEXT.MAIN_MENU, callback_data=MAIN_MENU_ACTION)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_deals_keyboard(cards: tuple[DealCard, ...], page_info: PageInfo) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for card in cards:
        rows.append(
            [
                InlineKeyboardButton(
                    text=_truncate_text(
                        DEAL_KEYBOARD_TEXT.deal_card(
                            card.deal_id,
                            _format_status(card.status),
                            format_money(card.amount, card.currency),
                            card.counterpart_display,
                        ),
                        42,
                    ),
                    callback_data=f"{DEAL_OPEN_PREFIX}{card.deal_id}",
                )
            ]
        )

    nav_row = _build_pagination_row(
        previous_callback=f"{DEAL_PAGE_PREFIX}{page_info.page - 1}" if page_info.has_previous else None,
        next_callback=f"{DEAL_PAGE_PREFIX}{page_info.page + 1}" if page_info.has_next else None,
        page_info=page_info,
    )
    if nav_row is not None:
        rows.append(nav_row)

    rows.append(
        [
            InlineKeyboardButton(text=DEAL_KEYBOARD_TEXT.DEAL_HOME, callback_data=DEAL_HOME_ACTION),
            InlineKeyboardButton(text=DEAL_KEYBOARD_TEXT.WALLET, callback_data=STORE_WALLET_ACTION),
        ]
    )
    rows.append([InlineKeyboardButton(text=DEAL_KEYBOARD_TEXT.MAIN_MENU, callback_data=MAIN_MENU_ACTION)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_deal_detail_keyboard(deal: DealView, *, can_review: bool = False) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []

    if can_review:
        rows.append(
            [
                InlineKeyboardButton(
                    text=DEAL_KEYBOARD_TEXT.LEAVE_REVIEW,
                    callback_data=f"{REVIEW_START_PREFIX}{deal.deal_id}",
                )
            ]
        )

    if deal.can_accept:
        action_row = [InlineKeyboardButton(text=DEAL_KEYBOARD_TEXT.ACCEPT, callback_data=f"{DEAL_ACCEPT_PREFIX}{deal.deal_id}")]
        if deal.can_decline and not deal.can_cancel:
            action_row.append(
                InlineKeyboardButton(text=DEAL_KEYBOARD_TEXT.DECLINE, callback_data=f"{DEAL_DECLINE_PREFIX}{deal.deal_id}")
            )
        rows.append(action_row)
    elif deal.can_cancel:
        rows.append(
            [
                InlineKeyboardButton(
                    text=DEAL_KEYBOARD_TEXT.CANCEL_DEAL,
                    callback_data=f"{DEAL_CANCEL_PREFIX}{deal.deal_id}",
                )
            ]
        )
    elif deal.can_decline:
        rows.append(
            [
                InlineKeyboardButton(text=DEAL_KEYBOARD_TEXT.DECLINE, callback_data=f"{DEAL_DECLINE_PREFIX}{deal.deal_id}")
            ]
        )

    if deal.can_mark_delivered:
        rows.append(
            [
                InlineKeyboardButton(
                    text=DEAL_KEYBOARD_TEXT.MARK_DELIVERED,
                    callback_data=f"{DEAL_DELIVERED_PREFIX}{deal.deal_id}",
                )
            ]
        )

    if deal.can_send_message:
        rows.append(
            [
                InlineKeyboardButton(text=DEAL_KEYBOARD_TEXT.DEAL_CHAT, callback_data=f"{DEAL_MESSAGE_PREFIX}{deal.deal_id}")
            ]
        )

    resolution_row: list[InlineKeyboardButton] = []
    if deal.can_confirm_success:
        resolution_row.append(
            InlineKeyboardButton(
                text=DEAL_KEYBOARD_TEXT.CONFIRM_SUCCESS,
                callback_data=f"{DEAL_SUCCESS_PREFIX}{deal.deal_id}",
            )
        )
    if deal.can_open_dispute:
        resolution_row.append(
            InlineKeyboardButton(
                text=DEAL_KEYBOARD_TEXT.OPEN_DISPUTE,
                callback_data=f"{DEAL_DISPUTE_PREFIX}{deal.deal_id}",
            )
        )
    if resolution_row:
        rows.append(resolution_row)

    if deal.can_call_moderator:
        rows.append(
            [
                InlineKeyboardButton(
                    text=DEAL_KEYBOARD_TEXT.CALL_MODERATOR,
                    callback_data=f"{DEAL_MODERATOR_PREFIX}{deal.deal_id}",
                )
            ]
        )

    rows.append(
        [
            InlineKeyboardButton(text=DEAL_KEYBOARD_TEXT.MY_DEALS, callback_data=DEAL_LIST_ACTION),
            InlineKeyboardButton(text=DEAL_KEYBOARD_TEXT.DEAL_HOME, callback_data=DEAL_HOME_ACTION),
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(text=DEAL_KEYBOARD_TEXT.WALLET, callback_data=STORE_WALLET_ACTION),
            InlineKeyboardButton(text=DEAL_KEYBOARD_TEXT.MAIN_MENU, callback_data=MAIN_MENU_ACTION),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_deal_open_keyboard(deal_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=DEAL_KEYBOARD_TEXT.OPEN_DEAL, callback_data=f"{DEAL_OPEN_PREFIX}{deal_id}")],
            [
                InlineKeyboardButton(text=DEAL_KEYBOARD_TEXT.MY_DEALS, callback_data=DEAL_LIST_ACTION),
                InlineKeyboardButton(text=DEAL_KEYBOARD_TEXT.DEAL_HOME, callback_data=DEAL_HOME_ACTION),
            ],
        ]
    )


def build_deal_invite_keyboard(deal_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=DEAL_KEYBOARD_TEXT.ACCEPT, callback_data=f"{DEAL_ACCEPT_PREFIX}{deal_id}"),
                InlineKeyboardButton(text=DEAL_KEYBOARD_TEXT.DECLINE, callback_data=f"{DEAL_DECLINE_PREFIX}{deal_id}"),
            ],
            [InlineKeyboardButton(text=DEAL_KEYBOARD_TEXT.OPEN_DEAL, callback_data=f"{DEAL_OPEN_PREFIX}{deal_id}")],
        ]
    )


def build_moderator_deal_keyboard(deal_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=DEAL_KEYBOARD_TEXT.MOD_RELEASE,
                    callback_data=f"{DEAL_MODERATION_PREFIX}{deal_id}:release",
                )
            ],
            [
                InlineKeyboardButton(
                    text=DEAL_KEYBOARD_TEXT.MOD_REFUND,
                    callback_data=f"{DEAL_MODERATION_PREFIX}{deal_id}:refund",
                )
            ],
            [InlineKeyboardButton(text=DEAL_KEYBOARD_TEXT.OPEN_DEAL, callback_data=f"{DEAL_OPEN_PREFIX}{deal_id}")],
        ]
    )


def build_review_rating_keyboard(deal_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⭐" * rating,
                    callback_data=f"{REVIEW_RATE_PREFIX}{deal_id}:{rating}",
                )
                for rating in range(1, 6)
            ],
            [InlineKeyboardButton(text=DEAL_KEYBOARD_TEXT.DEAL_HOME, callback_data=DEAL_HOME_ACTION)],
        ]
    )


def build_withdrawal_network_keyboard(networks: tuple[str, ...]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    current_row: list[InlineKeyboardButton] = []
    for network in networks:
        current_row.append(
            InlineKeyboardButton(text=network, callback_data=f"{DEAL_WITHDRAW_NETWORK_PREFIX}{network}")
        )
        if len(current_row) == 2:
            rows.append(current_row)
            current_row = []
    if current_row:
        rows.append(current_row)
    rows.append([InlineKeyboardButton(text=DEAL_KEYBOARD_TEXT.DEAL_HOME, callback_data=DEAL_HOME_ACTION)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_moderator_withdrawal_keyboard(request_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=DEAL_KEYBOARD_TEXT.APPROVE_WITHDRAWAL,
                    callback_data=f"{DEAL_WITHDRAW_MODERATION_PREFIX}{request_id}:approve",
                )
            ],
            [
                InlineKeyboardButton(
                    text=DEAL_KEYBOARD_TEXT.REJECT_WITHDRAWAL,
                    callback_data=f"{DEAL_WITHDRAW_MODERATION_PREFIX}{request_id}:reject",
                )
            ],
            [InlineKeyboardButton(text=DEAL_KEYBOARD_TEXT.DEAL_HOME, callback_data=DEAL_HOME_ACTION)],
        ]
    )


def _build_pagination_row(
    *,
    previous_callback: str | None,
    next_callback: str | None,
    page_info: PageInfo,
) -> list[InlineKeyboardButton] | None:
    if not previous_callback and not next_callback:
        return None

    return [
        InlineKeyboardButton(
            text=DEAL_KEYBOARD_TEXT.PAGINATION_PREVIOUS if previous_callback else DEAL_KEYBOARD_TEXT.PAGINATION_PLACEHOLDER,
            callback_data=previous_callback or "noop",
        ),
        InlineKeyboardButton(text=DEAL_KEYBOARD_TEXT.page_info(page_info.page, page_info.total_pages), callback_data="noop"),
        InlineKeyboardButton(
            text=DEAL_KEYBOARD_TEXT.PAGINATION_NEXT if next_callback else DEAL_KEYBOARD_TEXT.PAGINATION_PLACEHOLDER,
            callback_data=next_callback or "noop",
        ),
    ]


def _format_status(status: str) -> str:
    return DEAL_KEYBOARD_TEXT.STATUS_LABELS.get(status, status)


def _truncate_text(value: str, limit: int) -> str:
    normalized = " ".join(value.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 1].rstrip() + "..."
