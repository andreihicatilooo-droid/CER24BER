from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from cerber_bot.db.models import UserOrder, utcnow


class UserOrderRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def top_product_ids(self, *, limit: int = 10, provider: str | None = None) -> list[str]:
        """Вернуть список product_id, отсортированных по количеству успешных покупок DESC.

        Args:
            limit:    Максимальное количество записей.
            provider: Фильтр по провайдеру (например 'giftapi'). None — все.
        """
        query = (
            select(UserOrder.product_id, func.count(UserOrder.id).label("cnt"))
            .where(UserOrder.status == "completed")
        )
        if provider is not None:
            query = query.where(UserOrder.provider == provider)
        query = (
            query
            .group_by(UserOrder.product_id)
            .order_by(func.count(UserOrder.id).desc())
            .limit(limit)
        )
        result = await self.session.execute(query)
        return [row.product_id for row in result.all()]

    async def create(
        self,
        *,
        telegram_id: int,
        external_id: str,
        provider_order_id: str | None,
        provider: str,
        product_id: str,
        product_name: str,
        sku_id: str,
        sku_name: str,
        status: str,
        total_amount: Decimal,
        currency: str,
        delivery_payload: str | None,
        error_message: str | None,
    ) -> UserOrder:
        now = utcnow()
        order = UserOrder(
            telegram_id=telegram_id,
            external_id=external_id,
            provider_order_id=provider_order_id,
            provider=provider,
            product_id=product_id,
            product_name=product_name,
            sku_id=sku_id,
            sku_name=sku_name,
            status=status,
            total_amount=total_amount,
            currency=currency,
            delivery_payload=delivery_payload,
            error_message=error_message,
            created_at=now,
            updated_at=now,
        )
        self.session.add(order)
        await self.session.flush()
        return order

    async def count_by_telegram_id(self, telegram_id: int) -> int:
        query = select(func.count(UserOrder.id)).where(UserOrder.telegram_id == telegram_id)
        result = await self.session.execute(query)
        return int(result.scalar_one())

    async def list_by_telegram_id(self, telegram_id: int, *, offset: int, limit: int) -> list[UserOrder]:
        query = (
            select(UserOrder)
            .where(UserOrder.telegram_id == telegram_id)
            .order_by(UserOrder.id.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_for_user(self, order_id: int, telegram_id: int) -> UserOrder | None:
        query = select(UserOrder).where(UserOrder.id == order_id, UserOrder.telegram_id == telegram_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()