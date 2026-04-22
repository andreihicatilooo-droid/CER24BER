from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from cerber_bot.db.repositories.tgaccounts import TgAccountRepository
from cerber_bot.db.session import create_engine, create_session_factory, init_database


@pytest.mark.asyncio
async def test_tgaccount_repository_crud_flow(tmp_path: Path) -> None:
    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'tgaccounts.db').as_posix()}"
    engine = create_engine(database_url)
    session_factory = create_session_factory(engine)
    await init_database(engine)

    async with session_factory() as session:
        repository = TgAccountRepository(session)
        purchase = await repository.create(
            telegram_id=123456789,
            getmytg_purchase_id=98765,
            country_code="RU",
            status="PENDING",
            amount=Decimal("5.50"),
            currency="USD",
            purchase_type="sms",
        )
        await session.commit()

    async with session_factory() as session:
        repository = TgAccountRepository(session)
        by_id = await repository.get_by_id(purchase.id)
        by_getmytg = await repository.get_by_getmytg_id(98765)
        user_items = await repository.list_by_telegram_id(123456789)

        assert by_id is not None
        assert by_getmytg is not None
        assert len(user_items) == 1
        assert by_getmytg.country_code == "RU"
        assert str(by_getmytg.amount) == "5.50"

        await repository.update_status(by_getmytg, status="SUCCESS", phone_number="+79990001122")
        await repository.update_verification(
            by_getmytg,
            verification_code="12345",
            verification_password="secret-pass",
        )
        await session.commit()

    async with session_factory() as session:
        repository = TgAccountRepository(session)
        updated = await repository.get_by_getmytg_id(98765)

        assert updated is not None
        assert updated.status == "SUCCESS"
        assert updated.phone_number == "+79990001122"
        assert updated.verification_code == "12345"
        assert updated.verification_password == "secret-pass"

    await engine.dispose()
