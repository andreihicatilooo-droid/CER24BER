from __future__ import annotations

from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

from ceer_bot.web.app import create_web_app


class _DummyUserService:
    wallet_currency = "USD"


@pytest.fixture
async def client() -> AsyncClient:
    container = SimpleNamespace(
        user_service=_DummyUserService(),
        settings=SimpleNamespace(ceer_bot_token="123456:TEST_TOKEN"),
        bot=None,
    )
    app = create_web_app(container)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def test_ttt_miniapp_serves_static_shell(client: AsyncClient) -> None:
    response = await client.get("/mini/ttt/?game_id=game-1")

    assert response.status_code == 200
    assert '/mini/ttt/app.js' in response.text
    assert '/mini/ttt/styles.css' in response.text


async def test_durak_miniapp_serves_current_static_shell(client: AsyncClient) -> None:
    response = await client.get("/mini/durak/?game_id=game-1")

    assert response.status_code == 200
    assert '/mini/durak/app.js' in response.text
    assert '/mini/durak/styles.css' in response.text
    assert '/game.js' not in response.text


async def test_durak_miniapp_script_uses_current_api_routes(client: AsyncClient) -> None:
    response = await client.get("/mini/durak/app.js")

    assert response.status_code == 200
    assert '/api/durak/' in response.text
    assert '/api/state/' not in response.text
    assert '/api/move/' not in response.text