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