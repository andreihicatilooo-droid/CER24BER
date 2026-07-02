"""Сервис приглашений: реферальные ссылки и учёт приглашённых пользователей."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from cerber_bot.db.repositories.users import UserRepository


REFERRAL_PREFIX = "ref_"


@dataclass(slots=True, frozen=True)
class ReferralStats:
    invited_count: int
    referrer_telegram_id: int | None


class ReferralService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession], *, bot_username: str = "") -> None:
        self.session_factory = session_factory
        self.bot_username = bot_username.lstrip("@")

    def parse_payload(self, payload: str | None) -> int | None:
        """Извлекает telegram_id пригласившего из deep-link payload вида ref_123."""
        if not payload:
            return None
        normalized = payload.strip()
        if not normalized.startswith(REFERRAL_PREFIX):
            return None
        raw_id = normalized.removeprefix(REFERRAL_PREFIX)
        if not raw_id.isdigit():
            return None
        return int(raw_id)

    def build_link(self, telegram_id: int) -> str | None:
        if not self.bot_username:
            return None
        return f"https://t.me/{self.bot_username}?start={REFERRAL_PREFIX}{telegram_id}"

    async def apply_referral(self, new_user_telegram_id: int, referrer_telegram_id: int) -> bool:
        """Привязывает приглашённого к рефереру. Только один раз и не к самому себе."""
        if new_user_telegram_id == referrer_telegram_id:
            return False
        async with self.session_factory() as session:
            repository = UserRepository(session)
            user = await repository.get_by_telegram_id(new_user_telegram_id)
            if user is None or user.referrer_telegram_id is not None:
                return False
            referrer = await repository.get_by_telegram_id(referrer_telegram_id)
            if referrer is None:
                return False
            user.referrer_telegram_id = referrer_telegram_id
            await session.commit()
            return True

    async def get_stats(self, telegram_id: int) -> ReferralStats:
        async with self.session_factory() as session:
            repository = UserRepository(session)
            invited = await repository.count_referrals(telegram_id)
            user = await repository.get_by_telegram_id(telegram_id)
            return ReferralStats(
                invited_count=invited,
                referrer_telegram_id=user.referrer_telegram_id if user is not None else None,
            )
