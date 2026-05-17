from decimal import Decimal
from pathlib import Path

import pytest
from aiogram.types import User

from cerber_bot.db.session import create_engine, create_session_factory, init_database
from cerber_bot.services.users import UserService


@pytest.mark.asyncio
async def test_user_service_creates_user_on_first_start(tmp_path: Path) -> None:
    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'test.db').as_posix()}"
    engine = create_engine(database_url)
    session_factory = create_session_factory(engine)
    await init_database(engine)

    service = UserService(session_factory)
    telegram_user = User(
        id=987654321,
        is_bot=False,
        first_name="Ivan",
        last_name="Petrov",
        username="cerber_user",
        language_code="ru",
    )

    profile, created = await service.register_or_update(telegram_user)
    persisted = await service.get_profile(telegram_user.id)

    assert created is True
    assert profile.telegram_id == telegram_user.id
    assert persisted is not None
    assert persisted.username == "cerber_user"
    assert str(persisted.balance) == "0.00"
    assert persisted.balance_currency == "USD"

    await engine.dispose()


@pytest.mark.asyncio
async def test_user_service_adjust_balance_updates_existing_user(tmp_path: Path) -> None:
    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'adjust-balance.db').as_posix()}"
    engine = create_engine(database_url)
    session_factory = create_session_factory(engine)
    await init_database(engine)

    service = UserService(session_factory)
    telegram_user = User(
        id=987654321,
        is_bot=False,
        first_name="Ivan",
        last_name="Petrov",
        username="cerber_user",
        language_code="ru",
    )

    await service.register_or_update(telegram_user)

    old_balance, updated = await service.adjust_balance(telegram_user.id, delta=Decimal("40.00"), admin_id=777)
    assert old_balance == Decimal("0.00")
    assert updated.balance == Decimal("40.00")

    old_balance, updated = await service.adjust_balance(telegram_user.id, delta=Decimal("-15.50"), admin_id=777)
    assert old_balance == Decimal("40.00")
    assert updated.balance == Decimal("24.50")

    persisted = await service.get_profile(telegram_user.id)
    assert persisted is not None
    assert persisted.balance == Decimal("24.50")

    await engine.dispose()


@pytest.mark.asyncio
async def test_user_service_adjust_balance_rejects_negative_result(tmp_path: Path) -> None:
    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'adjust-balance-negative.db').as_posix()}"
    engine = create_engine(database_url)
    session_factory = create_session_factory(engine)
    await init_database(engine)

    service = UserService(session_factory)
    telegram_user = User(
        id=987654321,
        is_bot=False,
        first_name="Ivan",
        last_name="Petrov",
        username="cerber_user",
        language_code="ru",
    )

    await service.register_or_update(telegram_user)

    with pytest.raises(ValueError, match="Баланс не может стать отрицательным"):
        await service.adjust_balance(telegram_user.id, delta=Decimal("-1.00"), admin_id=777)

    await engine.dispose()
