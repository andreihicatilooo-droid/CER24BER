"""Сервис гарант-сделок.

Отвечает за создание/принятие/отмену сделок, блокировку средств, чат сделки,
диспуты с подключением модераторов и заявки на вывод в USDT.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from aiogram.types import User as TelegramUserObject
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from cerber_bot.db.models import DealOffer, EscrowDeal, EscrowDealMessage, TelegramUser, WithdrawalRequest, utcnow
from cerber_bot.db.repositories.deals import EscrowDealMessageRepository, EscrowDealRepository, WithdrawalRequestRepository
from cerber_bot.db.repositories.offers import DealOfferRepository
from cerber_bot.db.repositories.users import UserRepository
from cerber_bot.db.repositories.wallet import WalletTransactionRepository
from cerber_bot.services.exchange import ExchangeRateService, WalletQuote
from cerber_bot.services.store import PageInfo, build_page_info, format_money, normalize_money_amount
from cerber_bot.texts import DEAL_SERVICE_TEXT


PENDING_DEAL_STATUSES = {"pending_acceptance", "active", "delivered", "disputed"}

# Статусы, в которых доступен чат и действия сторон
LIVE_DEAL_STATUSES = {"active", "delivered", "disputed"}

# Сколько часов у покупателя после выдачи товара на закрытие/диспут, потом автозакрытие в пользу продавца
DELIVERY_AUTO_RELEASE_HOURS = 24


class DealServiceError(RuntimeError):
    pass


class DealPermissionError(DealServiceError):
    pass


class DealStateError(DealServiceError):
    pass


class WithdrawalError(DealServiceError):
    pass


@dataclass(slots=True, frozen=True)
class DealUserView:
    telegram_id: int
    display_name: str


@dataclass(slots=True, frozen=True)
class DealMessageView:
    sender_role: str
    sender_display: str
    content_type: str
    body: str
    created_at: object


@dataclass(slots=True, frozen=True)
class DealCard:
    deal_id: int
    status: str
    amount: Decimal
    currency: str
    viewer_role: str
    counterpart_display: str
    updated_at: object


@dataclass(slots=True, frozen=True)
class DealView:
    deal_id: int
    status: str
    amount: Decimal
    currency: str
    amount_quote: WalletQuote
    terms: str
    buyer: DealUserView
    seller: DealUserView
    counterpart: DealUserView
    viewer_role: str | None
    resolution: str | None
    resolution_note: str | None
    moderator_requested_at: object | None
    created_at: object
    accepted_at: object | None
    completed_at: object | None
    disputed_at: object | None
    closed_at: object | None
    delivered_at: object | None
    messages: tuple[DealMessageView, ...]
    can_accept: bool
    can_decline: bool
    can_cancel: bool
    can_send_message: bool
    can_confirm_success: bool
    can_open_dispute: bool
    can_call_moderator: bool
    can_mark_delivered: bool


@dataclass(slots=True, frozen=True)
class DealBalanceView:
    available: Decimal
    held: Decimal
    total: Decimal
    currency: str
    available_quote: WalletQuote
    held_quote: WalletQuote
    total_quote: WalletQuote


@dataclass(slots=True, frozen=True)
class DealStatistics:
    total_deals: int
    open_deals: int
    completed_deals: int
    disputed_deals: int
    total_volume: Decimal
    currency: str
    total_volume_quote: WalletQuote
    pending_withdrawals: int


@dataclass(slots=True, frozen=True)
class WithdrawalRequestView:
    request_id: int
    telegram_id: int
    status: str
    amount: Decimal
    amount_usdt: Decimal
    currency: str
    amount_quote: WalletQuote
    network: str
    address: str
    created_at: object
    resolved_at: object | None
    resolution_note: str | None
    can_cancel: bool


@dataclass(slots=True, frozen=True)
class DealDashboard:
    balance: DealBalanceView
    statistics: DealStatistics
    open_withdrawal: WithdrawalRequestView | None


@dataclass(slots=True, frozen=True)
class DealInvitationResult:
    deal: DealView
    counterparty: DealUserView


@dataclass(slots=True, frozen=True)
class DealActionResult:
    deal: DealView
    counterparty_id: int | None


@dataclass(slots=True, frozen=True)
class DealMessageRelayResult:
    deal: DealView
    recipient_id: int
    sender_display: str
    preview: str


@dataclass(slots=True, frozen=True)
class DealModerationResult:
    deal_id: int
    buyer_telegram_id: int
    seller_telegram_id: int
    status: str
    resolution: str | None


@dataclass(slots=True, frozen=True)
class WithdrawalActionResult:
    request: WithdrawalRequestView
    owner_telegram_id: int


@dataclass(slots=True, frozen=True)
class DealOfferView:
    offer_uuid: str
    author_telegram_id: int
    author_display: str
    author_role: str
    amount: Decimal
    currency: str
    terms: str
    is_template: bool


@dataclass(slots=True, frozen=True)
class OfferAcceptResult:
    deal: DealView
    buyer_telegram_id: int
    seller_telegram_id: int
    author_telegram_id: int
    acceptor_telegram_id: int


class DealService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        exchange_rate_service: ExchangeRateService,
        wallet_currency: str,
        moderator_ids: tuple[int, ...],
        withdrawal_min_amount_usdt: Decimal,
        withdrawal_networks: tuple[str, ...],
    ) -> None:
        self.session_factory = session_factory
        self.exchange_rate_service = exchange_rate_service
        self.wallet_currency = wallet_currency
        self.moderator_ids = moderator_ids
        self.withdrawal_min_amount_usdt = normalize_money_amount(withdrawal_min_amount_usdt)
        self.withdrawal_networks = tuple(network.upper() for network in withdrawal_networks)

    @property
    def has_moderators(self) -> bool:
        return bool(self.moderator_ids)

    async def get_dashboard(self, telegram_id: int) -> DealDashboard:
        async with self.session_factory() as session:
            user_repository = UserRepository(session)
            deal_repository = EscrowDealRepository(session)
            withdrawal_repository = WithdrawalRequestRepository(session)

            user = await user_repository.get_by_telegram_id(telegram_id)
            balance_view = await self._build_balance_view(user)
            total_volume = await deal_repository.sum_completed_for_user(telegram_id)
            statistics = DealStatistics(
                total_deals=await deal_repository.count_for_user(telegram_id),
                open_deals=await deal_repository.count_open_for_user(telegram_id),
                completed_deals=await deal_repository.count_completed_for_user(telegram_id),
                disputed_deals=await deal_repository.count_disputed_for_user(telegram_id),
                total_volume=total_volume,
                currency=balance_view.currency,
                total_volume_quote=await self.exchange_rate_service.quote_wallet(total_volume, balance_view.currency),
                pending_withdrawals=await withdrawal_repository.count_open_for_user(telegram_id),
            )
            open_withdrawal = await withdrawal_repository.get_open_for_user(telegram_id)
            return DealDashboard(
                balance=balance_view,
                statistics=statistics,
                open_withdrawal=await self._to_withdrawal_view(open_withdrawal) if open_withdrawal is not None else None,
            )

    async def get_deals_page(self, telegram_id: int, *, page: int, per_page: int = 6) -> tuple[tuple[DealCard, ...], PageInfo]:
        async with self.session_factory() as session:
            deal_repository = EscrowDealRepository(session)
            user_repository = UserRepository(session)

            total_items = await deal_repository.count_for_user(telegram_id)
            page_info = build_page_info(total_items=total_items, page=page, per_page=per_page)
            offset = (page_info.page - 1) * page_info.per_page
            deals = await deal_repository.list_for_user(telegram_id, offset=offset, limit=page_info.per_page)
            user_ids = {deal.buyer_telegram_id for deal in deals} | {deal.seller_telegram_id for deal in deals}
            users = await user_repository.list_by_telegram_ids(user_ids)
            cards = tuple(self._to_deal_card(deal, telegram_id, users) for deal in deals)
            return cards, page_info

    async def get_deal_view(self, telegram_id: int, deal_id: int) -> DealView | None:
        async with self.session_factory() as session:
            deal_repository = EscrowDealRepository(session)
            deal = await deal_repository.get_for_user(deal_id, telegram_id)
            if deal is None:
                return None
            return await self._build_deal_view(session, deal, telegram_id)

    async def create_deal_request(
        self,
        telegram_user: TelegramUserObject,
        *,
        seller_identifier: str,
        amount: Decimal,
        terms: str,
    ) -> DealInvitationResult:
        normalized_amount = normalize_money_amount(amount)
        if normalized_amount <= Decimal("0.00"):
            raise DealServiceError(DEAL_SERVICE_TEXT.DEAL_AMOUNT_POSITIVE)

        normalized_terms = terms.strip()
        if len(normalized_terms) < 10:
            raise DealServiceError(DEAL_SERVICE_TEXT.DEAL_TERMS_TOO_SHORT)

        async with self.session_factory() as session:
            user_repository = UserRepository(session)
            deal_repository = EscrowDealRepository(session)
            message_repository = EscrowDealMessageRepository(session)
            wallet_repository = WalletTransactionRepository(session)

            buyer, _ = await user_repository.get_or_create(
                telegram_id=telegram_user.id,
                username=telegram_user.username,
                first_name=telegram_user.first_name,
                last_name=telegram_user.last_name,
                language_code=telegram_user.language_code,
                is_bot=telegram_user.is_bot,
                balance_currency=self.wallet_currency,
            )
            # Блокируем строку покупателя перед изменением баланса
            buyer = await user_repository.get_by_telegram_id(buyer.telegram_id, with_lock=True)
            seller = await user_repository.find_by_identifier(seller_identifier)
            if seller is None:
                raise DealServiceError(DEAL_SERVICE_TEXT.PARTNER_NOT_FOUND)
            if seller.telegram_id == buyer.telegram_id:
                raise DealServiceError(DEAL_SERVICE_TEXT.DEAL_WITH_SELF)

            currency = buyer.balance_currency or self.wallet_currency
            self._ensure_wallet_currency(buyer, currency)
            if Decimal(str(buyer.balance)) < normalized_amount:
                raise DealServiceError(
                    DEAL_SERVICE_TEXT.hold_insufficient_funds(format_money(Decimal(str(buyer.balance)), currency))
                )

            buyer.balance -= normalized_amount
            buyer.held_balance += normalized_amount
            deal = await deal_repository.create(
                buyer_telegram_id=buyer.telegram_id,
                seller_telegram_id=seller.telegram_id,
                status="pending_acceptance",
                amount=normalized_amount,
                currency=currency,
                terms=normalized_terms,
            )
            await wallet_repository.add(
                telegram_id=buyer.telegram_id,
                transaction_type="deal_hold",
                amount=-normalized_amount,
                currency=currency,
                description=DEAL_SERVICE_TEXT.deal_hold_description(deal.id),
                reference=f"deal:{deal.id}",
            )
            await message_repository.add(
                deal_id=deal.id,
                sender_telegram_id=0,
                sender_role="system",
                content_type="system",
                body=DEAL_SERVICE_TEXT.DEAL_CREATED_MESSAGE,
            )
            await session.commit()

            return DealInvitationResult(
                deal=await self._build_deal_view(session, deal, buyer.telegram_id),
                counterparty=self._to_user_view(seller),
            )

    async def accept_deal(self, telegram_id: int, deal_id: int) -> DealActionResult:
        async with self.session_factory() as session:
            user_repository = UserRepository(session)
            deal_repository = EscrowDealRepository(session)
            message_repository = EscrowDealMessageRepository(session)

            deal = await deal_repository.get_for_user(deal_id, telegram_id)
            if deal is None:
                raise DealServiceError(DEAL_SERVICE_TEXT.DEAL_NOT_FOUND)
            pending_actor = deal.pending_actor or "seller"
            expected_acceptor_id = (
                deal.buyer_telegram_id if pending_actor == "buyer" else deal.seller_telegram_id
            )
            if expected_acceptor_id != telegram_id:
                raise DealPermissionError(DEAL_SERVICE_TEXT.ACCEPT_ONLY_SECOND_PARTY)
            if deal.status != "pending_acceptance":
                raise DealStateError(DEAL_SERVICE_TEXT.DEAL_CANNOT_ACCEPT)

            acceptor = await user_repository.get_by_telegram_id(telegram_id, with_lock=True)
            if acceptor is None:
                raise DealServiceError(DEAL_SERVICE_TEXT.SELLER_NOT_FOUND)
            self._ensure_wallet_currency(acceptor, deal.currency)

            amount = Decimal(str(deal.amount))
            if pending_actor == "buyer" and not deal.funds_held:
                # Витринная сделка: покупатель подтверждает условия — блокируем его средства
                if Decimal(str(acceptor.balance)) < amount:
                    raise DealServiceError(
                        DEAL_SERVICE_TEXT.hold_insufficient_funds(
                            format_money(Decimal(str(acceptor.balance)), deal.currency)
                        )
                    )
                acceptor.balance -= amount
                acceptor.held_balance += amount
                deal.funds_held = True
                await WalletTransactionRepository(session).add(
                    telegram_id=acceptor.telegram_id,
                    transaction_type="deal_hold",
                    amount=-amount,
                    currency=deal.currency,
                    description=DEAL_SERVICE_TEXT.deal_hold_description(deal.id),
                    reference=f"deal:{deal.id}",
                )

            now = utcnow()
            deal.status = "active"
            deal.accepted_at = now
            deal.updated_at = now
            await message_repository.add(
                deal_id=deal.id,
                sender_telegram_id=0,
                sender_role="system",
                content_type="system",
                body=DEAL_SERVICE_TEXT.DEAL_ACCEPTED_MESSAGE,
            )
            await session.commit()
            counterparty_id = (
                deal.seller_telegram_id if telegram_id == deal.buyer_telegram_id else deal.buyer_telegram_id
            )
            return DealActionResult(
                deal=await self._build_deal_view(session, deal, telegram_id),
                counterparty_id=counterparty_id,
            )

    async def decline_deal(self, telegram_id: int, deal_id: int) -> DealActionResult:
        async with self.session_factory() as session:
            user_repository = UserRepository(session)
            deal_repository = EscrowDealRepository(session)
            message_repository = EscrowDealMessageRepository(session)
            wallet_repository = WalletTransactionRepository(session)

            deal = await deal_repository.get_for_user(deal_id, telegram_id)
            if deal is None:
                raise DealServiceError(DEAL_SERVICE_TEXT.DEAL_NOT_FOUND)
            if deal.status != "pending_acceptance":
                raise DealStateError(DEAL_SERVICE_TEXT.DEAL_WRONG_STATUS)
            if telegram_id not in {deal.buyer_telegram_id, deal.seller_telegram_id}:
                raise DealPermissionError(DEAL_SERVICE_TEXT.DEAL_PERMISSION_DENIED)

            buyer = await user_repository.get_by_telegram_id(deal.buyer_telegram_id, with_lock=True)
            if buyer is None:
                raise DealServiceError(DEAL_SERVICE_TEXT.BUYER_NOT_FOUND)

            amount = Decimal(str(deal.amount))
            if deal.funds_held:
                if Decimal(str(buyer.held_balance)) < amount:
                    raise DealStateError(DEAL_SERVICE_TEXT.DEAL_HELD_UNAVAILABLE)
                buyer.held_balance -= amount
                buyer.balance += amount

            now = utcnow()
            canceled_by_buyer = telegram_id == deal.buyer_telegram_id
            deal.status = "canceled" if canceled_by_buyer else "declined"
            deal.resolution = "canceled_by_buyer" if canceled_by_buyer else "declined_by_seller"
            deal.closed_at = now
            deal.updated_at = now
            if deal.funds_held:
                deal.funds_held = False
                await wallet_repository.add(
                    telegram_id=buyer.telegram_id,
                    transaction_type="deal_release",
                    amount=amount,
                    currency=deal.currency,
                    description=DEAL_SERVICE_TEXT.deal_hold_return_description(deal.id),
                    reference=f"deal:{deal.id}",
                )
            await message_repository.add(
                deal_id=deal.id,
                sender_telegram_id=0,
                sender_role="system",
                content_type="system",
                body=DEAL_SERVICE_TEXT.DEAL_CANCELED_MESSAGE,
            )
            await session.commit()
            counterparty_id = deal.seller_telegram_id if canceled_by_buyer else deal.buyer_telegram_id
            return DealActionResult(
                deal=await self._build_deal_view(session, deal, telegram_id),
                counterparty_id=counterparty_id,
            )

    async def request_moderator(self, telegram_id: int, deal_id: int) -> DealActionResult:
        async with self.session_factory() as session:
            deal_repository = EscrowDealRepository(session)
            message_repository = EscrowDealMessageRepository(session)

            deal = await deal_repository.get_for_user(deal_id, telegram_id)
            if deal is None:
                raise DealServiceError(DEAL_SERVICE_TEXT.DEAL_NOT_FOUND)
            if deal.status not in LIVE_DEAL_STATUSES:
                raise DealStateError(DEAL_SERVICE_TEXT.MODERATOR_ONLY_ACTIVE_OR_DISPUTE)

            deal.moderator_requested_at = utcnow()
            deal.updated_at = deal.moderator_requested_at
            await message_repository.add(
                deal_id=deal.id,
                sender_telegram_id=0,
                sender_role="system",
                content_type="system",
                body=DEAL_SERVICE_TEXT.MODERATOR_REQUESTED_MESSAGE,
            )
            await session.commit()
            return DealActionResult(
                deal=await self._build_deal_view(session, deal, telegram_id),
                counterparty_id=self._counterparty_id(deal, telegram_id),
            )

    async def open_dispute(self, telegram_id: int, deal_id: int) -> DealActionResult:
        async with self.session_factory() as session:
            deal_repository = EscrowDealRepository(session)
            message_repository = EscrowDealMessageRepository(session)

            deal = await deal_repository.get_for_user(deal_id, telegram_id)
            if deal is None:
                raise DealServiceError(DEAL_SERVICE_TEXT.DEAL_NOT_FOUND)
            if deal.status not in {"active", "delivered"}:
                raise DealStateError(DEAL_SERVICE_TEXT.DISPUTE_ONLY_ACTIVE)

            now = utcnow()
            deal.status = "disputed"
            deal.disputed_at = now
            deal.moderator_requested_at = now
            deal.updated_at = now
            await message_repository.add(
                deal_id=deal.id,
                sender_telegram_id=0,
                sender_role="system",
                content_type="system",
                body=DEAL_SERVICE_TEXT.DISPUTE_OPENED_MESSAGE,
            )
            await session.commit()
            return DealActionResult(
                deal=await self._build_deal_view(session, deal, telegram_id),
                counterparty_id=self._counterparty_id(deal, telegram_id),
            )

    async def confirm_success(self, telegram_id: int, deal_id: int) -> DealActionResult:
        async with self.session_factory() as session:
            user_repository = UserRepository(session)
            deal_repository = EscrowDealRepository(session)
            message_repository = EscrowDealMessageRepository(session)
            wallet_repository = WalletTransactionRepository(session)

            deal = await deal_repository.get_for_user(deal_id, telegram_id)
            if deal is None:
                raise DealServiceError(DEAL_SERVICE_TEXT.DEAL_NOT_FOUND)
            if deal.buyer_telegram_id != telegram_id:
                raise DealPermissionError(DEAL_SERVICE_TEXT.CONFIRM_ONLY_BUYER)
            if deal.status not in {"active", "delivered", "disputed"}:
                raise DealStateError(DEAL_SERVICE_TEXT.DEAL_CANNOT_CONFIRM)

            buyer = await user_repository.get_by_telegram_id(deal.buyer_telegram_id, with_lock=True)
            seller = await user_repository.get_by_telegram_id(deal.seller_telegram_id, with_lock=True)
            if buyer is None or seller is None:
                raise DealServiceError(DEAL_SERVICE_TEXT.DEAL_PARTICIPANTS_NOT_FOUND)

            amount = Decimal(str(deal.amount))
            if Decimal(str(buyer.held_balance)) < amount:
                raise DealStateError(DEAL_SERVICE_TEXT.DEAL_HELD_UNAVAILABLE)

            self._ensure_wallet_currency(seller, deal.currency)
            buyer.held_balance -= amount
            seller.balance += amount
            seller.balance_currency = deal.currency

            now = utcnow()
            deal.status = "completed"
            deal.completed_at = now
            deal.closed_at = now
            deal.updated_at = now
            if deal.resolution is None and deal.disputed_at is not None:
                deal.resolution = "released_after_dispute"

            await wallet_repository.add(
                telegram_id=seller.telegram_id,
                transaction_type="deal_release",
                amount=amount,
                currency=deal.currency,
                description=DEAL_SERVICE_TEXT.deal_credit_description(deal.id),
                reference=f"deal:{deal.id}",
            )
            await message_repository.add(
                deal_id=deal.id,
                sender_telegram_id=0,
                sender_role="system",
                content_type="system",
                body=DEAL_SERVICE_TEXT.DEAL_CONFIRMED_MESSAGE,
            )
            await session.commit()
            return DealActionResult(
                deal=await self._build_deal_view(session, deal, telegram_id),
                counterparty_id=deal.seller_telegram_id,
            )

    async def mark_delivered(self, telegram_id: int, deal_id: int) -> DealActionResult:
        """Продавец отмечает, что товар выдан. Запускает 24-часовое окно покупателя."""
        async with self.session_factory() as session:
            deal_repository = EscrowDealRepository(session)
            message_repository = EscrowDealMessageRepository(session)

            deal = await deal_repository.get_for_user(deal_id, telegram_id)
            if deal is None:
                raise DealServiceError(DEAL_SERVICE_TEXT.DEAL_NOT_FOUND)
            if deal.seller_telegram_id != telegram_id:
                raise DealPermissionError(DEAL_SERVICE_TEXT.DELIVER_ONLY_SELLER)
            if deal.status != "active":
                raise DealStateError(DEAL_SERVICE_TEXT.DELIVER_ONLY_ACTIVE)

            now = utcnow()
            deal.status = "delivered"
            deal.delivered_at = now
            deal.updated_at = now
            await message_repository.add(
                deal_id=deal.id,
                sender_telegram_id=0,
                sender_role="system",
                content_type="system",
                body=DEAL_SERVICE_TEXT.DEAL_DELIVERED_MESSAGE,
            )
            await session.commit()
            return DealActionResult(
                deal=await self._build_deal_view(session, deal, telegram_id),
                counterparty_id=deal.buyer_telegram_id,
            )

    async def auto_release_delivered(self) -> list[DealModerationResult]:
        """Автозакрытие сделок: товар выдан более 24 часов назад — средства уходят продавцу."""
        from datetime import timedelta

        threshold = utcnow() - timedelta(hours=DELIVERY_AUTO_RELEASE_HOURS)
        results: list[DealModerationResult] = []
        async with self.session_factory() as session:
            user_repository = UserRepository(session)
            deal_repository = EscrowDealRepository(session)
            message_repository = EscrowDealMessageRepository(session)
            wallet_repository = WalletTransactionRepository(session)

            deals = await deal_repository.list_delivered_before(threshold)
            for deal in deals:
                buyer = await user_repository.get_by_telegram_id(deal.buyer_telegram_id, with_lock=True)
                seller = await user_repository.get_by_telegram_id(deal.seller_telegram_id, with_lock=True)
                if buyer is None or seller is None:
                    continue

                amount = Decimal(str(deal.amount))
                if Decimal(str(buyer.held_balance)) < amount:
                    continue

                buyer.held_balance -= amount
                seller.balance += amount
                seller.balance_currency = deal.currency

                now = utcnow()
                deal.status = "completed"
                deal.completed_at = now
                deal.closed_at = now
                deal.updated_at = now
                deal.resolution = "auto_release_after_delivery"
                await wallet_repository.add(
                    telegram_id=seller.telegram_id,
                    transaction_type="deal_release",
                    amount=amount,
                    currency=deal.currency,
                    description=DEAL_SERVICE_TEXT.deal_credit_description(deal.id),
                    reference=f"deal:{deal.id}",
                )
                await message_repository.add(
                    deal_id=deal.id,
                    sender_telegram_id=0,
                    sender_role="system",
                    content_type="system",
                    body=DEAL_SERVICE_TEXT.DEAL_AUTO_RELEASED_MESSAGE,
                )
                results.append(
                    DealModerationResult(
                        deal_id=deal.id,
                        buyer_telegram_id=deal.buyer_telegram_id,
                        seller_telegram_id=deal.seller_telegram_id,
                        status=deal.status,
                        resolution=deal.resolution,
                    )
                )
            await session.commit()
        return results

    async def resolve_dispute(self, moderator_id: int, deal_id: int, resolution: str) -> DealModerationResult:
        if moderator_id not in self.moderator_ids:
            raise DealPermissionError(DEAL_SERVICE_TEXT.MODERATOR_ONLY)

        normalized_resolution = resolution.strip().lower()
        if normalized_resolution not in {"refund", "release"}:
            raise DealServiceError(DEAL_SERVICE_TEXT.UNKNOWN_MODERATION_ACTION)

        async with self.session_factory() as session:
            user_repository = UserRepository(session)
            deal_repository = EscrowDealRepository(session)
            message_repository = EscrowDealMessageRepository(session)
            wallet_repository = WalletTransactionRepository(session)

            deal = await deal_repository.get_by_id(deal_id)
            if deal is None:
                raise DealServiceError(DEAL_SERVICE_TEXT.DEAL_NOT_FOUND)
            if deal.status != "disputed":
                raise DealStateError(DEAL_SERVICE_TEXT.MODERATION_ONLY_DISPUTED)

            buyer = await user_repository.get_by_telegram_id(deal.buyer_telegram_id, with_lock=True)
            seller = await user_repository.get_by_telegram_id(deal.seller_telegram_id, with_lock=True)
            if buyer is None or seller is None:
                raise DealServiceError(DEAL_SERVICE_TEXT.DEAL_PARTICIPANTS_NOT_FOUND)

            amount = Decimal(str(deal.amount))
            if Decimal(str(buyer.held_balance)) < amount:
                raise DealStateError(DEAL_SERVICE_TEXT.DISPUTE_HELD_UNAVAILABLE)

            now = utcnow()
            buyer.held_balance -= amount
            if normalized_resolution == "refund":
                buyer.balance += amount
                deal.status = "refunded"
                deal.resolution = "refund_buyer"
                await wallet_repository.add(
                    telegram_id=buyer.telegram_id,
                    transaction_type="deal_refund",
                    amount=amount,
                    currency=deal.currency,
                    description=DEAL_SERVICE_TEXT.dispute_refund_description(deal.id),
                    reference=f"deal:{deal.id}",
                )
                message_text = DEAL_SERVICE_TEXT.MODERATOR_REFUND_MESSAGE
            else:
                self._ensure_wallet_currency(seller, deal.currency)
                seller.balance += amount
                seller.balance_currency = deal.currency
                deal.status = "completed"
                deal.completed_at = now
                deal.resolution = "release_seller"
                await wallet_repository.add(
                    telegram_id=seller.telegram_id,
                    transaction_type="deal_release",
                    amount=amount,
                    currency=deal.currency,
                    description=DEAL_SERVICE_TEXT.moderator_release_description(deal.id),
                    reference=f"deal:{deal.id}",
                )
                message_text = DEAL_SERVICE_TEXT.MODERATOR_RELEASE_MESSAGE

            deal.resolution_note = f"moderated_by:{moderator_id}"
            deal.closed_at = now
            deal.updated_at = now
            await message_repository.add(
                deal_id=deal.id,
                sender_telegram_id=0,
                sender_role="system",
                content_type="system",
                body=message_text,
            )
            await session.commit()
            return DealModerationResult(
                deal_id=deal.id,
                buyer_telegram_id=deal.buyer_telegram_id,
                seller_telegram_id=deal.seller_telegram_id,
                status=deal.status,
                resolution=deal.resolution,
            )

    async def record_chat_message(
        self,
        telegram_id: int,
        *,
        deal_id: int,
        content_type: str,
        body: str,
    ) -> DealMessageRelayResult:
        normalized_body = body.strip()
        if not normalized_body:
            raise DealServiceError(DEAL_SERVICE_TEXT.DEAL_CHAT_EMPTY)

        async with self.session_factory() as session:
            user_repository = UserRepository(session)
            deal_repository = EscrowDealRepository(session)
            message_repository = EscrowDealMessageRepository(session)

            deal = await deal_repository.get_for_user(deal_id, telegram_id)
            if deal is None:
                raise DealServiceError(DEAL_SERVICE_TEXT.DEAL_NOT_FOUND)
            if deal.status not in LIVE_DEAL_STATUSES:
                raise DealStateError(DEAL_SERVICE_TEXT.CHAT_ONLY_ACTIVE_OR_DISPUTE)

            sender = await user_repository.get_by_telegram_id(telegram_id)
            if sender is None:
                raise DealServiceError(DEAL_SERVICE_TEXT.SENDER_NOT_FOUND)

            role = self._viewer_role(deal, telegram_id)
            await message_repository.add(
                deal_id=deal.id,
                sender_telegram_id=telegram_id,
                sender_role=role,
                content_type=content_type,
                body=normalized_body,
            )
            deal.updated_at = utcnow()
            await session.commit()
            return DealMessageRelayResult(
                deal=await self._build_deal_view(session, deal, telegram_id),
                recipient_id=self._counterparty_id(deal, telegram_id),
                sender_display=self._display_name(sender),
                preview=normalized_body,
            )

    async def get_open_withdrawal(self, telegram_id: int) -> WithdrawalRequestView | None:
        async with self.session_factory() as session:
            repository = WithdrawalRequestRepository(session)
            request = await repository.get_open_for_user(telegram_id)
            if request is None:
                return None
            return await self._to_withdrawal_view(request)

    async def create_withdrawal_request(
        self,
        telegram_user: TelegramUserObject,
        *,
        amount_usdt: Decimal,
        network: str,
        address: str,
    ) -> WithdrawalActionResult:
        normalized_amount_usdt = normalize_money_amount(amount_usdt)
        if normalized_amount_usdt < self.withdrawal_min_amount_usdt:
            raise WithdrawalError(
                DEAL_SERVICE_TEXT.minimum_withdrawal_amount(format_money(self.withdrawal_min_amount_usdt, 'USDT'))
            )

        normalized_network = network.strip().upper()
        if normalized_network not in self.withdrawal_networks:
            raise WithdrawalError(
                DEAL_SERVICE_TEXT.unsupported_network(', '.join(self.withdrawal_networks))
            )
        normalized_address = address.strip()
        if len(normalized_address) < 8:
            raise WithdrawalError(DEAL_SERVICE_TEXT.INVALID_USDT_ADDRESS)

        async with self.session_factory() as session:
            user_repository = UserRepository(session)
            wallet_repository = WalletTransactionRepository(session)
            withdrawal_repository = WithdrawalRequestRepository(session)

            user, _ = await user_repository.get_or_create(
                telegram_id=telegram_user.id,
                username=telegram_user.username,
                first_name=telegram_user.first_name,
                last_name=telegram_user.last_name,
                language_code=telegram_user.language_code,
                is_bot=telegram_user.is_bot,
                balance_currency=self.wallet_currency,
            )
            # Блокируем строку пользователя перед изменением баланса
            user = await user_repository.get_by_telegram_id(user.telegram_id, with_lock=True)
            open_request = await withdrawal_repository.get_open_for_user(user.telegram_id)
            if open_request is not None:
                raise WithdrawalError(DEAL_SERVICE_TEXT.OPEN_WITHDRAWAL_EXISTS)

            wallet_currency = user.balance_currency or self.wallet_currency
            self._ensure_wallet_currency(user, wallet_currency)
            amount_in_wallet_currency = await self.exchange_rate_service.convert(
                normalized_amount_usdt,
                "USDT",
                wallet_currency,
            )
            if Decimal(str(user.balance)) < amount_in_wallet_currency:
                raise WithdrawalError(
                    DEAL_SERVICE_TEXT.withdrawal_insufficient_funds(format_money(Decimal(str(user.balance)), wallet_currency))
                )

            user.balance -= amount_in_wallet_currency
            user.held_balance += amount_in_wallet_currency
            request = await withdrawal_repository.create(
                telegram_id=user.telegram_id,
                status="requested",
                amount=amount_in_wallet_currency,
                amount_usdt=normalized_amount_usdt,
                currency=wallet_currency,
                network=normalized_network,
                address=normalized_address,
            )
            await wallet_repository.add(
                telegram_id=user.telegram_id,
                transaction_type="withdrawal_hold",
                amount=-amount_in_wallet_currency,
                currency=wallet_currency,
                description=DEAL_SERVICE_TEXT.withdrawal_request_description(
                    format_money(normalized_amount_usdt, 'USDT'),
                    normalized_network,
                ),
                reference=f"withdrawal:{request.id}",
            )
            await session.commit()
            return WithdrawalActionResult(
                request=await self._to_withdrawal_view(request),
                owner_telegram_id=user.telegram_id,
            )

    async def cancel_withdrawal_request(self, telegram_id: int, request_id: int) -> WithdrawalActionResult:
        async with self.session_factory() as session:
            user_repository = UserRepository(session)
            wallet_repository = WalletTransactionRepository(session)
            withdrawal_repository = WithdrawalRequestRepository(session)

            request = await withdrawal_repository.get_for_user(request_id, telegram_id)
            if request is None:
                raise WithdrawalError(DEAL_SERVICE_TEXT.WITHDRAWAL_NOT_FOUND)
            if request.status != "requested":
                raise WithdrawalError(DEAL_SERVICE_TEXT.WITHDRAWAL_CANNOT_CANCEL)

            user = await user_repository.get_by_telegram_id(telegram_id, with_lock=True)
            if user is None:
                raise WithdrawalError(DEAL_SERVICE_TEXT.USER_NOT_FOUND)

            amount = Decimal(str(request.amount))
            if Decimal(str(user.held_balance)) < amount:
                raise WithdrawalError(DEAL_SERVICE_TEXT.WITHDRAWAL_FUNDS_UNAVAILABLE)

            user.held_balance -= amount
            user.balance += amount
            request.status = "canceled"
            request.resolution_note = DEAL_SERVICE_TEXT.WITHDRAWAL_CANCELED_BY_USER
            request.resolved_at = utcnow()
            request.updated_at = request.resolved_at
            await wallet_repository.add(
                telegram_id=telegram_id,
                transaction_type="withdrawal_release",
                amount=amount,
                currency=request.currency,
                description=DEAL_SERVICE_TEXT.withdrawal_cancel_refund_description(request.id),
                reference=f"withdrawal:{request.id}",
            )
            await session.commit()
            return WithdrawalActionResult(
                request=await self._to_withdrawal_view(request),
                owner_telegram_id=telegram_id,
            )

    async def moderate_withdrawal_request(
        self,
        moderator_id: int,
        request_id: int,
        action: str,
    ) -> WithdrawalActionResult:
        if moderator_id not in self.moderator_ids:
            raise DealPermissionError(DEAL_SERVICE_TEXT.MODERATOR_ONLY)

        normalized_action = action.strip().lower()
        if normalized_action not in {"approve", "reject"}:
            raise WithdrawalError(DEAL_SERVICE_TEXT.UNKNOWN_WITHDRAWAL_ACTION)

        async with self.session_factory() as session:
            user_repository = UserRepository(session)
            wallet_repository = WalletTransactionRepository(session)
            withdrawal_repository = WithdrawalRequestRepository(session)

            request = await withdrawal_repository.get_by_id(request_id)
            if request is None:
                raise WithdrawalError(DEAL_SERVICE_TEXT.WITHDRAWAL_NOT_FOUND)
            if request.status != "requested":
                raise WithdrawalError(DEAL_SERVICE_TEXT.WITHDRAWAL_ALREADY_PROCESSED)

            user = await user_repository.get_by_telegram_id(request.telegram_id)
            if user is None:
                raise WithdrawalError(DEAL_SERVICE_TEXT.WITHDRAWAL_OWNER_NOT_FOUND)

            amount = Decimal(str(request.amount))
            if Decimal(str(user.held_balance)) < amount:
                raise WithdrawalError(DEAL_SERVICE_TEXT.WITHDRAWAL_HELD_UNAVAILABLE)

            user.held_balance -= amount
            request.resolved_at = utcnow()
            request.updated_at = request.resolved_at
            if normalized_action == "approve":
                request.status = "approved"
                request.resolution_note = DEAL_SERVICE_TEXT.withdrawal_approved_by_moderator(moderator_id)
                await wallet_repository.add(
                    telegram_id=user.telegram_id,
                    transaction_type="withdrawal_approved",
                    amount=-amount,
                    currency=request.currency,
                    description=DEAL_SERVICE_TEXT.withdrawal_approved_description(request.id),
                    reference=f"withdrawal:{request.id}",
                )
            else:
                user.balance += amount
                request.status = "rejected"
                request.resolution_note = DEAL_SERVICE_TEXT.withdrawal_rejected_by_moderator(moderator_id)
                await wallet_repository.add(
                    telegram_id=user.telegram_id,
                    transaction_type="withdrawal_release",
                    amount=amount,
                    currency=request.currency,
                    description=DEAL_SERVICE_TEXT.withdrawal_reject_refund_description(request.id),
                    reference=f"withdrawal:{request.id}",
                )

            await session.commit()
            return WithdrawalActionResult(
                request=await self._to_withdrawal_view(request),
                owner_telegram_id=user.telegram_id,
            )

    async def _build_balance_view(self, user: TelegramUser | None) -> DealBalanceView:
        available = Decimal("0.00") if user is None else Decimal(str(user.balance))
        held = Decimal("0.00") if user is None else Decimal(str(user.held_balance))
        currency = self.wallet_currency if user is None else (user.balance_currency or self.wallet_currency)
        total = available + held
        return DealBalanceView(
            available=available,
            held=held,
            total=total,
            currency=currency,
            available_quote=await self.exchange_rate_service.quote_wallet(available, currency),
            held_quote=await self.exchange_rate_service.quote_wallet(held, currency),
            total_quote=await self.exchange_rate_service.quote_wallet(total, currency),
        )

    async def _build_deal_view(self, session: AsyncSession, deal: EscrowDeal, viewer_id: int | None) -> DealView:
        user_repository = UserRepository(session)
        message_repository = EscrowDealMessageRepository(session)
        users = await user_repository.list_by_telegram_ids({deal.buyer_telegram_id, deal.seller_telegram_id})
        buyer = self._to_user_view(users.get(deal.buyer_telegram_id), telegram_id=deal.buyer_telegram_id)
        seller = self._to_user_view(users.get(deal.seller_telegram_id), telegram_id=deal.seller_telegram_id)
        viewer_role = self._viewer_role(deal, viewer_id) if viewer_id is not None else None
        counterpart = seller if viewer_role == "buyer" else buyer
        messages = await message_repository.list_recent(deal.id, limit=8)
        amount = Decimal(str(deal.amount))
        return DealView(
            deal_id=deal.id,
            status=deal.status,
            amount=amount,
            currency=deal.currency,
            amount_quote=await self.exchange_rate_service.quote_wallet(amount, deal.currency),
            terms=deal.terms,
            buyer=buyer,
            seller=seller,
            counterpart=counterpart,
            viewer_role=viewer_role,
            resolution=deal.resolution,
            resolution_note=deal.resolution_note,
            moderator_requested_at=deal.moderator_requested_at,
            created_at=deal.created_at,
            accepted_at=deal.accepted_at,
            completed_at=deal.completed_at,
            disputed_at=deal.disputed_at,
            closed_at=deal.closed_at,
            delivered_at=deal.delivered_at,
            messages=tuple(self._to_message_view(item, users) for item in messages),
            can_accept=(
                deal.status == "pending_acceptance"
                and viewer_role is not None
                and viewer_role == (deal.pending_actor or "seller")
            ),
            can_decline=viewer_role in {"buyer", "seller"} and deal.status == "pending_acceptance",
            can_cancel=viewer_role == "buyer" and deal.status == "pending_acceptance",
            can_send_message=viewer_role in {"buyer", "seller"} and deal.status in LIVE_DEAL_STATUSES,
            can_confirm_success=viewer_role == "buyer" and deal.status in {"active", "delivered", "disputed"},
            can_open_dispute=viewer_role in {"buyer", "seller"} and deal.status in {"active", "delivered"},
            can_call_moderator=viewer_role in {"buyer", "seller"} and deal.status in LIVE_DEAL_STATUSES,
            can_mark_delivered=viewer_role == "seller" and deal.status == "active",
        )

    async def _to_withdrawal_view(self, request: WithdrawalRequest) -> WithdrawalRequestView:
        amount = Decimal(str(request.amount))
        return WithdrawalRequestView(
            request_id=request.id,
            telegram_id=request.telegram_id,
            status=request.status,
            amount=amount,
            amount_usdt=Decimal(str(request.amount_usdt)),
            currency=request.currency,
            amount_quote=await self.exchange_rate_service.quote_wallet(amount, request.currency),
            network=request.network,
            address=request.address,
            created_at=request.created_at,
            resolved_at=request.resolved_at,
            resolution_note=request.resolution_note,
            can_cancel=request.status == "requested",
        )

    def _to_deal_card(
        self,
        deal: EscrowDeal,
        viewer_id: int,
        users: dict[int, TelegramUser],
    ) -> DealCard:
        viewer_role = self._viewer_role(deal, viewer_id)
        counterpart_id = deal.seller_telegram_id if viewer_role == "buyer" else deal.buyer_telegram_id
        counterpart = users.get(counterpart_id)
        return DealCard(
            deal_id=deal.id,
            status=deal.status,
            amount=Decimal(str(deal.amount)),
            currency=deal.currency,
            viewer_role=viewer_role,
            counterpart_display=self._display_name(counterpart, telegram_id=counterpart_id),
            updated_at=deal.updated_at,
        )

    def _to_message_view(self, message: EscrowDealMessage, users: dict[int, TelegramUser]) -> DealMessageView:
        if message.sender_role == "system":
            sender_display = DEAL_SERVICE_TEXT.SYSTEM_SENDER
        else:
            sender_display = self._display_name(users.get(message.sender_telegram_id), telegram_id=message.sender_telegram_id)
        return DealMessageView(
            sender_role=message.sender_role,
            sender_display=sender_display,
            content_type=message.content_type,
            body=message.body,
            created_at=message.created_at,
        )

    def _to_user_view(self, user: TelegramUser | None, telegram_id: int | None = None) -> DealUserView:
        resolved_telegram_id = telegram_id if telegram_id is not None else (user.telegram_id if user is not None else 0)
        return DealUserView(
            telegram_id=resolved_telegram_id,
            display_name=self._display_name(user, telegram_id=resolved_telegram_id),
        )

    def _display_name(self, user: TelegramUser | None, telegram_id: int | None = None) -> str:
        if user is not None and user.display_name:
            return user.display_name
        if user is not None and user.username:
            return f"@{user.username}"
        if user is not None:
            full_name = " ".join(part for part in (user.first_name, user.last_name) if part)
            if full_name:
                return full_name
            telegram_id = user.telegram_id
        if telegram_id is None:
            return DEAL_SERVICE_TEXT.UNKNOWN_USER
        return f"ID {telegram_id}"

    def _ensure_wallet_currency(self, user: TelegramUser, currency: str) -> None:
        normalized_currency = currency.upper()
        current_currency = (user.balance_currency or normalized_currency).upper()
        if current_currency != normalized_currency:
            if Decimal(str(user.balance)) != Decimal("0.00") or Decimal(str(user.held_balance)) != Decimal("0.00"):
                raise DealServiceError(
                    DEAL_SERVICE_TEXT.wallet_currency_mismatch(current_currency, normalized_currency)
                )
        user.balance_currency = normalized_currency

    def _viewer_role(self, deal: EscrowDeal, viewer_id: int | None) -> str:
        if viewer_id == deal.buyer_telegram_id:
            return "buyer"
        if viewer_id == deal.seller_telegram_id:
            return "seller"
        raise DealPermissionError(DEAL_SERVICE_TEXT.USER_NOT_IN_DEAL)

    def _counterparty_id(self, deal: EscrowDeal, viewer_id: int) -> int:
        role = self._viewer_role(deal, viewer_id)
        return deal.seller_telegram_id if role == "buyer" else deal.buyer_telegram_id

    async def get_public_stats(self, telegram_id: int) -> tuple[int, int, int, Decimal]:
        """Публичная статистика пользователя: (всего сделок, завершено, диспутов, оборот)."""
        async with self.session_factory() as session:
            deal_repository = EscrowDealRepository(session)
            return (
                await deal_repository.count_for_user(telegram_id),
                await deal_repository.count_completed_for_user(telegram_id),
                await deal_repository.count_disputed_for_user(telegram_id),
                await deal_repository.sum_completed_for_user(telegram_id),
            )

    # ── Инлайн-предложения сделок (посты-шаблоны) ──────────────

    async def save_offer(
        self,
        telegram_user: TelegramUserObject,
        *,
        offer_uuid: str,
        author_role: str,
        amount: Decimal,
        terms: str,
        is_template: bool,
    ) -> DealOfferView:
        normalized_amount = normalize_money_amount(amount)
        if normalized_amount <= Decimal("0.00"):
            raise DealServiceError(DEAL_SERVICE_TEXT.DEAL_AMOUNT_POSITIVE)
        normalized_terms = terms.strip()
        if len(normalized_terms) < 10:
            raise DealServiceError(DEAL_SERVICE_TEXT.DEAL_TERMS_TOO_SHORT)
        normalized_role = author_role if author_role in {"buyer", "seller"} else "buyer"

        async with self.session_factory() as session:
            user_repository = UserRepository(session)
            offer_repository = DealOfferRepository(session)
            author, _ = await user_repository.get_or_create(
                telegram_id=telegram_user.id,
                username=telegram_user.username,
                first_name=telegram_user.first_name,
                last_name=telegram_user.last_name,
                language_code=telegram_user.language_code,
                is_bot=telegram_user.is_bot,
                balance_currency=self.wallet_currency,
            )
            offer = await offer_repository.upsert(
                uuid=offer_uuid,
                author_telegram_id=author.telegram_id,
                author_role=normalized_role,
                amount=normalized_amount,
                currency=author.balance_currency or self.wallet_currency,
                terms=normalized_terms,
                is_template=is_template,
            )
            await session.commit()
            return self._to_offer_view(offer, author)

    async def get_offer_view(self, offer_uuid: str) -> DealOfferView | None:
        async with self.session_factory() as session:
            offer_repository = DealOfferRepository(session)
            user_repository = UserRepository(session)
            offer = await offer_repository.get_by_uuid(offer_uuid)
            if offer is None or offer.status != "open":
                return None
            author = await user_repository.get_by_telegram_id(offer.author_telegram_id)
            return self._to_offer_view(offer, author)

    async def list_template_offers(self, telegram_id: int, *, limit: int = 10) -> tuple[DealOfferView, ...]:
        async with self.session_factory() as session:
            offer_repository = DealOfferRepository(session)
            user_repository = UserRepository(session)
            offers = await offer_repository.list_templates_for_author(telegram_id, limit=limit)
            author = await user_repository.get_by_telegram_id(telegram_id)
            return tuple(self._to_offer_view(offer, author) for offer in offers)

    async def accept_deal_offer(self, offer_uuid: str, acceptor: TelegramUserObject) -> OfferAcceptResult:
        """Создаёт приглашение в сделку по инлайн-посту (витрине).

        Сделка создаётся в статусе pending_acceptance: нажавший кнопку должен
        подтвердить условия в боте. Если автор поста — покупатель, его средства
        блокируются сразу; если покупатель — нажавший, блокировка происходит
        при его подтверждении условий (accept_deal).
        """
        async with self.session_factory() as session:
            user_repository = UserRepository(session)
            offer_repository = DealOfferRepository(session)
            deal_repository = EscrowDealRepository(session)
            message_repository = EscrowDealMessageRepository(session)
            wallet_repository = WalletTransactionRepository(session)

            offer = await offer_repository.get_by_uuid(offer_uuid)
            if offer is None or offer.status != "open":
                raise DealServiceError(DEAL_SERVICE_TEXT.OFFER_NOT_FOUND)
            if offer.author_telegram_id == acceptor.id:
                raise DealServiceError(DEAL_SERVICE_TEXT.DEAL_WITH_SELF)

            author = await user_repository.get_by_telegram_id(offer.author_telegram_id)
            if author is None:
                raise DealServiceError(DEAL_SERVICE_TEXT.PARTNER_NOT_FOUND)
            acceptor_user, _ = await user_repository.get_or_create(
                telegram_id=acceptor.id,
                username=acceptor.username,
                first_name=acceptor.first_name,
                last_name=acceptor.last_name,
                language_code=acceptor.language_code,
                is_bot=acceptor.is_bot,
                balance_currency=self.wallet_currency,
            )

            amount = normalize_money_amount(Decimal(str(offer.amount)))
            now = utcnow()
            if offer.author_role == "seller":
                # Витрина продавца: нажавший — покупатель, подтверждает условия и блокирует средства позже
                buyer_id, seller_id = acceptor_user.telegram_id, author.telegram_id
                pending_actor = "buyer"
                funds_held = False
                currency = acceptor_user.balance_currency or self.wallet_currency
            else:
                # Автор — покупатель: блокируем его средства сразу, нажавший (продавец) подтверждает
                buyer = await user_repository.get_by_telegram_id(author.telegram_id, with_lock=True)
                currency = buyer.balance_currency or self.wallet_currency
                self._ensure_wallet_currency(buyer, currency)
                if Decimal(str(buyer.balance)) < amount:
                    raise DealServiceError(
                        DEAL_SERVICE_TEXT.hold_insufficient_funds(format_money(Decimal(str(buyer.balance)), currency))
                    )
                buyer.balance -= amount
                buyer.held_balance += amount
                buyer_id, seller_id = author.telegram_id, acceptor_user.telegram_id
                pending_actor = "seller"
                funds_held = True

            deal = await deal_repository.create(
                buyer_telegram_id=buyer_id,
                seller_telegram_id=seller_id,
                status="pending_acceptance",
                amount=amount,
                currency=currency,
                terms=offer.terms,
                pending_actor=pending_actor,
                funds_held=funds_held,
            )
            if funds_held:
                await wallet_repository.add(
                    telegram_id=buyer_id,
                    transaction_type="deal_hold",
                    amount=-amount,
                    currency=currency,
                    description=DEAL_SERVICE_TEXT.deal_hold_description(deal.id),
                    reference=f"deal:{deal.id}",
                )
            await message_repository.add(
                deal_id=deal.id,
                sender_telegram_id=0,
                sender_role="system",
                content_type="system",
                body=DEAL_SERVICE_TEXT.OFFER_ACCEPTED_MESSAGE,
            )
            if not offer.is_template:
                offer.status = "accepted"
                offer.updated_at = now
            await session.commit()

            return OfferAcceptResult(
                deal=await self._build_deal_view(session, deal, acceptor.id),
                buyer_telegram_id=buyer_id,
                seller_telegram_id=seller_id,
                author_telegram_id=offer.author_telegram_id,
                acceptor_telegram_id=acceptor.id,
            )

    def _to_offer_view(self, offer: DealOffer, author: TelegramUser | None) -> DealOfferView:
        return DealOfferView(
            offer_uuid=offer.uuid,
            author_telegram_id=offer.author_telegram_id,
            author_display=self._display_name(author, telegram_id=offer.author_telegram_id),
            author_role=offer.author_role,
            amount=Decimal(str(offer.amount)),
            currency=offer.currency,
            terms=offer.terms,
            is_template=offer.is_template,
        )

    # ── Методы для админ-бота ──────────────────────────────────

    async def get_admin_summary(self) -> tuple[int, int]:
        """Возвращает (кол-во диспутов, кол-во ожидающих выводов)."""
        async with self.session_factory() as session:
            deal_repo = EscrowDealRepository(session)
            withdrawal_repo = WithdrawalRequestRepository(session)
            disputes = await deal_repo.count_disputed()
            withdrawals = await withdrawal_repo.count_pending()
            return disputes, withdrawals

    async def list_disputed_deals(self) -> list[DealView]:
        async with self.session_factory() as session:
            deal_repo = EscrowDealRepository(session)
            deals = await deal_repo.list_disputed()
            views: list[DealView] = []
            for deal in deals:
                views.append(await self._build_deal_view(session, deal, viewer_id=None))
            return views

    async def get_deal_view_admin(self, deal_id: int) -> DealView | None:
        """Просмотр сделки для модератора (без привязки к участнику)."""
        async with self.session_factory() as session:
            deal_repo = EscrowDealRepository(session)
            deal = await deal_repo.get_by_id(deal_id)
            if deal is None:
                return None
            return await self._build_deal_view(session, deal, viewer_id=None)

    async def list_pending_withdrawals(self) -> list[WithdrawalRequestView]:
        async with self.session_factory() as session:
            withdrawal_repo = WithdrawalRequestRepository(session)
            requests = await withdrawal_repo.list_pending()
            views: list[WithdrawalRequestView] = []
            for request in requests:
                views.append(await self._to_withdrawal_view(request))
            return views

    async def send_moderator_message(
        self,
        moderator_id: int,
        *,
        deal_id: int,
        body: str,
    ) -> tuple[DealView, int, int]:
        """Отправить сообщение от модератора в чат сделки.

        Возвращает (DealView, buyer_telegram_id, seller_telegram_id).
        """
        if moderator_id not in self.moderator_ids:
            raise DealPermissionError(DEAL_SERVICE_TEXT.MODERATOR_ONLY)

        normalized_body = body.strip()
        if not normalized_body:
            raise DealServiceError(DEAL_SERVICE_TEXT.DEAL_CHAT_EMPTY)

        async with self.session_factory() as session:
            deal_repo = EscrowDealRepository(session)
            message_repo = EscrowDealMessageRepository(session)

            deal = await deal_repo.get_by_id(deal_id)
            if deal is None:
                raise DealServiceError(DEAL_SERVICE_TEXT.DEAL_NOT_FOUND)
            if deal.status not in LIVE_DEAL_STATUSES:
                raise DealStateError(DEAL_SERVICE_TEXT.CHAT_ONLY_ACTIVE_OR_DISPUTE)

            await message_repo.add(
                deal_id=deal.id,
                sender_telegram_id=moderator_id,
                sender_role="moderator",
                content_type="text",
                body=normalized_body,
            )
            deal.updated_at = utcnow()
            await session.commit()

            view = await self._build_deal_view(session, deal, viewer_id=None)
            return view, deal.buyer_telegram_id, deal.seller_telegram_id