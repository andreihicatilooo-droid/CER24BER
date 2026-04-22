from pathlib import Path

import pytest

from cerber_bot.db.models import AdminNotificationEvent
from cerber_bot.db.session import create_engine, create_session_factory, init_database
from cerber_bot.services.admin_events import AdminEventService


class FakeBot:
    def __init__(self) -> None:
        self.messages: list[tuple[int, str]] = []

    async def send_message(self, telegram_id: int, text: str, parse_mode=None, reply_markup=None) -> None:
        self.messages.append((telegram_id, text))


@pytest.mark.asyncio
async def test_admin_event_service_enqueues_and_delivers_deal_alert(tmp_path: Path) -> None:
    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'admin-events.db').as_posix()}"
    engine = create_engine(database_url)
    session_factory = create_session_factory(engine)
    await init_database(engine)

    service = AdminEventService(session_factory, moderator_ids=(7001, 7002))
    await service.enqueue_deal_alert(text="<b>deal</b>", deal_id=55, disputed=True)

    bot = FakeBot()
    delivered = await service.deliver_pending(bot)

    assert delivered == 1
    assert bot.messages == [(7001, "<b>deal</b>"), (7002, "<b>deal</b>")]

    async with session_factory() as session:
        events = (await session.execute(AdminNotificationEvent.__table__.select())).fetchall()

    assert len(events) == 1
    assert events[0].status == "delivered"

    await engine.dispose()


@pytest.mark.asyncio
async def test_admin_event_service_enqueues_and_delivers_withdrawal_alert(tmp_path: Path) -> None:
    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'admin-events-withdrawal.db').as_posix()}"
    engine = create_engine(database_url)
    session_factory = create_session_factory(engine)
    await init_database(engine)

    service = AdminEventService(session_factory, moderator_ids=(9001,))
    await service.enqueue_withdrawal_alert(text="<b>withdraw</b>", request_id=77)

    bot = FakeBot()
    delivered = await service.deliver_pending(bot)

    assert delivered == 1
    assert bot.messages == [(9001, "<b>withdraw</b>")]

    async with session_factory() as session:
        events = (await session.execute(AdminNotificationEvent.__table__.select())).fetchall()

    assert len(events) == 1
    assert events[0].status == "delivered"

    await engine.dispose()