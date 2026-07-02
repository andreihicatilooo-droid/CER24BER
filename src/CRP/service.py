"""Сервис репутации пользователей для CRP."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from cerber_bot.db.models import EscrowDeal, TelegramUser, UserReview, utcnow
from cerber_bot.db.repositories.users import UserRepository


SUCCESS_REPUTATION_POINTS = 1
DISPUTE_REFUND_PENALTY = 2
DISPUTE_RELEASE_PENALTY = 1


@dataclass(slots=True, frozen=True)
class ReputationView:
    telegram_id: int
    score: int
    dispute_losses: int
    updated_at: object

    @classmethod
    def empty(cls, telegram_id: int) -> "ReputationView":
        return cls(telegram_id=telegram_id, score=0, dispute_losses=0, updated_at=utcnow())


@dataclass(slots=True, frozen=True)
class ReviewView:
    id: int
    rater_telegram_id: int
    rated_telegram_id: int
    deal_id: int | None
    score: int
    comment: str | None
    created_at: datetime


class NicknameAlreadySetError(RuntimeError):
    pass


class InvalidReviewError(RuntimeError):
    pass


class ReputationService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def get_user_reputation(self, telegram_id: int) -> ReputationView:
        async with self.session_factory() as session:
            repository = UserRepository(session)
            user = await repository.get_by_telegram_id(telegram_id)
            if user is None:
                return ReputationView.empty(telegram_id)
            return self._to_view(user)

    async def get_display_name(self, telegram_id: int) -> str:
        async with self.session_factory() as session:
            repository = UserRepository(session)
            user = await repository.get_by_telegram_id(telegram_id)
            return self._display_name(user, telegram_id)

    async def set_nickname(self, telegram_id: int, nickname: str) -> TelegramUser:
        normalized = nickname.strip()
        if not normalized:
            raise NicknameAlreadySetError("Никнейм не может быть пустым.")
        if len(normalized) > 64:
            raise NicknameAlreadySetError("Никнейм слишком длинный (максимум 64 символа).")

        async with self.session_factory() as session:
            repository = UserRepository(session)
            user = await repository.get_by_telegram_id(telegram_id)
            if user is None:
                raise NicknameAlreadySetError("Пользователь не найден.")
            if user.nickname is not None or user.nickname_changed_at is not None:
                raise NicknameAlreadySetError("Никнейм можно сменить только один раз.")
            user.nickname = normalized
            user.nickname_changed_at = utcnow()
            user.updated_at = utcnow()
            await session.commit()
            return user

    async def add_review(
        self,
        *,
        rater_telegram_id: int,
        rated_telegram_id: int,
        score: int,
        comment: str | None = None,
        deal_id: int | None = None,
    ) -> ReviewView:
        if rater_telegram_id == rated_telegram_id:
            raise InvalidReviewError("Нельзя оставлять отзыв самому себе.")
        if not 1 <= score <= 5:
            raise InvalidReviewError("Оценка должна быть от 1 до 5.")

        async with self.session_factory() as session:
            if deal_id is not None:
                can_review = await self._can_leave_review_for_deal(
                    session,
                    rater_telegram_id=rater_telegram_id,
                    rated_telegram_id=rated_telegram_id,
                    deal_id=deal_id,
                )
                if not can_review:
                    raise InvalidReviewError("Нельзя оставить отзыв по этой сделке.")

            review = UserReview(
                rater_telegram_id=rater_telegram_id,
                rated_telegram_id=rated_telegram_id,
                deal_id=deal_id,
                score=score,
                comment=comment.strip() if comment else None,
                created_at=utcnow(),
            )
            session.add(review)
            await session.commit()
            return self._to_review_view(review)

    async def get_reviews_for_user(self, telegram_id: int, *, limit: int = 50) -> list[ReviewView]:
        async with self.session_factory() as session:
            result = await session.execute(
                select(UserReview)
                .where(UserReview.rated_telegram_id == telegram_id)
                .order_by(UserReview.created_at.desc())
                .limit(limit)
            )
            return [self._to_review_view(item) for item in result.scalars().all()]

    async def get_reviews_by_user(self, telegram_id: int, *, limit: int = 50) -> list[ReviewView]:
        async with self.session_factory() as session:
            result = await session.execute(
                select(UserReview)
                .where(UserReview.rater_telegram_id == telegram_id)
                .order_by(UserReview.created_at.desc())
                .limit(limit)
            )
            return [self._to_review_view(item) for item in result.scalars().all()]

    async def can_leave_review(
        self,
        *,
        rater_telegram_id: int,
        rated_telegram_id: int,
        deal_id: int | None = None,
    ) -> bool:
        if rater_telegram_id == rated_telegram_id:
            return False

        async with self.session_factory() as session:
            if deal_id is not None:
                return await self._can_leave_review_for_deal(
                    session,
                    rater_telegram_id=rater_telegram_id,
                    rated_telegram_id=rated_telegram_id,
                    deal_id=deal_id,
                )

            result = await session.execute(
                select(EscrowDeal)
                .where(
                    EscrowDeal.status == "completed",
                    (
                        (EscrowDeal.buyer_telegram_id == rater_telegram_id)
                        & (EscrowDeal.seller_telegram_id == rated_telegram_id)
                    )
                    | (
                        (EscrowDeal.seller_telegram_id == rater_telegram_id)
                        & (EscrowDeal.buyer_telegram_id == rated_telegram_id)
                    ),
                )
                .limit(1)
            )
            return result.scalar_one_or_none() is not None

    async def _can_leave_review_for_deal(
        self,
        session: AsyncSession,
        *,
        rater_telegram_id: int,
        rated_telegram_id: int,
        deal_id: int,
    ) -> bool:
        deal_result = await session.execute(
            select(EscrowDeal)
            .where(
                EscrowDeal.id == deal_id,
                EscrowDeal.status == "completed",
                (
                    (EscrowDeal.buyer_telegram_id == rater_telegram_id)
                    & (EscrowDeal.seller_telegram_id == rated_telegram_id)
                )
                | (
                    (EscrowDeal.seller_telegram_id == rater_telegram_id)
                    & (EscrowDeal.buyer_telegram_id == rated_telegram_id)
                ),
            )
            .limit(1)
        )
        deal = deal_result.scalar_one_or_none()
        if deal is None:
            return False

        existing_result = await session.execute(
            select(UserReview)
            .where(
                UserReview.deal_id == deal_id,
                UserReview.rater_telegram_id == rater_telegram_id,
                UserReview.rated_telegram_id == rated_telegram_id,
            )
            .limit(1)
        )
        return existing_result.scalar_one_or_none() is None

    def _to_view(self, user: TelegramUser) -> ReputationView:
        return ReputationView(
            telegram_id=user.telegram_id,
            score=int(user.reputation_score or 0),
            dispute_losses=int(user.reputation_dispute_losses or 0),
            updated_at=user.reputation_updated_at,
        )

    def _to_review_view(self, review: UserReview) -> ReviewView:
        return ReviewView(
            id=review.id,
            rater_telegram_id=review.rater_telegram_id,
            rated_telegram_id=review.rated_telegram_id,
            deal_id=review.deal_id,
            score=review.score,
            comment=review.comment,
            created_at=review.created_at,
        )

    def _display_name(self, user: TelegramUser | None, telegram_id: int | None = None) -> str:
        if user is not None and user.nickname:
            return user.nickname
        if user is not None and user.username:
            return f"@{user.username}"
        if user is not None:
            full_name = " ".join(part for part in (user.first_name, user.last_name) if part)
            if full_name:
                return full_name
            telegram_id = user.telegram_id
        if telegram_id is None:
            return "unknown"
        return f"ID {telegram_id}"
