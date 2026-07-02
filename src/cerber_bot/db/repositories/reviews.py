"""Репозиторий отзывов по гарант-сделкам."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from cerber_bot.db.models import DealReview


class DealReviewRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(
        self,
        *,
        deal_id: int,
        reviewer_telegram_id: int,
        target_telegram_id: int,
        rating: int,
        comment: str | None,
    ) -> DealReview:
        review = DealReview(
            deal_id=deal_id,
            reviewer_telegram_id=reviewer_telegram_id,
            target_telegram_id=target_telegram_id,
            rating=rating,
            comment=comment,
        )
        self.session.add(review)
        await self.session.flush()
        return review

    async def get_for_deal_and_reviewer(self, deal_id: int, reviewer_telegram_id: int) -> DealReview | None:
        query = select(DealReview).where(
            DealReview.deal_id == deal_id,
            DealReview.reviewer_telegram_id == reviewer_telegram_id,
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list_for_target(self, target_telegram_id: int, *, limit: int = 10) -> list[DealReview]:
        query = (
            select(DealReview)
            .where(DealReview.target_telegram_id == target_telegram_id)
            .order_by(DealReview.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def aggregate_for_target(self, target_telegram_id: int) -> tuple[int, float, int, int]:
        """Возвращает (кол-во, средний рейтинг, положительных 4-5, отрицательных 1-2)."""
        result = await self.session.execute(
            select(func.count(DealReview.id), func.coalesce(func.avg(DealReview.rating), 0.0)).where(
                DealReview.target_telegram_id == target_telegram_id
            )
        )
        count, average = result.one()
        positive = await self._count_by_rating(target_telegram_id, minimum=4)
        negative = await self._count_by_rating(target_telegram_id, maximum=2)
        return int(count), float(average), positive, negative

    async def _count_by_rating(self, target_telegram_id: int, *, minimum: int | None = None, maximum: int | None = None) -> int:
        query = select(func.count(DealReview.id)).where(DealReview.target_telegram_id == target_telegram_id)
        if minimum is not None:
            query = query.where(DealReview.rating >= minimum)
        if maximum is not None:
            query = query.where(DealReview.rating <= maximum)
        result = await self.session.execute(query)
        return int(result.scalar_one())
