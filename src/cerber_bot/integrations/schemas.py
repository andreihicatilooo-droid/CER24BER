from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True, frozen=True)
class Product:
    external_id: str
    provider: str
    title: str
    price: Decimal
    description: str = ""
    currency: str = "RUB"
    in_stock: int | None = None
    category: str | None = None
    url: str | None = None
    photo_url: str | None = None

    def formatted_price(self) -> str:
        normalized = self.price.quantize(Decimal("0.01"))
        text = format(normalized, "f").rstrip("0").rstrip(".")
        return f"{text} {self.currency}"


@dataclass(slots=True, frozen=True)
class ProviderResult:
    provider_name: str
    products: tuple[Product, ...]
    error: str | None = None


@dataclass(slots=True, frozen=True)
class CatalogSnapshot:
    products: tuple[Product, ...]
    provider_count: int
    collected_at: datetime
    errors: dict[str, str] = field(default_factory=dict)