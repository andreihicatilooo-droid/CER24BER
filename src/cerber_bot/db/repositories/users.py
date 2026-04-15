from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from cerber_bot.db.models import TelegramUser, utcnow


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_telegram_id(self, telegram_id: int, *, with_lock: bool = False) -> TelegramUser | None:
        query = select(TelegramUser).where(TelegramUser.telegram_id == telegram_id)
        if with_lock and not self._is_sqlite():
            query = query.with_for_update()
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    def _is_sqlite(self) -> bool:
        try:
            return self.session.get_bind().dialect.name == "sqlite"
        except Exception:
            return False

    async def get_by_username(self, username: str) -> TelegramUser | None:
        normalized = username.strip().lstrip("@").lower()
        if not normalized:
            return None
        query = select(TelegramUser).where(func.lower(TelegramUser.username) == normalized)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def find_by_identifier(self, value: str) -> TelegramUser | None:
        normalized = value.strip()
        if not normalized:
            return None
        if normalized.lstrip("-").isdigit():
            return await self.get_by_telegram_id(int(normalized))
        return await self.get_by_username(normalized)

    async def list_by_telegram_ids(self, telegram_ids: set[int] | tuple[int, ...] | list[int]) -> dict[int, TelegramUser]:
        normalized_ids = tuple(sorted(set(telegram_ids)))
        if not normalized_ids:
            return {}
        query = select(TelegramUser).where(TelegramUser.telegram_id.in_(normalized_ids))
        result = await self.session.execute(query)
        users = list(result.scalars().all())
        return {user.telegram_id: user for user in users}

    async def get_or_create(
        self,
        telegram_id: int,
        username: str | None,
        first_name: str | None,
        last_name: str | None,
        language_code: str | None,
        is_bot: bool,
        balance_currency: str = "USD",
    ) -> tuple[TelegramUser, bool]:
        existing = await self.get_by_telegram_id(telegram_id)
        now = utcnow()

        if existing is not None:
            existing.username = username
            existing.first_name = first_name
            existing.last_name = last_name
            existing.language_code = language_code
            existing.is_bot = is_bot
            existing.last_seen_at = now
            existing.updated_at = now
            if not existing.balance_currency:
                existing.balance_currency = balance_currency
            return existing, False

        user = TelegramUser(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
            language_code=language_code,
            is_bot=is_bot,
            balance=Decimal("0.00"),
            held_balance=Decimal("0.00"),
            balance_currency=balance_currency,
            created_at=now,
            updated_at=now,
            last_seen_at=now,
        )
        self.session.add(user)
        await self.session.flush()
        return user, True

    async def count_users(self) -> int:
        result = await self.session.execute(select(func.count()).select_from(TelegramUser))
        return result.scalar_one()

    async def count_active_since(self, since: datetime) -> int:
        query = select(func.count()).select_from(TelegramUser).where(TelegramUser.last_seen_at >= since)
        result = await self.session.execute(query)
        return result.scalar_one()

    async def list_all_telegram_ids(self) -> list[int]:
        query = select(TelegramUser.telegram_id).where(TelegramUser.is_bot == False)  # noqa: E712
        result = await self.session.execute(query)
        return list(result.scalars().all())