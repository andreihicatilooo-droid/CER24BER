from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cerber_bot.db.models import WalletTransaction, utcnow


class WalletTransactionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(
        self,
        *,
        telegram_id: int,
        transaction_type: str,
        amount: Decimal,
        currency: str,
        description: str,
        reference: str | None = None,
    ) -> WalletTransaction:
        transaction = WalletTransaction(
            telegram_id=telegram_id,
            transaction_type=transaction_type,
            amount=amount,
            currency=currency,
            description=description,
            reference=reference,
            created_at=utcnow(),
        )
        self.session.add(transaction)
        await self.session.flush()
        return transaction

    async def list_recent(self, telegram_id: int, limit: int = 10) -> list[WalletTransaction]:
        query = (
            select(WalletTransaction)
            .where(WalletTransaction.telegram_id == telegram_id)
            .order_by(WalletTransaction.id.desc())
            .limit(limit)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_by_reference(self, reference: str) -> WalletTransaction | None:
        query = (
            select(WalletTransaction)
            .where(WalletTransaction.reference == reference)
            .order_by(WalletTransaction.id.desc())
            .limit(1)
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()