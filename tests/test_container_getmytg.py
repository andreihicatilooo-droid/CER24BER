from __future__ import annotations

from pathlib import Path

import pytest

from cerber_bot.config import Settings
from cerber_bot.container import AppContainer


def _build_settings(database_path: Path, *, api_key: str | None) -> Settings:
    return Settings(
        BOT_TOKEN="123456:FAKE_TOKEN_FOR_TESTS",
        DATABASE_URL=f"sqlite+aiosqlite:///{database_path.as_posix()}",
        GIFTAPI_TOKEN=None,
        GIFTAPI_SECRET=None,
        NICEPAY_MERCHANT_ID=None,
        NICEPAY_SECRET=None,
        WEB_ENABLED=False,
        GETMYTG_API_KEY=api_key,
    )


@pytest.mark.asyncio
async def test_container_builds_without_getmytg_api_key(tmp_path: Path) -> None:
    container = await AppContainer.build(_build_settings(tmp_path / "container-no-key.db", api_key=None))
    try:
        assert container.getmytg_client is None
        assert container.tgaccounts_service is not None
        assert container.tgaccounts_service.is_configured is False
    finally:
        await container.close()


@pytest.mark.asyncio
async def test_container_builds_with_getmytg_api_key(tmp_path: Path) -> None:
    container = await AppContainer.build(_build_settings(tmp_path / "container-with-key.db", api_key="secret-key"))
    try:
        assert container.getmytg_client is not None
        assert container.getmytg_client.is_configured is True
        assert container.tgaccounts_service is not None
        assert container.tgaccounts_service.is_configured is True
    finally:
        await container.close()
