"""Smoke-тесты для веб-приложения CERBER."""

import pytest
from httpx import ASGITransport, AsyncClient

from cerber_bot.container import AppContainer
from cerber_bot.config import Settings
from cerber_bot.web.app import create_web_app


@pytest.fixture
async def app():
    settings = Settings(
        BOT_TOKEN="123456:FAKE_TOKEN_FOR_TESTS",
        DATABASE_URL="sqlite+aiosqlite://",
        GIFTAPI_TOKEN=None,
        GIFTAPI_SECRET=None,
        NICEPAY_MERCHANT_ID=None,
        NICEPAY_SECRET=None,
        WEB_ENABLED=True,
    )
    container = await AppContainer.build(settings)
    web_app = create_web_app(container)
    yield web_app
    await container.close()


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def test_login_page_loads(client: AsyncClient):
    response = await client.get("/")
    assert response.status_code == 200
    assert "CERBER" in response.text


async def test_store_redirects_without_auth(client: AsyncClient):
    response = await client.get("/store", follow_redirects=False)
    assert response.status_code in (302, 401)


async def test_webapp_auth_rejects_invalid(client: AsyncClient):
    response = await client.post(
        "/auth/telegram-webapp",
        data={"init_data": "user=%7B%22id%22%3A1%7D&hash=invalid"},
    )
    assert response.status_code == 403


async def test_wallet_requires_auth(client: AsyncClient):
    response = await client.get("/wallet", follow_redirects=False)
    assert response.status_code in (302, 401)


async def test_deals_requires_auth(client: AsyncClient):
    response = await client.get("/deals", follow_redirects=False)
    assert response.status_code in (302, 401)


async def test_profile_requires_auth(client: AsyncClient):
    response = await client.get("/profile", follow_redirects=False)
    assert response.status_code in (302, 401)


async def test_logout_redirects(client: AsyncClient):
    response = await client.get("/logout", follow_redirects=False)
    assert response.status_code == 302
