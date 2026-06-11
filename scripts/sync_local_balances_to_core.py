"""One-time migration: local telegram_users balance → Cerber Core USDT ledger.

Usage:
    python scripts/sync_local_balances_to_core.py          # dry-run (default)
    python scripts/sync_local_balances_to_core.py --apply   # execute migration

Requires BILLING_MODE=core_first and valid CERBER_CORE_* credentials in .env.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from decimal import Decimal

from sqlalchemy import select

from cerber_bot.config import load_settings
from cerber_bot.container import AppContainer
from cerber_bot.db.models import TelegramUser

logger = logging.getLogger(__name__)


async def sync_local_balances(*, apply: bool) -> int:
    settings = load_settings()
    if not settings.is_core_first_billing:
        raise SystemExit("Set BILLING_MODE=core_first before running this script.")

    container = await AppContainer.build(settings)
    migrated = 0

    try:
        assert container.ledger_service is not None
        async with container.session_factory() as session:
            result = await session.execute(
                select(TelegramUser).where(
                    (TelegramUser.balance > 0) | (TelegramUser.held_balance > 0)
                )
            )
            users = result.scalars().all()

        for user in users:
            available = Decimal(str(user.balance))
            held = Decimal(str(user.held_balance))
            total = available + held
            if total <= Decimal("0.00"):
                continue

            currency = user.balance_currency or settings.wallet_currency
            amount_usdt = await container.exchange_rate_service.convert(total, currency, "USDT")
            operation_id = f"sync:{user.telegram_id}"

            logger.info(
                "user=%s available=%s held=%s currency=%s -> %s USDT op=%s",
                user.telegram_id,
                available,
                held,
                currency,
                amount_usdt,
                operation_id,
            )

            if not apply:
                migrated += 1
                continue

            await container.ledger_service.ensure_user(user.telegram_id)
            await container.ledger_service.credit_usdt(
                user.telegram_id,
                amount_usdt=amount_usdt,
                tx_type="topup",
                description="Migration from local wallet balance",
                operation_id=operation_id,
            )

            async with container.session_factory() as session:
                db_user = await session.get(TelegramUser, user.id)
                if db_user is None:
                    continue
                db_user.balance = Decimal("0.00")
                db_user.held_balance = Decimal("0.00")
                await session.commit()

            migrated += 1
    finally:
        await container.close()

    return migrated


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate local wallet balances to Cerber Core.")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Execute migration (default is dry-run).",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    mode = "apply" if args.apply else "dry-run"
    logger.info("Starting local → Core balance sync (%s)", mode)
    count = asyncio.run(sync_local_balances(apply=args.apply))
    logger.info("Processed %s user(s). Mode: %s", count, mode)


if __name__ == "__main__":
    main()
