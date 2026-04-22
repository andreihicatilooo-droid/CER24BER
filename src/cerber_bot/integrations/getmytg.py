"""HTTP-клиент GetMyTG."""

from __future__ import annotations

from collections.abc import Mapping

import httpx


JsonDict = dict[str, object]


class GetMyTGError(RuntimeError):
    pass


class GetMyTGConfigError(GetMyTGError):
    pass


class GetMyTGRequestError(GetMyTGError):
    def __init__(self, *, status_code: int | None, error: str) -> None:
        super().__init__(error)
        self.status_code = status_code
        self.error = error


class GetMyTGClient:
    def __init__(
        self,
        *,
        base_url: str,
        http_client: httpx.AsyncClient,
        api_key: str | None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.http_client = http_client
        self.api_key = api_key.strip() if api_key else None

    @property
    def is_configured(self) -> bool:
        return self.api_key is not None

    def _ensure_configured(self) -> None:
        if not self.is_configured:
            raise GetMyTGConfigError("GetMyTG API key is not configured")

    async def health_check(self) -> JsonDict:
        return await self._request_json("GET", "/v1/service/health", auth_required=False)

    async def list_countries(self, *, auth: bool = False) -> JsonDict:
        path = "/v1/accounts" if auth else "/v1/accounts/countries"
        return await self._request_json("GET", path, auth_required=auth)

    async def list_countries_personal(self) -> JsonDict:
        return await self._request_json("GET", "/v1/accounts", auth_required=True)

    async def get_country(self, country_code: str) -> JsonDict:
        normalized_country = country_code.strip().upper()
        return await self._request_json("GET", f"/v1/accounts/{normalized_country}", auth_required=True)

    async def get_profile(self) -> JsonDict:
        return await self._request_json("GET", "/v1/profile", auth_required=True)

    async def create_purchase(self, country_code: str) -> JsonDict:
        normalized_country = country_code.strip().upper()
        return await self._request_json(
            "POST",
            "/v1/purchases",
            auth_required=True,
            json_body={"country_code": normalized_country},
        )

    async def get_purchase(self, purchase_id: int) -> JsonDict:
        return await self._request_json("GET", f"/v1/purchases/{purchase_id}", auth_required=True)

    async def request_code(self, purchase_id: int, callback_url: str | None = None) -> JsonDict:
        json_body: JsonDict = {}
        if callback_url:
            json_body["callback_url"] = callback_url
        return await self._request_json(
            "POST",
            f"/v1/purchases/{purchase_id}/request-code",
            auth_required=True,
            json_body=json_body,
        )

    async def refund_purchase(self, purchase_id: int) -> JsonDict:
        return await self._request_json(
            "POST",
            f"/v1/purchases/{purchase_id}/refund",
            auth_required=True,
        )

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        auth_required: bool,
        json_body: Mapping[str, object] | None = None,
    ) -> JsonDict:
        if auth_required:
            self._ensure_configured()

        headers = {"Accept": "application/json"}
        if auth_required and self.api_key:
            headers["x-api-key"] = self.api_key

        try:
            response = await self.http_client.request(
                method,
                f"{self.base_url}{path}",
                headers=headers,
                json=json_body,
            )
        except (httpx.ConnectError, httpx.TimeoutException) as error:
            raise GetMyTGError(f"GetMyTG network error: {error}") from error

        try:
            payload = response.json()
        except ValueError:
            payload = None

        if response.is_error:
            message = self._extract_error(payload) or response.text or "GetMyTG request failed"
            raise GetMyTGRequestError(status_code=response.status_code, error=message)

        return self._mapping(payload, "GetMyTG response must be a JSON object")

    @staticmethod
    def _extract_error(payload: object) -> str | None:
        if not isinstance(payload, Mapping):
            return None
        for key in ("error", "message", "detail"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value
        return None

    @staticmethod
    def _mapping(value: object, message: str) -> JsonDict:
        if not isinstance(value, Mapping):
            raise GetMyTGError(message)
        return dict(value)
