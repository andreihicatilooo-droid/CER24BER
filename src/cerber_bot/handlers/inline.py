"""Инлайн-предложения сделок: посты-шаблоны с кнопкой в любые чаты.

Пользователь создаёт шаблон поста в разделе CERBER TRADE (или набирает
@bot <сумма> <условия> прямо в чате). Пост отправляется через inline-режим
и содержит кнопку «Принять сделку» — нажатие создаёт активную гарант-сделку
в боте: средства покупателя блокируются до подтверждения.
"""

from __future__ import annotations

import hashlib
import logging
import uuid as uuid_module
from decimal import Decimal, InvalidOperation
from html import escape

from aiogram import F, Router
from aiogram.exceptions import AiogramError, TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
    Message,
)

from cerber_bot.container import AppContainer
from cerber_bot.keyboards.deals import OFFER_ACCEPT_PREFIX, OFFER_NEW_ACTION, OFFER_ROLE_PREFIX, build_deal_open_keyboard
from cerber_bot.services.deals import DealOfferView, DealServiceError
from cerber_bot.services.store import format_money
from cerber_bot.texts import OFFER_TEXT


logger = logging.getLogger(__name__)


class OfferStates(StatesGroup):
    waiting_for_amount = State()
    waiting_for_terms = State()


def build_inline_router(container: AppContainer) -> Router:
    router = Router(name="inline_offers")
    bot_username = container.settings.bot_username.lstrip("@")

    def offer_post_text(offer: DealOfferView) -> str:
        role = OFFER_TEXT.ROLE_LABELS.get(offer.author_role, offer.author_role)
        return "\n".join(
            [
                OFFER_TEXT.POST_TITLE,
                OFFER_TEXT.POST_AUTHOR.format(author=escape(offer.author_display), role=role),
                OFFER_TEXT.POST_AMOUNT.format(amount=escape(format_money(offer.amount, offer.currency))),
                "",
                OFFER_TEXT.POST_TERMS_TITLE,
                escape(offer.terms),
                "",
                OFFER_TEXT.POST_FOOTER,
            ]
        )

    def offer_post_keyboard(offer_uuid: str, *, accept_enabled: bool = True) -> InlineKeyboardMarkup:
        rows: list[list[InlineKeyboardButton]] = []
        if accept_enabled:
            rows.append(
                [InlineKeyboardButton(text=OFFER_TEXT.BTN_ACCEPT, callback_data=f"{OFFER_ACCEPT_PREFIX}{offer_uuid}")]
            )
        if bot_username:
            rows.append(
                [InlineKeyboardButton(text=OFFER_TEXT.BTN_OPEN_BOT, url=f"https://t.me/{bot_username}")]
            )
        return InlineKeyboardMarkup(inline_keyboard=rows or [[
            InlineKeyboardButton(text=OFFER_TEXT.BTN_ACCEPT, callback_data=f"{OFFER_ACCEPT_PREFIX}{offer_uuid}")
        ]])

    def showcase_article(templates: tuple[DealOfferView, ...]) -> InlineQueryResultArticle:
        """Пост-витрина: несколько товаров продавца, по кнопке на каждый."""
        products = templates[:8]
        author = products[0].author_display
        lines = [
            OFFER_TEXT.SHOWCASE_TITLE,
            OFFER_TEXT.SHOWCASE_AUTHOR.format(author=escape(author)),
            "",
        ]
        buttons: list[list[InlineKeyboardButton]] = []
        for index, offer in enumerate(products, start=1):
            lines.append(
                OFFER_TEXT.SHOWCASE_PRODUCT_ROW.format(
                    index=index,
                    terms=escape(offer.terms[:80]),
                    amount=escape(format_money(offer.amount, offer.currency)),
                )
            )
            buttons.append([
                InlineKeyboardButton(
                    text=OFFER_TEXT.SHOWCASE_PRODUCT_BUTTON.format(
                        index=index,
                        amount=format_money(offer.amount, offer.currency),
                    ),
                    callback_data=f"{OFFER_ACCEPT_PREFIX}{offer.offer_uuid}",
                )
            ])
        lines.append("")
        lines.append(OFFER_TEXT.POST_FOOTER)
        if bot_username:
            buttons.append([InlineKeyboardButton(text=OFFER_TEXT.BTN_OPEN_BOT, url=f"https://t.me/{bot_username}")])
        return InlineQueryResultArticle(
            id=f"showcase_{products[0].author_telegram_id}",
            title=OFFER_TEXT.SHOWCASE_INLINE_TITLE.format(count=len(products)),
            description=OFFER_TEXT.SHOWCASE_INLINE_DESCRIPTION,
            input_message_content=InputTextMessageContent(
                message_text="\n".join(lines),
                parse_mode="HTML",
            ),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        )

    def offer_article(offer: DealOfferView, *, title: str) -> InlineQueryResultArticle:
        return InlineQueryResultArticle(
            id=offer.offer_uuid,
            title=title,
            description=offer.terms[:100],
            input_message_content=InputTextMessageContent(
                message_text=offer_post_text(offer),
                parse_mode="HTML",
            ),
            reply_markup=offer_post_keyboard(offer.offer_uuid),
        )

    # ── Inline-режим ────────────────────────────────────────

    @router.inline_query()
    async def handle_inline_query(query: InlineQuery) -> None:
        text = (query.query or "").strip()
        results: list[InlineQueryResultArticle] = []

        if text.startswith("tpl_"):
            offer = await container.deal_service.get_offer_view(text.removeprefix("tpl_").strip())
            if offer is not None:
                results.append(
                    offer_article(
                        offer,
                        title=OFFER_TEXT.INLINE_TEMPLATE_TITLE.format(
                            amount=format_money(offer.amount, offer.currency),
                            terms=offer.terms[:40],
                        ),
                    )
                )
        elif not text or text.lower() in {"shop", "витрина", "vitrina"}:
            templates = await container.deal_service.list_template_offers(query.from_user.id)
            if len(templates) >= 2:
                results.append(showcase_article(templates))
            for offer in templates:
                results.append(
                    offer_article(
                        offer,
                        title=OFFER_TEXT.INLINE_TEMPLATE_TITLE.format(
                            amount=format_money(offer.amount, offer.currency),
                            terms=offer.terms[:40],
                        ),
                    )
                )
        else:
            parsed = _parse_quick_offer(text)
            if parsed is not None:
                amount, terms = parsed
                for role, title_template in (
                    ("buyer", OFFER_TEXT.INLINE_QUICK_BUYER_TITLE),
                    ("seller", OFFER_TEXT.INLINE_QUICK_SELLER_TITLE),
                ):
                    offer_uuid = _quick_offer_uuid(query.from_user.id, role, amount, terms)
                    try:
                        offer = await container.deal_service.save_offer(
                            query.from_user,
                            offer_uuid=offer_uuid,
                            author_role=role,
                            amount=amount,
                            terms=terms,
                            is_template=False,
                        )
                    except DealServiceError:
                        continue
                    results.append(
                        offer_article(
                            offer,
                            title=title_template.format(amount=format_money(offer.amount, offer.currency)),
                        )
                    )

        if not results:
            results.append(
                InlineQueryResultArticle(
                    id="help",
                    title=OFFER_TEXT.INLINE_HELP_TITLE,
                    description=OFFER_TEXT.INLINE_HELP_DESCRIPTION,
                    input_message_content=InputTextMessageContent(
                        message_text=OFFER_TEXT.INLINE_HELP_MESSAGE.format(bot_username=bot_username or "бота"),
                        parse_mode="HTML",
                    ),
                )
            )

        await query.answer(results[:10], cache_time=1, is_personal=True)

    # ── Принятие предложения из поста ───────────────────────

    @router.callback_query(F.data.startswith(OFFER_ACCEPT_PREFIX))
    async def handle_offer_accept(callback: CallbackQuery) -> None:
        if callback.from_user is None:
            await callback.answer()
            return

        offer_uuid = (callback.data or "").removeprefix(OFFER_ACCEPT_PREFIX)
        try:
            result = await container.deal_service.accept_deal_offer(offer_uuid, callback.from_user)
        except DealServiceError as error:
            await callback.answer(OFFER_TEXT.ACCEPT_FAILED.format(error=str(error)), show_alert=True)
            return

        deal = result.deal

        # Разовое предложение после принятия закрывается — убираем кнопку из поста.
        # Шаблон/витрина остаётся активной для других пользователей.
        offer = await container.deal_service.get_offer_view(offer_uuid)
        if callback.bot is not None and callback.inline_message_id and offer is None:
            try:
                await callback.bot.edit_message_reply_markup(
                    inline_message_id=callback.inline_message_id,
                    reply_markup=offer_post_keyboard(offer_uuid, accept_enabled=False),
                )
            except (TelegramBadRequest, AiogramError):
                pass

        # Уведомляем автора поста в личке
        if callback.bot is not None:
            counterpart = deal.buyer if result.author_telegram_id == deal.seller.telegram_id else deal.seller
            try:
                await callback.bot.send_message(
                    result.author_telegram_id,
                    OFFER_TEXT.DEAL_CREATED_NOTIFICATION.format(
                        deal_id=deal.deal_id,
                        counterpart=escape(counterpart.display_name),
                        amount=escape(format_money(deal.amount, deal.currency)),
                    ),
                    parse_mode="HTML",
                    reply_markup=build_deal_open_keyboard(deal.deal_id),
                )
            except AiogramError:
                logger.debug("Не удалось уведомить автора предложения %s", result.author_telegram_id)

        url = f"https://t.me/{bot_username}?start=deal_{deal.deal_id}" if bot_username else None
        try:
            await callback.answer(OFFER_TEXT.ACCEPT_OK, url=url)
        except TelegramBadRequest:
            await callback.answer(OFFER_TEXT.ACCEPT_OK, show_alert=True)

    # ── Создание шаблона поста из меню CERBER TRADE ────────

    @router.callback_query(F.data == OFFER_NEW_ACTION)
    async def handle_offer_new(callback: CallbackQuery, state: FSMContext) -> None:
        message = _message(callback)
        if message is None:
            await callback.answer()
            return

        await state.clear()
        await message.answer(
            OFFER_TEXT.TEMPLATE_ROLE_PROMPT,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=OFFER_TEXT.ROLE_BUYER, callback_data=f"{OFFER_ROLE_PREFIX}buyer")],
                [InlineKeyboardButton(text=OFFER_TEXT.ROLE_SELLER, callback_data=f"{OFFER_ROLE_PREFIX}seller")],
            ]),
        )
        await callback.answer()

    @router.callback_query(F.data.startswith(OFFER_ROLE_PREFIX))
    async def handle_offer_role(callback: CallbackQuery, state: FSMContext) -> None:
        message = _message(callback)
        if message is None:
            await callback.answer()
            return

        role = (callback.data or "").removeprefix(OFFER_ROLE_PREFIX)
        await state.update_data(offer_role=role if role in {"buyer", "seller"} else "buyer")
        await state.set_state(OfferStates.waiting_for_amount)
        await message.answer(OFFER_TEXT.TEMPLATE_AMOUNT_PROMPT)
        await callback.answer()

    @router.message(OfferStates.waiting_for_amount)
    async def handle_offer_amount(message: Message, state: FSMContext) -> None:
        raw = (message.text or "").replace(",", ".").strip()
        try:
            amount = Decimal(raw)
        except InvalidOperation:
            await message.answer(OFFER_TEXT.TEMPLATE_AMOUNT_PROMPT)
            return
        if amount <= 0:
            await message.answer(OFFER_TEXT.TEMPLATE_AMOUNT_PROMPT)
            return

        await state.update_data(offer_amount=str(amount))
        await state.set_state(OfferStates.waiting_for_terms)
        await message.answer(OFFER_TEXT.TEMPLATE_TERMS_PROMPT)

    @router.message(OfferStates.waiting_for_terms)
    async def handle_offer_terms(message: Message, state: FSMContext) -> None:
        if message.from_user is None:
            return

        data = await state.get_data()
        role = str(data.get("offer_role") or "buyer")
        amount = Decimal(str(data.get("offer_amount") or "0"))
        terms = (message.text or "").strip()

        try:
            offer = await container.deal_service.save_offer(
                message.from_user,
                offer_uuid=uuid_module.uuid4().hex,
                author_role=role,
                amount=amount,
                terms=terms,
                is_template=True,
            )
        except DealServiceError as error:
            await message.answer(escape(str(error)))
            return

        await state.clear()
        hint = (
            OFFER_TEXT.TEMPLATE_SAVED_HINT.format(bot_username=bot_username)
            if bot_username
            else OFFER_TEXT.TEMPLATE_SAVED_HINT_NO_USERNAME
        )
        await message.answer(
            f"{OFFER_TEXT.TEMPLATE_SAVED_TITLE}\n\n{offer_post_text(offer)}\n\n{hint}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=OFFER_TEXT.BTN_SEND_TO_CHAT,
                        switch_inline_query=f"tpl_{offer.offer_uuid}",
                    )
                ],
            ]),
        )

    return router


def _parse_quick_offer(text: str) -> tuple[Decimal, str] | None:
    parts = text.split(maxsplit=1)
    if len(parts) != 2:
        return None
    raw_amount, terms = parts[0].replace(",", "."), parts[1].strip()
    try:
        amount = Decimal(raw_amount)
    except InvalidOperation:
        return None
    if amount <= 0 or len(terms) < 10:
        return None
    return amount, terms


def _quick_offer_uuid(author_id: int, role: str, amount: Decimal, terms: str) -> str:
    payload = f"{author_id}:{role}:{amount}:{terms}".encode("utf-8")
    return hashlib.sha1(payload).hexdigest()[:32]


def _message(callback: CallbackQuery) -> Message | None:
    if isinstance(callback.message, Message):
        return callback.message
    return None
