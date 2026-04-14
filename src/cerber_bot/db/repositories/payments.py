from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cerber_bot.db.models import WalletPayment, utcnow


class WalletPaymentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_pending(
        self,
        *,
        telegram_id: int,
        payload: str,
        provider: str,
        amount,
        currency: str,
        title: str,
        description: str,
    ) -> WalletPayment:
        now = utcnow()
        payment = WalletPayment(
            telegram_id=telegram_id,
            payload=payload,
            provider=provider,
            status="pending",
            amount=amount,
            currency=currency,
            title=title,
            description=description,
            created_at=now,
            updated_at=now,
            paid_at=None,
        )
        self.session.add(payment)
        await self.session.flush()
        return payment

    async def get_by_payload(self, payload: str) -> WalletPayment | None:
        query = select(WalletPayment).where(WalletPayment.payload == payload)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def mark_paid(
        self,
        payment: WalletPayment,
        *,
        provider_reference: str | None,
        provider_payment_id: str | None,
    ) -> WalletPayment:
        now = utcnow()
        payment.status = "paid"
        payment.telegram_payment_charge_id = provider_reference
        payment.provider_payment_charge_id = provider_payment_id
        payment.paid_at = now
        payment.updated_at = now
        await self.session.flush()
        return payment

    async def mark_failed(
        self,
        payment: WalletPayment,
        *,
        provider_reference: str | None,
        provider_payment_id: str | None,
    ) -> WalletPayment:
        payment.status = "error"
        payment.telegram_payment_charge_id = provider_reference
        payment.provider_payment_charge_id = provider_payment_id
        payment.updated_at = utcnow()
        await self.session.flush()
        return payment