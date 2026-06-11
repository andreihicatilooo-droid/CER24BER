from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cerber_bot.integrations.cerber_core import CerberCoreBalance, CerberCoreTransaction


@dataclass(slots=True, frozen=True)
class LedgerSnapshot:
    """Available USDT balance as reported by Cerber Core."""

    available_usdt: Decimal
    balance_rub: Decimal
    rate_usdt_rub: Decimal

    @classmethod
    def from_core(cls, balance: CerberCoreBalance) -> LedgerSnapshot:
        return cls(
            available_usdt=balance.balance_usdt,
            balance_rub=balance.balance_rub,
            rate_usdt_rub=balance.rate_usdt_rub,
        )


@dataclass(slots=True, frozen=True)
class LedgerTransferResult:
    from_balance: LedgerSnapshot
    to_balance: LedgerSnapshot


LedgerHistory = tuple[CerberCoreTransaction, ...]
