"""Репозиторий инлайн-предложений (шаблонов постов) сделок."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cerber_bot.db.models import DealOffer, utcnow


class DealOfferRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_uuid(self, uuid: str) -> DealOffer | None:
        result = await self.session.execute(select(DealOffer).where(DealOffer.uuid == uuid))
        return result.scalar_one_or_none()

    async def upsert(
        self,
        *,
        uuid: str,
        author_telegram_id: int,
        author_role: str,
        amount: Decimal,
        currency: str,
        terms: str,
        is_template: bool,
    ) -> DealOffer:
        offer = await self.get_by_uuid(uuid)
        if offer is not None:
            offer.author_role = author_role
            offer.amount = amount
            offer.currency = currency
            offer.terms = terms
            offer.is_template = is_template
            offer.updated_at = utcnow()
            await self.session.flush()
            return offer

        offer = DealOffer(
            uuid=uuid,
            author_telegram_id=author_telegram_id,
            author_role=author_role,
            amount=amount,
            currency=currency,
            terms=terms,
            is_template=is_template,
            status="open",
        )
        self.session.add(offer)
        await self.session.flush()
        return offer

    async def list_templates_for_author(self, author_telegram_id: int, *, limit: int = 10) -> list[DealOffer]:
        query = (
            select(DealOffer)
            .where(
                DealOffer.author_telegram_id == author_telegram_id,
                DealOffer.is_template == True,  # noqa: E712
                DealOffer.status == "open",
            )
            .order_by(DealOffer.updated_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())
