"""Сервис репутации пользователей."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from cerber_bot.db.models import TelegramUser, utcnow
from cerber_bot.db.repositories.users import UserRepository


SUCCESS_REPUTATION_POINTS = 1
DISPUTE_REFUND_PENALTY = 2
DISPUTE_RELEASE_PENALTY = 1


@dataclass(slots=True, frozen=True)
class ReputationView:
    telegram_id: int
    score: int
    dispute_losses: int
    updated_at: object

    @classmethod
    def empty(cls, telegram_id: int) -> "ReputationView":
        return cls(telegram_id=telegram_id, score=0, dispute_losses=0, updated_at=utcnow())


class ReputationService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def get_user_reputation(self, telegram_id: int) -> ReputationView:
        async with self.session_factory() as session:
            repository = UserRepository(session)
            user = await repository.get_by_telegram_id(telegram_id)
            if user is None:
                return ReputationView.empty(telegram_id)
            return self._to_view(user)

    def apply_success(self, buyer: TelegramUser, seller: TelegramUser) -> None:
        self._increase_score(buyer, SUCCESS_REPUTATION_POINTS)
        self._increase_score(seller, SUCCESS_REPUTATION_POINTS)

    def apply_dispute_resolution(self, buyer: TelegramUser, seller: TelegramUser, *, resolution: str) -> None:
        normalized = resolution.strip().lower()
        if normalized == "refund":
            self._penalize(seller, DISPUTE_REFUND_PENALTY)
        elif normalized == "release":
            self._increase_score(seller, SUCCESS_REPUTATION_POINTS)
            self._penalize(buyer, DISPUTE_RELEASE_PENALTY)

    def _increase_score(self, user: TelegramUser, delta: int) -> None:
        user.reputation_score = int(user.reputation_score or 0) + delta
        user.reputation_updated_at = utcnow()

    def _penalize(self, user: TelegramUser, delta: int) -> None:
        user.reputation_score = int(user.reputation_score or 0) - delta
        user.reputation_dispute_losses = int(user.reputation_dispute_losses or 0) + 1
        user.reputation_updated_at = utcnow()

    def _to_view(self, user: TelegramUser) -> ReputationView:
        return ReputationView(
            telegram_id=user.telegram_id,
            score=int(user.reputation_score or 0),
            dispute_losses=int(user.reputation_dispute_losses or 0),
            updated_at=user.reputation_updated_at,
        )