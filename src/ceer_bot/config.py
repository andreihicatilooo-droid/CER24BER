"""Настройки CEER Bot из переменных окружения и .env файла.

Читает тот же .env что и CERBER, берёт DATABASE_URL оттуда же.
Единственный уникальный параметр — CEER_BOT_TOKEN.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8-sig",
        extra="ignore",
        case_sensitive=False,
    )

    ceer_bot_token: str = Field(alias="CEER_BOT_TOKEN")
    database_url: str = Field(
        default="sqlite+aiosqlite:///./data/cerber.db",
        alias="DATABASE_URL",
    )
    request_timeout_seconds: float = Field(default=15.0, alias="REQUEST_TIMEOUT_SECONDS")
    wallet_currency: str = Field(default="USD", alias="WALLET_CURRENCY")
    support_url: str = Field(default="https://t.me/cerber_support", alias="SUPPORT_URL")
    # Минимальная ставка в играх (в валюте кошелька)
    game_min_bet: str = Field(default="1.00", alias="GAME_MIN_BET")
    # Максимальная ставка в играх (0 = без ограничения)
    game_max_bet: str = Field(default="100.00", alias="GAME_MAX_BET")


def load_settings() -> Settings:
    """Загружает настройки из .env файла."""
    return Settings()
