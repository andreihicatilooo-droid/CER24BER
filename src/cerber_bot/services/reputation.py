"""Сервис репутации: отзывы и рейтинг участников гарант-сделок."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from cerber_bot.db.repositories.deals import EscrowDealRepository
from cerber_bot.db.repositories.reviews import DealReviewRepository
from cerber_bot.db.repositories.users import UserRepository
from cerber_bot.texts import REVIEW_TEXT


REVIEWABLE_DEAL_STATUSES = {"completed", "refunded"}


class ReputationServiceError(RuntimeError):
    pass


@dataclass(slots=True, frozen=True)
class ReviewView:
    review_id: int
    deal_id: int
    reviewer_display: str
    rating: int
    comment: str | None
    created_at: datetime


@dataclass(slots=True, frozen=True)
class ReputationSummary:
    telegram_id: int
    review_count: int
    average_rating: float
    positive_count: int
    negative_count: int

    @property
    def stars(self) -> str:
        full = round(self.average_rating)
        return "★" * full + "☆" * (5 - full)


class ReputationService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def create_review(
        self,
        reviewer_telegram_id: int,
        *,
        deal_id: int,
        rating: int,
        comment: str | None,
    ) -> ReviewView:
        if rating < 1 or rating > 5:
            raise ReputationServiceError(REVIEW_TEXT.RATING_OUT_OF_RANGE)

        normalized_comment = (comment or "").strip() or None
        if normalized_comment is not None and len(normalized_comment) > 500:
            normalized_comment = normalized_comment[:500]

        async with self.session_factory() as session:
            deal_repository = EscrowDealRepository(session)
            review_repository = DealReviewRepository(session)
            user_repository = UserRepository(session)

            deal = await deal_repository.get_for_user(deal_id, reviewer_telegram_id)
            if deal is None:
                raise ReputationServiceError(REVIEW_TEXT.DEAL_NOT_FOUND)
            if deal.status not in REVIEWABLE_DEAL_STATUSES:
                raise ReputationServiceError(REVIEW_TEXT.DEAL_NOT_FINISHED)

            existing = await review_repository.get_for_deal_and_reviewer(deal_id, reviewer_telegram_id)
            if existing is not None:
                raise ReputationServiceError(REVIEW_TEXT.ALREADY_REVIEWED)

            target_telegram_id = (
                deal.seller_telegram_id
                if reviewer_telegram_id == deal.buyer_telegram_id
                else deal.buyer_telegram_id
            )
            review = await review_repository.add(
                deal_id=deal_id,
                reviewer_telegram_id=reviewer_telegram_id,
                target_telegram_id=target_telegram_id,
                rating=rating,
                comment=normalized_comment,
            )
            await session.commit()

            reviewer = await user_repository.get_by_telegram_id(reviewer_telegram_id)
            return ReviewView(
                review_id=review.id,
                deal_id=deal_id,
                reviewer_display=_display_name(reviewer, reviewer_telegram_id),
                rating=rating,
                comment=normalized_comment,
                created_at=review.created_at,
            )

    async def has_review(self, reviewer_telegram_id: int, deal_id: int) -> bool:
        async with self.session_factory() as session:
            review_repository = DealReviewRepository(session)
            return await review_repository.get_for_deal_and_reviewer(deal_id, reviewer_telegram_id) is not None

    async def get_summary(self, telegram_id: int) -> ReputationSummary:
        async with self.session_factory() as session:
            review_repository = DealReviewRepository(session)
            count, average, positive, negative = await review_repository.aggregate_for_target(telegram_id)
            return ReputationSummary(
                telegram_id=telegram_id,
                review_count=count,
                average_rating=round(average, 2),
                positive_count=positive,
                negative_count=negative,
            )

    async def list_reviews(self, telegram_id: int, *, limit: int = 10) -> tuple[ReviewView, ...]:
        async with self.session_factory() as session:
            review_repository = DealReviewRepository(session)
            user_repository = UserRepository(session)
            reviews = await review_repository.list_for_target(telegram_id, limit=limit)
            reviewer_ids = {review.reviewer_telegram_id for review in reviews}
            users = await user_repository.list_by_telegram_ids(reviewer_ids)
            return tuple(
                ReviewView(
                    review_id=review.id,
                    deal_id=review.deal_id,
                    reviewer_display=_display_name(users.get(review.reviewer_telegram_id), review.reviewer_telegram_id),
                    rating=review.rating,
                    comment=review.comment,
                    created_at=review.created_at,
                )
                for review in reviews
            )


def _display_name(user, telegram_id: int) -> str:
    if user is not None:
        if user.display_name:
            return user.display_name
        if user.username:
            return f"@{user.username}"
        full_name = " ".join(part for part in (user.first_name, user.last_name) if part)
        if full_name:
            return full_name
    return f"ID {telegram_id}"
