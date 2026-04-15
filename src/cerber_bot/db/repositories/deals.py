from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from cerber_bot.db.models import EscrowDeal, EscrowDealMessage, WithdrawalRequest, utcnow


class EscrowDealRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        buyer_telegram_id: int,
        seller_telegram_id: int,
        status: str,
        amount: Decimal,
        currency: str,
        terms: str,
    ) -> EscrowDeal:
        now = utcnow()
        deal = EscrowDeal(
            buyer_telegram_id=buyer_telegram_id,
            seller_telegram_id=seller_telegram_id,
            status=status,
            amount=amount,
            currency=currency,
            terms=terms,
            created_at=now,
            updated_at=now,
        )
        self.session.add(deal)
        await self.session.flush()
        return deal

    async def get_by_id(self, deal_id: int) -> EscrowDeal | None:
        query = select(EscrowDeal).where(EscrowDeal.id == deal_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_for_user(self, deal_id: int, telegram_id: int) -> EscrowDeal | None:
        query = select(EscrowDeal).where(
            EscrowDeal.id == deal_id,
            or_(EscrowDeal.buyer_telegram_id == telegram_id, EscrowDeal.seller_telegram_id == telegram_id),
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list_for_user(self, telegram_id: int, *, offset: int, limit: int) -> list[EscrowDeal]:
        query = (
            select(EscrowDeal)
            .where(or_(EscrowDeal.buyer_telegram_id == telegram_id, EscrowDeal.seller_telegram_id == telegram_id))
            .order_by(EscrowDeal.id.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def count_for_user(self, telegram_id: int) -> int:
        query = select(func.count(EscrowDeal.id)).where(
            or_(EscrowDeal.buyer_telegram_id == telegram_id, EscrowDeal.seller_telegram_id == telegram_id)
        )
        result = await self.session.execute(query)
        return int(result.scalar_one())

    async def sum_completed_for_user(self, telegram_id: int) -> Decimal:
        query = select(func.coalesce(func.sum(EscrowDeal.amount), 0)).where(
            EscrowDeal.status == "completed",
            or_(EscrowDeal.buyer_telegram_id == telegram_id, EscrowDeal.seller_telegram_id == telegram_id),
        )
        result = await self.session.execute(query)
        return Decimal(str(result.scalar_one()))

    async def count_completed_for_user(self, telegram_id: int) -> int:
        query = select(func.count(EscrowDeal.id)).where(
            EscrowDeal.status == "completed",
            or_(EscrowDeal.buyer_telegram_id == telegram_id, EscrowDeal.seller_telegram_id == telegram_id),
        )
        result = await self.session.execute(query)
        return int(result.scalar_one())

    async def count_disputed_for_user(self, telegram_id: int) -> int:
        query = select(func.count(EscrowDeal.id)).where(
            EscrowDeal.status == "disputed",
            or_(EscrowDeal.buyer_telegram_id == telegram_id, EscrowDeal.seller_telegram_id == telegram_id),
        )
        result = await self.session.execute(query)
        return int(result.scalar_one())

    async def list_disputed(self, *, offset: int = 0, limit: int = 20) -> list[EscrowDeal]:
        """Все сделки со статусом 'disputed', новые сверху."""
        query = (
            select(EscrowDeal)
            .where(EscrowDeal.status == "disputed")
            .order_by(EscrowDeal.id.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def count_disputed(self) -> int:
        query = select(func.count(EscrowDeal.id)).where(EscrowDeal.status == "disputed")
        result = await self.session.execute(query)
        return int(result.scalar_one())

    async def count_open_for_user(self, telegram_id: int) -> int:
        query = select(func.count(EscrowDeal.id)).where(
            EscrowDeal.status.in_(("pending_acceptance", "active", "disputed")),
            or_(EscrowDeal.buyer_telegram_id == telegram_id, EscrowDeal.seller_telegram_id == telegram_id),
        )
        result = await self.session.execute(query)
        return int(result.scalar_one())


class EscrowDealMessageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(
        self,
        *,
        deal_id: int,
        sender_telegram_id: int,
        sender_role: str,
        content_type: str,
        body: str,
    ) -> EscrowDealMessage:
        message = EscrowDealMessage(
            deal_id=deal_id,
            sender_telegram_id=sender_telegram_id,
            sender_role=sender_role,
            content_type=content_type,
            body=body,
            created_at=utcnow(),
        )
        self.session.add(message)
        await self.session.flush()
        return message

    async def list_recent(self, deal_id: int, *, limit: int = 8) -> list[EscrowDealMessage]:
        query = (
            select(EscrowDealMessage)
            .where(EscrowDealMessage.deal_id == deal_id)
            .order_by(EscrowDealMessage.id.desc())
            .limit(limit)
        )
        result = await self.session.execute(query)
        items = list(result.scalars().all())
        items.reverse()
        return items


class WithdrawalRequestRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        telegram_id: int,
        status: str,
        amount: Decimal,
        amount_usdt: Decimal,
        currency: str,
        network: str,
        address: str,
    ) -> WithdrawalRequest:
        now = utcnow()
        request = WithdrawalRequest(
            telegram_id=telegram_id,
            status=status,
            amount=amount,
            amount_usdt=amount_usdt,
            currency=currency,
            network=network,
            address=address,
            created_at=now,
            updated_at=now,
        )
        self.session.add(request)
        await self.session.flush()
        return request

    async def get_by_id(self, request_id: int) -> WithdrawalRequest | None:
        query = select(WithdrawalRequest).where(WithdrawalRequest.id == request_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_for_user(self, request_id: int, telegram_id: int) -> WithdrawalRequest | None:
        query = select(WithdrawalRequest).where(
            WithdrawalRequest.id == request_id,
            WithdrawalRequest.telegram_id == telegram_id,
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_open_for_user(self, telegram_id: int) -> WithdrawalRequest | None:
        query = (
            select(WithdrawalRequest)
            .where(WithdrawalRequest.telegram_id == telegram_id, WithdrawalRequest.status == "requested")
            .order_by(WithdrawalRequest.id.desc())
            .limit(1)
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def count_open_for_user(self, telegram_id: int) -> int:
        query = select(func.count(WithdrawalRequest.id)).where(
            WithdrawalRequest.telegram_id == telegram_id,
            WithdrawalRequest.status == "requested",
        )
        result = await self.session.execute(query)
        return int(result.scalar_one())

    async def list_pending(self, *, offset: int = 0, limit: int = 20) -> list[WithdrawalRequest]:
        """Все заявки на вывод со статусом 'requested', новые сверху."""
        query = (
            select(WithdrawalRequest)
            .where(WithdrawalRequest.status == "requested")
            .order_by(WithdrawalRequest.id.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def count_pending(self) -> int:
        query = select(func.count(WithdrawalRequest.id)).where(
            WithdrawalRequest.status == "requested",
        )
        result = await self.session.execute(query)
        return int(result.scalar_one())