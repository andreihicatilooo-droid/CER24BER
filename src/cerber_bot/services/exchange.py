"""Сервис курсов валют.

Загружает курсы из внешнего API, кэширует их и конвертирует суммы
между USD, USDT, RUB и другими валютами.  В случае недоступности API
использует fallback-курс USDT/RUB.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from time import monotonic

import httpx


logger = logging.getLogger(__name__)


class ExchangeRateError(RuntimeError):
    pass


@dataclass(slots=True, frozen=True)
class WalletQuote:
    base_amount: Decimal
    base_currency: str
    usdt_amount: Decimal
    rub_amount: Decimal
    usdt_rub_rate: Decimal
    source: str


class ExchangeRateService:
    def __init__(
        self,
        *,
        http_client: httpx.AsyncClient,
        api_url: str,
        cache_ttl_seconds: int = 600,
        fallback_usdt_rub_rate: Decimal = Decimal("90.00"),
    ) -> None:
        self.http_client = http_client
        self.api_url = api_url
        self.cache_ttl_seconds = cache_ttl_seconds
        self.fallback_usdt_rub_rate = normalize_amount(fallback_usdt_rub_rate)
        self._cached_rates: dict[str, Decimal] | None = None
        self._cache_source = "fallback"
        self._cache_until = 0.0

    async def quote_wallet(self, amount: Decimal, currency: str) -> WalletQuote:
        normalized_amount = normalize_amount(amount)
        usdt_amount = await self.convert(normalized_amount, currency, "USDT")
        rub_amount = await self.convert(normalized_amount, currency, "RUB")
        usdt_rub_rate = await self.convert(Decimal("1.00"), "USDT", "RUB")
        _, source = await self._get_rates()
        return WalletQuote(
            base_amount=normalized_amount,
            base_currency=currency.upper(),
            usdt_amount=usdt_amount,
            rub_amount=rub_amount,
            usdt_rub_rate=usdt_rub_rate,
            source=source,
        )

    async def convert(self, amount: Decimal, from_currency: str, to_currency: str) -> Decimal:
        normalized_amount = normalize_amount(amount)
        source_currency = normalize_currency(from_currency)
        target_currency = normalize_currency(to_currency)
        if source_currency == target_currency:
            return normalized_amount

        rates, _ = await self._get_rates()
        usd_amount = to_usd(normalized_amount, source_currency, rates)
        converted = from_usd(usd_amount, target_currency, rates)
        return normalize_amount(converted)

    async def _get_rates(self) -> tuple[dict[str, Decimal], str]:
        current = monotonic()
        if self._cached_rates is not None and current < self._cache_until:
            return self._cached_rates, self._cache_source

        try:
            response = await self.http_client.get(self.api_url)
            response.raise_for_status()
            payload = response.json()
            rates_payload = payload.get("rates") if isinstance(payload, dict) else None
            if not isinstance(rates_payload, dict) or not rates_payload:
                raise ExchangeRateError("Exchange API returned an invalid payload.")

            rates = {str(code).upper(): normalize_amount(Decimal(str(value))) for code, value in rates_payload.items()}
            rates["USD"] = Decimal("1.00")
            rates["USDT"] = Decimal("1.00")
            self._cached_rates = rates
            self._cache_source = "live"
            self._cache_until = current + self.cache_ttl_seconds
            return rates, self._cache_source
        except (httpx.HTTPError, ValueError, ArithmeticError, ExchangeRateError) as error:
            if self._cached_rates is not None:
                logger.warning("Exchange rate refresh failed, using cached rates: %s", error)
                self._cache_until = current + min(self.cache_ttl_seconds, 120)
                return self._cached_rates, self._cache_source

            logger.warning("Exchange rate refresh failed, using fallback USDT/RUB rate: %s", error)
            fallback_rates = {
                "USD": Decimal("1.00"),
                "USDT": Decimal("1.00"),
                "RUB": self.fallback_usdt_rub_rate,
            }
            self._cached_rates = fallback_rates
            self._cache_source = "fallback"
            self._cache_until = current + min(self.cache_ttl_seconds, 120)
            return fallback_rates, self._cache_source


def normalize_currency(currency: str) -> str:
    return currency.strip().upper()


def normalize_amount(amount: Decimal) -> Decimal:
    return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def to_usd(amount: Decimal, currency: str, rates: dict[str, Decimal]) -> Decimal:
    normalized_currency = normalize_currency(currency)
    if normalized_currency in {"USD", "USDT"}:
        return amount
    rate = rates.get(normalized_currency)
    if rate is None or rate <= Decimal("0"):
        raise ExchangeRateError(f"Currency {normalized_currency} is not supported for conversion.")
    return amount / rate


def from_usd(amount: Decimal, currency: str, rates: dict[str, Decimal]) -> Decimal:
    normalized_currency = normalize_currency(currency)
    if normalized_currency in {"USD", "USDT"}:
        return amount
    rate = rates.get(normalized_currency)
    if rate is None or rate <= Decimal("0"):
        raise ExchangeRateError(f"Currency {normalized_currency} is not supported for conversion.")
    return amount * rate