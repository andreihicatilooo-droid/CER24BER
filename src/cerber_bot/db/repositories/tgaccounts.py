from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cerber_bot.db.models import TgAccountPurchase, utcnow


class TgAccountRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        telegram_id: int,
        getmytg_purchase_id: int,
        country_code: str,
        status: str,
        amount: Decimal,
        currency: str,
        purchase_type: str,
        phone_number: str | None = None,
        verification_code: str | None = None,
        verification_password: str | None = None,
    ) -> TgAccountPurchase:
        now = utcnow()
        purchase = TgAccountPurchase(
            telegram_id=telegram_id,
            getmytg_purchase_id=getmytg_purchase_id,
            country_code=country_code,
            phone_number=phone_number,
            status=status,
            amount=amount,
            currency=currency,
            verification_code=verification_code,
            verification_password=verification_password,
            purchase_type=purchase_type,
            created_at=now,
            updated_at=now,
        )
        self.session.add(purchase)
        await self.session.flush()
        return purchase

    async def get_by_id(self, purchase_id: int) -> TgAccountPurchase | None:
        query = select(TgAccountPurchase).where(TgAccountPurchase.id == purchase_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_getmytg_id(self, getmytg_purchase_id: int) -> TgAccountPurchase | None:
        query = select(TgAccountPurchase).where(TgAccountPurchase.getmytg_purchase_id == getmytg_purchase_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list_by_telegram_id(self, telegram_id: int) -> list[TgAccountPurchase]:
        query = (
            select(TgAccountPurchase)
            .where(TgAccountPurchase.telegram_id == telegram_id)
            .order_by(TgAccountPurchase.id.desc())
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def update_status(
        self,
        purchase: TgAccountPurchase,
        *,
        status: str,
        phone_number: str | None = None,
    ) -> TgAccountPurchase:
        purchase.status = status
        if phone_number is not None:
            purchase.phone_number = phone_number
        purchase.updated_at = utcnow()
        await self.session.flush()
        return purchase

    async def update_verification(
        self,
        purchase: TgAccountPurchase,
        *,
        verification_code: str | None,
        verification_password: str | None,
    ) -> TgAccountPurchase:
        purchase.verification_code = verification_code
        purchase.verification_password = verification_password
        purchase.updated_at = utcnow()
        await self.session.flush()
        return purchase
