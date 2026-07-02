"""Read-model кошелька для Core-first и legacy local режимов."""

from __future__ import annotations

from decimal import Decimal

from cerber_bot.db.repositories.deals import EscrowDealRepository, WithdrawalRequestRepository
from cerber_bot.db.repositories.orders import UserOrderRepository
from cerber_bot.db.repositories.users import UserRepository
from cerber_bot.db.repositories.wallet import WalletTransactionRepository
from cerber_bot.integrations.cerber_core import CerberCoreTransaction
from cerber_bot.services.exchange import ExchangeRateService
from cerber_bot.services.ledger import LedgerService
from cerber_bot.services.store import WalletSnapshot, WalletTransactionView

PENDING_DEAL_STATUSES = ("pending_acceptance", "active", "disputed")
PENDING_WITHDRAWAL_STATUS = "requested"


class WalletReadService:
    def __init__(
        self,
        *,
        session_factory,
        exchange_rate_service: ExchangeRateService,
        wallet_currency: str,
        ledger_service: LedgerService | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.exchange_rate_service = exchange_rate_service
        self.wallet_currency = wallet_currency
        self.ledger_service = ledger_service

    @property
    def is_core_first(self) -> bool:
        return self.ledger_service is not None

    async def get_snapshot(self, telegram_id: int, limit: int = 6) -> WalletSnapshot:
        if self.is_core_first:
            return await self._get_core_snapshot(telegram_id, limit=limit)
        return await self._get_local_snapshot(telegram_id, limit=limit)

    async def get_balance_amounts(self, telegram_id: int) -> tuple[Decimal, Decimal, str]:
        snapshot = await self.get_snapshot(telegram_id, limit=0)
        return snapshot.balance, snapshot.held_balance, snapshot.currency

    async def _get_core_snapshot(self, telegram_id: int, *, limit: int) -> WalletSnapshot:
        assert self.ledger_service is not None
        await self.ledger_service.ensure_user(telegram_id)
        async with self.session_factory() as session:
            user_repository = UserRepository(session)
            deal_repository = EscrowDealRepository(session)
            withdrawal_repository = WithdrawalRequestRepository(session)
            order_repository = UserOrderRepository(session)

            user = await user_repository.get_by_telegram_id(telegram_id)
            currency = self.wallet_currency if user is None else (user.balance_currency or self.wallet_currency)
            order_count = await order_repository.count_by_telegram_id(telegram_id)
            held_balance = await self._sum_escrow_held(deal_repository, withdrawal_repository, telegram_id)

        ledger_balance = await self.ledger_service.get_balance(telegram_id)
        available = await self.exchange_rate_service.convert(
            ledger_balance.available_usdt,
            "USDT",
            currency,
        )
        total_balance = available + held_balance
        transactions: tuple[WalletTransactionView, ...] = ()
        if limit > 0:
            core_transactions = await self.ledger_service.list_transactions(telegram_id, limit=limit)
            transactions = tuple(_core_transaction_view(item, currency) for item in core_transactions)

        balance_quote = await self.exchange_rate_service.quote_wallet(available, currency)
        held_quote = await self.exchange_rate_service.quote_wallet(held_balance, currency)
        total_quote = await self.exchange_rate_service.quote_wallet(total_balance, currency)
        return WalletSnapshot(
            balance=available,
            held_balance=held_balance,
            total_balance=total_balance,
            currency=currency,
            balance_quote=balance_quote,
            held_quote=held_quote,
            total_quote=total_quote,
            recent_transactions=transactions,
            order_count=order_count,
        )

    async def _get_local_snapshot(self, telegram_id: int, *, limit: int) -> WalletSnapshot:
        async with self.session_factory() as session:
            user_repository = UserRepository(session)
            wallet_repository = WalletTransactionRepository(session)
            order_repository = UserOrderRepository(session)

            user = await user_repository.get_by_telegram_id(telegram_id)
            transactions = await wallet_repository.list_recent(telegram_id, limit=limit) if limit > 0 else []
            order_count = await order_repository.count_by_telegram_id(telegram_id)

            balance = Decimal("0.00") if user is None else Decimal(str(user.balance))
            held_balance = Decimal("0.00") if user is None else Decimal(str(user.held_balance))
            total_balance = balance + held_balance
            currency = self.wallet_currency if user is None else (user.balance_currency or self.wallet_currency)
            balance_quote = await self.exchange_rate_service.quote_wallet(balance, currency)
            held_quote = await self.exchange_rate_service.quote_wallet(held_balance, currency)
            total_quote = await self.exchange_rate_service.quote_wallet(total_balance, currency)
            transaction_views = tuple(
                WalletTransactionView(
                    transaction_id=item.id,
                    transaction_type=item.transaction_type,
                    amount=Decimal(str(item.amount)),
                    currency=item.currency,
                    description=item.description,
                    reference=item.reference,
                    created_at=item.created_at,
                )
                for item in transactions
            )
            return WalletSnapshot(
                balance=balance,
                held_balance=held_balance,
                total_balance=total_balance,
                currency=currency,
                balance_quote=balance_quote,
                held_quote=held_quote,
                total_quote=total_quote,
                recent_transactions=transaction_views,
                order_count=order_count,
            )

    async def _sum_escrow_held(
        self,
        deal_repository: EscrowDealRepository,
        withdrawal_repository: WithdrawalRequestRepository,
        telegram_id: int,
    ) -> Decimal:
        deal_held = await deal_repository.sum_pending_buyer_amount(telegram_id)
        withdrawal_held = await withdrawal_repository.sum_pending_amount(telegram_id)
        return deal_held + withdrawal_held


def _core_transaction_view(item: CerberCoreTransaction, display_currency: str) -> WalletTransactionView:
    reference = item.id or None
    return WalletTransactionView(
        transaction_id=0,
        transaction_type=item.type,
        amount=item.amount_usdt,
        currency="USDT",
        description=item.description,
        reference=reference,
        created_at=item.created_at,
    )
