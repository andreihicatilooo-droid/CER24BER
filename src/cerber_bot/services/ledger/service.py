"""LedgerService — единая точка входа для Core-first billing."""

from __future__ import annotations

from decimal import Decimal

from cerber_bot.integrations.cerber_core import CerberCoreClient, CerberCoreConfigurationError, CerberCoreError
from cerber_bot.services.ledger.types import LedgerHistory, LedgerSnapshot, LedgerTransferResult


class LedgerConfigurationError(RuntimeError):
    pass


class LedgerInsufficientFundsError(RuntimeError):
    pass


class LedgerService:
    """Обёртка над Cerber Core для всех денежных операций бота."""

    def __init__(self, client: CerberCoreClient) -> None:
        self._client = client

    @classmethod
    def from_client(cls, client: CerberCoreClient | None) -> LedgerService:
        if client is None or not client.is_configured:
            raise LedgerConfigurationError(
                "Core-first billing требует CERBER_CORE_API_KEY, CERBER_CORE_SECRET_KEY и CERBER_CORE_BASE_URL."
            )
        return cls(client)

    async def ensure_user(self, telegram_id: int) -> None:
        await self._client.register_user(telegram_id)

    async def get_balance(self, telegram_id: int) -> LedgerSnapshot:
        balance = await self._client.get_balance(telegram_id)
        return LedgerSnapshot.from_core(balance)

    async def list_transactions(
        self,
        telegram_id: int,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> LedgerHistory:
        return await self._client.list_transactions(telegram_id, limit=limit, offset=offset)

    async def adjust(
        self,
        telegram_id: int,
        *,
        delta_usdt: Decimal,
        tx_type: str,
        description: str,
        operation_id: str,
    ) -> LedgerSnapshot:
        balance = await self._client.adjust_balance(
            telegram_id,
            delta_usdt=delta_usdt,
            tx_type=tx_type,
            description=description,
            operation_id=operation_id,
        )
        return LedgerSnapshot.from_core(balance)

    async def debit_usdt(
        self,
        telegram_id: int,
        *,
        amount_usdt: Decimal,
        tx_type: str,
        description: str,
        operation_id: str,
    ) -> LedgerSnapshot:
        if amount_usdt <= Decimal("0"):
            raise ValueError("amount_usdt must be > 0")
        try:
            return await self.adjust(
                telegram_id,
                delta_usdt=-amount_usdt,
                tx_type=tx_type,
                description=description,
                operation_id=operation_id,
            )
        except CerberCoreError as error:
            raise _map_core_error(error) from error

    async def credit_usdt(
        self,
        telegram_id: int,
        *,
        amount_usdt: Decimal,
        tx_type: str,
        description: str,
        operation_id: str,
    ) -> LedgerSnapshot:
        if amount_usdt <= Decimal("0"):
            raise ValueError("amount_usdt must be > 0")
        try:
            return await self.adjust(
                telegram_id,
                delta_usdt=amount_usdt,
                tx_type=tx_type,
                description=description,
                operation_id=operation_id,
            )
        except CerberCoreError as error:
            raise _map_core_error(error) from error

    async def hold(
        self,
        telegram_id: int,
        *,
        amount_usdt: Decimal,
        description: str,
        operation_id: str,
    ) -> LedgerSnapshot:
        if amount_usdt <= Decimal("0"):
            raise ValueError("amount_usdt must be > 0")
        try:
            balance = await self._client.hold_funds(
                telegram_id,
                amount_usdt=amount_usdt,
                description=description,
                operation_id=operation_id,
            )
            return LedgerSnapshot.from_core(balance)
        except CerberCoreError as error:
            raise _map_core_error(error) from error

    async def unblock(
        self,
        telegram_id: int,
        *,
        amount_usdt: Decimal,
        description: str,
        operation_id: str,
    ) -> LedgerSnapshot:
        if amount_usdt <= Decimal("0"):
            raise ValueError("amount_usdt must be > 0")
        try:
            balance = await self._client.unblock_funds(
                telegram_id,
                amount_usdt=amount_usdt,
                description=description,
                operation_id=operation_id,
            )
            return LedgerSnapshot.from_core(balance)
        except CerberCoreError as error:
            raise _map_core_error(error) from error

    async def transfer(
        self,
        from_telegram_id: int,
        to_telegram_id: int,
        *,
        amount_usdt: Decimal,
        description: str,
        operation_id: str,
    ) -> LedgerTransferResult:
        if amount_usdt <= Decimal("0"):
            raise ValueError("amount_usdt must be > 0")
        try:
            from_balance, to_balance = await self._client.transfer_funds(
                from_telegram_id,
                to_telegram_id,
                amount_usdt=amount_usdt,
                description=description,
                operation_id=operation_id,
            )
            return LedgerTransferResult(
                from_balance=LedgerSnapshot.from_core(from_balance),
                to_balance=LedgerSnapshot.from_core(to_balance),
            )
        except CerberCoreError as error:
            raise _map_core_error(error) from error

    async def create_withdrawal(
        self,
        telegram_id: int,
        *,
        amount_usdt: Decimal,
        description: str,
        operation_id: str,
    ) -> LedgerSnapshot:
        if amount_usdt <= Decimal("0"):
            raise ValueError("amount_usdt must be > 0")
        try:
            balance = await self._client.create_withdrawal(
                telegram_id,
                amount_usdt=amount_usdt,
                description=description,
                operation_id=operation_id,
            )
            return LedgerSnapshot.from_core(balance)
        except CerberCoreError as error:
            raise _map_core_error(error) from error

    async def cancel_withdrawal(
        self,
        telegram_id: int,
        *,
        amount_usdt: Decimal,
        description: str,
        operation_id: str,
    ) -> LedgerSnapshot:
        if amount_usdt <= Decimal("0"):
            raise ValueError("amount_usdt must be > 0")
        try:
            balance = await self._client.cancel_withdrawal(
                telegram_id,
                amount_usdt=amount_usdt,
                description=description,
                operation_id=operation_id,
            )
            return LedgerSnapshot.from_core(balance)
        except CerberCoreError as error:
            raise _map_core_error(error) from error


def is_core_billing_error(error: Exception) -> bool:
    return isinstance(error, (CerberCoreError, CerberCoreConfigurationError, LedgerConfigurationError, LedgerInsufficientFundsError))


def _map_core_error(error: CerberCoreError) -> Exception:
    message = str(error).lower()
    if "insufficient" in message:
        return LedgerInsufficientFundsError(str(error))
    return error
