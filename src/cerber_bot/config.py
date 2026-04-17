"""Настройки приложения из переменных окружения и .env файла.

Все параметры загружаются через pydantic-settings.  Значения по умолчанию
позволяют запустить бота с минимальной конфигурацией (только BOT_TOKEN).
"""

from decimal import Decimal
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SQLITE_ASYNC_PREFIX = "sqlite+aiosqlite:///"
SQLITE_RELATIVE_PREFIX = f"{SQLITE_ASYNC_PREFIX}./"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8-sig",
        extra="ignore",
        case_sensitive=False,
    )

    bot_token: str = Field(alias="BOT_TOKEN")
    admin_bot_token: str = Field(default="", alias="ADMIN_BOT_TOKEN")
    database_url: str = Field(default="sqlite+aiosqlite:///./data/cerber.db", alias="DATABASE_URL")
    start_image_path: Path = Field(default_factory=lambda: PROJECT_ROOT / "START.jpg", alias="START_IMAGE_PATH")
    support_url: str = Field(default="https://t.me/cerber_support", alias="SUPPORT_URL")
    moderator_ids_raw: str = Field(default="", alias="MODERATOR_IDS")
    request_timeout_seconds: float = Field(default=15.0, alias="REQUEST_TIMEOUT_SECONDS")
    catalog_cache_ttl: int = Field(default=120, alias="CATALOG_CACHE_TTL")
    exchange_rate_cache_ttl: int = Field(default=600, alias="EXCHANGE_RATE_CACHE_TTL")
    exchange_rate_api_url: str = Field(default="https://open.er-api.com/v6/latest/USD", alias="EXCHANGE_RATE_API_URL")
    fallback_usdt_rub_rate: Decimal = Field(default=Decimal("90.00"), alias="FALLBACK_USDT_RUB_RATE")
    wallet_currency: str = Field(default="USD", alias="WALLET_CURRENCY")
    giftapi_base_url: str = Field(
        default="https://sandbox.giftapi.io/api/v1/partner",
        alias="GIFTAPI_BASE_URL",
    )
    giftapi_token: str | None = Field(default=None, alias="GIFTAPI_TOKEN")
    giftapi_secret: str | None = Field(default=None, alias="GIFTAPI_SECRET")
    giftapi_locale: str = Field(default="ru", alias="GIFTAPI_LOCALE")
    nicepay_base_url: str = Field(default="https://nicepay.io", alias="NICEPAY_BASE_URL")
    nicepay_proxy: str = Field(default="", alias="NICEPAY_PROXY")
    nicepay_merchant_id: str | None = Field(default=None, alias="NICEPAY_MERCHANT_ID")
    nicepay_secret: str | None = Field(default=None, alias="NICEPAY_SECRET")
    nicepay_method: str | None = Field(default=None, alias="NICEPAY_METHOD")
    nicepay_success_url: str | None = Field(default=None, alias="NICEPAY_SUCCESS_URL")
    nicepay_fail_url: str | None = Field(default=None, alias="NICEPAY_FAIL_URL")
    nicepay_webhook_host: str = Field(default="0.0.0.0", alias="NICEPAY_WEBHOOK_HOST")
    nicepay_webhook_port: int = Field(default=8080, alias="NICEPAY_WEBHOOK_PORT")
    nicepay_webhook_path: str = Field(default="/webhooks/nicepay", alias="NICEPAY_WEBHOOK_PATH")
    rukassa_base_url: str = Field(default="https://lk.rukassa.io/api/v1", alias="RUKASSA_BASE_URL")
    rukassa_shop_id: int | None = Field(default=None, alias="RUKASSA_SHOP_ID")
    rukassa_token: str | None = Field(default=None, alias="RUKASSA_TOKEN")
    rukassa_webhook_path: str = Field(default="/webhooks/rukassa", alias="RUKASSA_WEBHOOK_PATH")
    rukassa_success_url: str | None = Field(default=None, alias="RUKASSA_SUCCESS_URL")
    rukassa_fail_url: str | None = Field(default=None, alias="RUKASSA_FAIL_URL")

    @field_validator("rukassa_shop_id", mode="before")
    @classmethod
    def _empty_str_to_none_int(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("nicepay_webhook_port", mode="before")
    @classmethod
    def _empty_str_nicepay_port(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return 8080
        return value

    @field_validator("web_port", mode="before")
    @classmethod
    def _empty_str_web_port(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return 8088
        return value
    payments_currency: str = Field(default="USD", alias="PAYMENTS_CURRENCY")
    payments_title: str = Field(default="CERBER wallet top-up", alias="PAYMENTS_TITLE")
    payments_description: str = Field(
        default="Top up your CERBER wallet to pay for digital goods.",
        alias="PAYMENTS_DESCRIPTION",
    )
    payments_min_amount: Decimal = Field(default=Decimal("5.00"), alias="PAYMENTS_MIN_AMOUNT")
    payments_max_amount: Decimal = Field(default=Decimal("500.00"), alias="PAYMENTS_MAX_AMOUNT")
    withdrawal_min_amount_usdt: Decimal = Field(default=Decimal("10.00"), alias="WITHDRAWAL_MIN_AMOUNT_USDT")
    withdrawal_networks_raw: str = Field(default="TRC20,BEP20,ERC20", alias="WITHDRAWAL_NETWORKS")
    web_host: str = Field(default="0.0.0.0", alias="WEB_HOST")
    web_port: int = Field(default=8088, alias="WEB_PORT")
    web_enabled: bool = Field(default=True, alias="WEB_ENABLED")
    web_base_url: str = Field(default="", alias="WEB_BASE_URL")
    bot_username: str = Field(default="", alias="BOT_USERNAME")
    telegram_api_url: str = Field(default="https://api.telegram.org", alias="TELEGRAM_API_URL")
    telegram_proxy: str = Field(default="", alias="TELEGRAM_PROXY")

    @property
    def moderator_ids(self) -> tuple[int, ...]:
        values: list[int] = []
        for chunk in self.moderator_ids_raw.split(","):
            normalized = chunk.strip()
            if not normalized:
                continue
            if normalized.lstrip("-").isdigit():
                values.append(int(normalized))
        return tuple(values)

    @property
    def withdrawal_networks(self) -> tuple[str, ...]:
        values = [chunk.strip().upper() for chunk in self.withdrawal_networks_raw.split(",") if chunk.strip()]
        return tuple(values) or ("TRC20",)


def load_settings() -> Settings:
    return Settings()


def resolve_database_url(database_url: str) -> str:
    if database_url.startswith(SQLITE_RELATIVE_PREFIX):
        relative_path = database_url.removeprefix(SQLITE_RELATIVE_PREFIX)
        return f"{SQLITE_ASYNC_PREFIX}{(PROJECT_ROOT / relative_path).as_posix()}"
    return database_url


def sqlite_storage_path(database_url: str) -> Path | None:
    resolved = resolve_database_url(database_url)
    if not resolved.startswith(SQLITE_ASYNC_PREFIX):
        return None
    return Path(resolved.removeprefix(SQLITE_ASYNC_PREFIX))