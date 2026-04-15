"""Удалён — провайдерный слой не используется в production."""


class BaseHttpCatalogProvider(CatalogProvider):
    def __init__(
        self,
        name: str,
        base_url: str,
        http_client: httpx.AsyncClient,
        token: str | None = None,
    ) -> None:
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.http_client = http_client
        self.token = token

    async def get_json(self, path: str) -> object:
        headers = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        response = await self.http_client.get(f"{self.base_url}{path}", headers=headers)
        response.raise_for_status()
        return response.json()

    @staticmethod
    def ensure_mapping(payload: object, message: str) -> Mapping[str, object]:
        if not isinstance(payload, Mapping):
            raise ProviderError(message)
        return payload

    @staticmethod
    def to_decimal(value: object) -> Decimal:
        try:
            return Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError) as error:
            raise ProviderError(CATALOG_PROVIDER_TEXT.invalid_price(value)) from error

    @staticmethod
    def to_int(value: object | None) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError) as error:
            raise ProviderError(CATALOG_PROVIDER_TEXT.invalid_stock(value)) from error