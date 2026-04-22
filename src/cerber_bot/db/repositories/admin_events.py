from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cerber_bot.db.models import AdminNotificationEvent, utcnow


class AdminEventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_pending(self, *, event_type: str, payload: str) -> AdminNotificationEvent:
        now = utcnow()
        event = AdminNotificationEvent(
            event_type=event_type,
            status="pending",
            payload=payload,
            attempts=0,
            last_error=None,
            created_at=now,
            updated_at=now,
            delivered_at=None,
        )
        self.session.add(event)
        await self.session.flush()
        return event

    async def list_pending(self, *, limit: int = 20) -> list[AdminNotificationEvent]:
        query = (
            select(AdminNotificationEvent)
            .where(AdminNotificationEvent.status == "pending")
            .order_by(AdminNotificationEvent.id.asc())
            .limit(limit)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def mark_delivered(self, event: AdminNotificationEvent) -> AdminNotificationEvent:
        now = utcnow()
        event.status = "delivered"
        event.attempts += 1
        event.last_error = None
        event.delivered_at = now
        event.updated_at = now
        await self.session.flush()
        return event

    async def mark_retry(self, event: AdminNotificationEvent, *, error: str | None) -> AdminNotificationEvent:
        event.attempts += 1
        event.last_error = error
        event.updated_at = utcnow()
        await self.session.flush()
        return event