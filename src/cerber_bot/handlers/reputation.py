"""Обработчики репутации, отзывов, смены имени и приглашений."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from html import escape

from aiogram import F, Router
from aiogram.exceptions import AiogramError
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from cerber_bot.container import AppContainer
from cerber_bot.keyboards.deals import REVIEW_RATE_PREFIX, REVIEW_START_PREFIX, build_review_rating_keyboard
from cerber_bot.keyboards.main_menu import (
    CHANGE_NAME_ACTION,
    MY_REVIEWS_ACTION,
    REFERRALS_ACTION,
    USER_SEARCH_ACTION,
    build_cerber_trade_menu,
    build_profile_keyboard,
)
from cerber_bot.services.reputation import ReputationServiceError, ReputationSummary, ReviewView
from cerber_bot.services.store import format_money
from cerber_bot.texts import ACCOUNT_TEXT, REFERRAL_TEXT, REVIEW_TEXT, SEARCH_TEXT


logger = logging.getLogger(__name__)


class ReputationStates(StatesGroup):
    waiting_for_review_comment = State()
    waiting_for_new_name = State()
    waiting_for_user_search = State()


def build_reputation_router(container: AppContainer) -> Router:
    router = Router(name="reputation")

    # ── Отзывы ──────────────────────────────────────────────

    @router.callback_query(F.data.startswith(REVIEW_START_PREFIX))
    async def handle_review_start(callback: CallbackQuery, state: FSMContext) -> None:
        message = _message(callback)
        if message is None:
            await callback.answer()
            return

        deal_id = _int_suffix(callback.data or "", REVIEW_START_PREFIX)
        await state.set_state(None)
        await message.answer(
            REVIEW_TEXT.RATING_PROMPT.format(deal_id=deal_id),
            reply_markup=build_review_rating_keyboard(deal_id),
        )
        await callback.answer(REVIEW_TEXT.CALLBACK_WAIT_RATING)

    @router.callback_query(F.data.startswith(REVIEW_RATE_PREFIX))
    async def handle_review_rate(callback: CallbackQuery, state: FSMContext) -> None:
        message = _message(callback)
        if message is None or callback.from_user is None:
            await callback.answer()
            return

        raw = (callback.data or "").removeprefix(REVIEW_RATE_PREFIX)
        try:
            deal_part, rating_part = raw.split(":", 1)
            deal_id, rating = int(deal_part), int(rating_part)
        except ValueError:
            await callback.answer()
            return

        await state.update_data(review_deal_id=deal_id, review_rating=rating)
        await state.set_state(ReputationStates.waiting_for_review_comment)
        await message.answer(REVIEW_TEXT.COMMENT_PROMPT)
        await callback.answer()

    @router.message(ReputationStates.waiting_for_review_comment)
    async def handle_review_comment(message: Message, state: FSMContext) -> None:
        if message.from_user is None:
            return

        data = await state.get_data()
        deal_id = int(data.get("review_deal_id", 0))
        rating = int(data.get("review_rating", 0))
        comment = (message.text or "").strip()
        if comment.lower() in REVIEW_TEXT.SKIP_WORDS:
            comment = ""

        try:
            review = await container.reputation_service.create_review(
                message.from_user.id,
                deal_id=deal_id,
                rating=rating,
                comment=comment or None,
            )
        except ReputationServiceError as error:
            await state.clear()
            await message.answer(escape(str(error)))
            return

        await state.clear()
        await message.answer(REVIEW_TEXT.SAVED)

        deal = await container.deal_service.get_deal_view(message.from_user.id, deal_id)
        if deal is not None:
            await _notify_review_target(message, review, target_id=deal.counterpart.telegram_id)

    async def _notify_review_target(message: Message, review: ReviewView, *, target_id: int) -> None:
        if message.bot is None or target_id <= 0:
            return
        lines = [
            REVIEW_TEXT.REVIEW_NOTIFICATION_TITLE,
            REVIEW_TEXT.REVIEW_NOTIFICATION_ROW.format(
                deal_id=review.deal_id,
                stars=REVIEW_TEXT.stars(review.rating),
            ),
        ]
        if review.comment:
            lines.append(escape(review.comment))
        try:
            await message.bot.send_message(target_id, "\n".join(lines), parse_mode="HTML")
        except AiogramError:
            logger.debug("Не удалось уведомить пользователя %s о новом отзыве", target_id)

    @router.callback_query(F.data == MY_REVIEWS_ACTION)
    async def handle_my_reviews(callback: CallbackQuery, state: FSMContext) -> None:
        message = _message(callback)
        if message is None or callback.from_user is None:
            await callback.answer()
            return

        await state.set_state(None)
        summary = await container.reputation_service.get_summary(callback.from_user.id)
        reviews = await container.reputation_service.list_reviews(callback.from_user.id)
        await message.answer(
            render_reviews(summary, reviews),
            reply_markup=build_cerber_trade_menu(container.settings),
        )
        await callback.answer()

    # ── Смена имени (один раз) ─────────────────────────────

    @router.callback_query(F.data == CHANGE_NAME_ACTION)
    async def handle_change_name_prompt(callback: CallbackQuery, state: FSMContext) -> None:
        message = _message(callback)
        if message is None or callback.from_user is None:
            await callback.answer()
            return

        profile = await container.user_service.get_profile(callback.from_user.id)
        if profile is not None and profile.name_changed_at is not None:
            await message.answer(ACCOUNT_TEXT.NAME_ALREADY_CHANGED)
            await callback.answer()
            return

        await state.clear()
        await state.set_state(ReputationStates.waiting_for_new_name)
        await message.answer(ACCOUNT_TEXT.NAME_PROMPT)
        await callback.answer()

    @router.message(ReputationStates.waiting_for_new_name)
    async def handle_change_name(message: Message, state: FSMContext) -> None:
        if message.from_user is None:
            return

        try:
            user = await container.user_service.change_display_name(message.from_user.id, message.text or "")
        except ValueError as error:
            await message.answer(escape(str(error)))
            return

        await state.clear()
        await message.answer(ACCOUNT_TEXT.NAME_CHANGED.format(name=escape(user.display_name or "")))

    # ── Приглашения ────────────────────────────────────────

    @router.callback_query(F.data == REFERRALS_ACTION)
    async def handle_referrals(callback: CallbackQuery, state: FSMContext) -> None:
        message = _message(callback)
        if message is None or callback.from_user is None:
            await callback.answer()
            return

        await state.set_state(None)
        stats = await container.referral_service.get_stats(callback.from_user.id)
        link = container.referral_service.build_link(callback.from_user.id)
        lines = [
            REFERRAL_TEXT.TITLE,
            REFERRAL_TEXT.INVITED_COUNT.format(count=stats.invited_count),
            "",
        ]
        if link:
            lines.append(REFERRAL_TEXT.YOUR_LINK)
            lines.append(escape(link))
        else:
            lines.append(REFERRAL_TEXT.LINK_UNAVAILABLE)
        await message.answer("\n".join(lines), reply_markup=build_cerber_trade_menu(container.settings))
        await callback.answer()

    # ── Поиск по юзернейму: профиль + история ──────────────

    @router.callback_query(F.data == USER_SEARCH_ACTION)
    async def handle_user_search_prompt(callback: CallbackQuery, state: FSMContext) -> None:
        message = _message(callback)
        if message is None:
            await callback.answer()
            return

        await state.clear()
        await state.set_state(ReputationStates.waiting_for_user_search)
        await message.answer(SEARCH_TEXT.PROMPT)
        await callback.answer()

    @router.message(ReputationStates.waiting_for_user_search)
    async def handle_user_search(message: Message, state: FSMContext) -> None:
        identifier = (message.text or "").strip()
        target = await container.user_service.find_user(identifier)
        if target is None:
            await message.answer(SEARCH_TEXT.NOT_FOUND)
            return

        await state.clear()
        summary = await container.reputation_service.get_summary(target.telegram_id)
        reviews = await container.reputation_service.list_reviews(target.telegram_id, limit=5)
        total, completed, disputed, volume = await container.deal_service.get_public_stats(target.telegram_id)
        showcase = await container.deal_service.list_template_offers(target.telegram_id, limit=5)

        display_name = target.display_name or " ".join(
            part for part in (target.first_name, target.last_name) if part
        ) or f"ID {target.telegram_id}"
        username = f"@{target.username}" if target.username else SEARCH_TEXT.USERNAME_UNKNOWN
        created_at = target.created_at.astimezone(timezone.utc).strftime("%d.%m.%Y")

        lines = [
            SEARCH_TEXT.TITLE,
            SEARCH_TEXT.ROW_NAME.format(name=escape(display_name)),
            SEARCH_TEXT.ROW_USERNAME.format(username=escape(username)),
            SEARCH_TEXT.ROW_ID.format(telegram_id=target.telegram_id),
            SEARCH_TEXT.ROW_REGISTERED.format(created_at=created_at),
            SEARCH_TEXT.ROW_DEALS.format(total=total, completed=completed, disputed=disputed),
            SEARCH_TEXT.ROW_VOLUME.format(
                volume=escape(format_money(volume, target.balance_currency or "USD"))
            ),
            "",
            REVIEW_TEXT.REVIEWS_SUMMARY.format(
                stars=summary.stars,
                average=f"{summary.average_rating:.2f}",
                count=summary.review_count,
                positive=summary.positive_count,
                negative=summary.negative_count,
            ),
        ]

        lines.append("")
        lines.append(SEARCH_TEXT.HISTORY_TITLE)
        if reviews:
            for review in reviews:
                lines.append(
                    REVIEW_TEXT.REVIEW_ROW.format(
                        stars=REVIEW_TEXT.stars(review.rating),
                        created_at=_format_timestamp(review.created_at),
                        reviewer=escape(review.reviewer_display),
                    )
                )
                if review.comment:
                    lines.append(REVIEW_TEXT.REVIEW_COMMENT_ROW.format(comment=escape(review.comment)))
        else:
            lines.append(REVIEW_TEXT.REVIEWS_EMPTY)

        lines.append("")
        lines.append(SEARCH_TEXT.SHOWCASE_TITLE)
        if showcase:
            for offer in showcase:
                lines.append(
                    SEARCH_TEXT.SHOWCASE_ROW.format(
                        terms=escape(offer.terms[:60]),
                        amount=escape(format_money(offer.amount, offer.currency)),
                    )
                )
        else:
            lines.append(SEARCH_TEXT.SHOWCASE_EMPTY)

        await message.answer("\n".join(lines), reply_markup=build_cerber_trade_menu(container.settings))

    return router


def render_reviews(summary: ReputationSummary, reviews: tuple[ReviewView, ...]) -> str:
    lines = [
        REVIEW_TEXT.REVIEWS_TITLE,
        REVIEW_TEXT.REVIEWS_SUMMARY.format(
            stars=summary.stars,
            average=f"{summary.average_rating:.2f}",
            count=summary.review_count,
            positive=summary.positive_count,
            negative=summary.negative_count,
        ),
    ]
    if not reviews:
        lines.append("")
        lines.append(REVIEW_TEXT.REVIEWS_EMPTY)
        return "\n".join(lines)

    for review in reviews:
        lines.append("")
        lines.append(
            REVIEW_TEXT.REVIEW_ROW.format(
                stars=REVIEW_TEXT.stars(review.rating),
                created_at=_format_timestamp(review.created_at),
                reviewer=escape(review.reviewer_display),
            )
        )
        if review.comment:
            lines.append(REVIEW_TEXT.REVIEW_COMMENT_ROW.format(comment=escape(review.comment)))
    return "\n".join(lines)


def _message(callback: CallbackQuery) -> Message | None:
    if isinstance(callback.message, Message):
        return callback.message
    return None


def _int_suffix(value: str, prefix: str) -> int:
    raw = value.removeprefix(prefix)
    try:
        return int(raw)
    except ValueError:
        return 0


def _format_timestamp(value: object) -> str:
    if not isinstance(value, datetime):
        return str(value)
    return value.astimezone(timezone.utc).strftime("%d.%m.%Y")
