"""HTTP-клиент GetMyTG на базе официального SDK."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
import hashlib
import hmac
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import gmt
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
    WEBHOOK_SIGNATURE_QUERY_PARAM = "sig"

    def __init__(
        self,
        *,
        base_url: str,
        http_client: httpx.AsyncClient,
        api_key: str | None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.sdk_base_url = self._normalize_sdk_base_url(base_url)
        self.http_client = http_client
        self.api_key = api_key.strip() if api_key else None
        self._public_sdk = gmt.AsyncGmt(
            api_key=None,
            base_url=self.sdk_base_url,
            http_client=http_client,
            max_retries=0,
        )
        self._auth_sdk = gmt.AsyncGmt(
            api_key=self.api_key,
            base_url=self.sdk_base_url,
            http_client=http_client,
            max_retries=0,
        )

    @property
    def is_configured(self) -> bool:
        return self.api_key is not None

    def _ensure_configured(self) -> None:
        if not self.is_configured:
            raise GetMyTGConfigError("GetMyTG API key is not configured")

    @staticmethod
    def _normalize_sdk_base_url(base_url: str) -> str:
        parts = urlsplit(base_url.strip())
        normalized_path = parts.path.rstrip("/")
        if normalized_path.endswith("/v1"):
            normalized_path = normalized_path[: -len("/v1")]
        return urlunsplit(parts._replace(path=normalized_path or "/" if parts.netloc else normalized_path)).rstrip("/")

    @staticmethod
    def build_webhook_signature(*, path: str, secret: str) -> str:
        normalized_path = path if path.startswith("/") else f"/{path}"
        return hmac.new(
            secret.encode("utf-8"),
            normalized_path.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    @classmethod
    def sign_webhook_url(cls, callback_url: str, secret: str) -> str:
        normalized_secret = secret.strip()
        if not normalized_secret:
            return callback_url

        parts = urlsplit(callback_url)
        query = dict(parse_qsl(parts.query, keep_blank_values=True))
        query[cls.WEBHOOK_SIGNATURE_QUERY_PARAM] = cls.build_webhook_signature(
            path=parts.path or "/",
            secret=normalized_secret,
        )
        return urlunsplit(parts._replace(query=urlencode(query)))

    @classmethod
    def verify_webhook_signature(
        cls,
        *,
        path: str,
        provided_signature: str,
        secret: str,
    ) -> bool:
        expected = cls.build_webhook_signature(path=path, secret=secret)
        return hmac.compare_digest(expected, provided_signature.strip())

    async def health_check(self) -> JsonDict:
        return await self._execute_public(lambda client: client.service.health_check())

    async def list_countries(
        self,
        *,
        auth: bool = False,
        sort: str | None = None,
        page: int | None = None,
        page_size: int | None = None,
        country_codes: str | None = None,
    ) -> JsonDict:
        normalized_sort = sort or "name_asc"
        normalized_page = page or 1
        normalized_page_size = page_size or 50
        if auth:
            return await self._execute_authenticated(
                lambda client: client.accounts.list(
                    sort=normalized_sort,
                    page=normalized_page,
                    page_size=normalized_page_size,
                    country_codes=country_codes or gmt.omit,
                )
            )
        return await self._execute_public(
            lambda client: client.accounts.list_countries(
                sort=normalized_sort,
                page=normalized_page,
                page_size=normalized_page_size,
                country_codes=country_codes or gmt.omit,
            )
        )

    async def list_countries_personal(
        self,
        *,
        sort: str | None = None,
        page: int | None = None,
        page_size: int | None = None,
        country_codes: str | None = None,
    ) -> JsonDict:
        return await self.list_countries(
            auth=True,
            sort=sort,
            page=page,
            page_size=page_size,
            country_codes=country_codes,
        )

    async def get_country(self, country_code: str) -> JsonDict:
        normalized_country = country_code.strip().upper()
        return await self._execute_authenticated(lambda client: client.accounts.retrieve(normalized_country))

    async def get_profile(self) -> JsonDict:
        return await self._execute_authenticated(lambda client: client.profile.retrieve())

    async def create_purchase(self, country_code: str) -> JsonDict:
        normalized_country = country_code.strip().upper()
        return await self._execute_authenticated(
            lambda client: client.purchases.create(country_code=normalized_country)
        )

    async def get_purchase(self, purchase_id: int) -> JsonDict:
        return await self._execute_authenticated(lambda client: client.purchases.retrieve(purchase_id))

    async def request_code(self, purchase_id: int, callback_url: str | None = None) -> JsonDict:
        if callback_url:
            return await self._execute_authenticated(
                lambda client: client.purchases.request_verification_code(
                    purchase_id,
                    callback_url=callback_url,
                )
            )
        return await self._execute_authenticated(
            lambda client: client.purchases.request_verification_code(purchase_id)
        )

    async def refund_purchase(self, purchase_id: int) -> JsonDict:
        return await self._execute_authenticated(lambda client: client.purchases.refund(purchase_id))

    async def _execute_public(
        self,
        operation: Callable[[gmt.AsyncGmt], object | Awaitable[object]],
    ) -> JsonDict:
        return await self._execute(self._public_sdk, operation, auth_required=False)

    async def _execute_authenticated(
        self,
        operation: Callable[[gmt.AsyncGmt], object | Awaitable[object]],
    ) -> JsonDict:
        self._ensure_configured()
        return await self._execute(self._auth_sdk, operation, auth_required=True)

    async def _execute(
        self,
        sdk_client: gmt.AsyncGmt,
        operation: Callable[[gmt.AsyncGmt], object | Awaitable[object]],
        *,
        auth_required: bool,
    ) -> JsonDict:
        try:
            result = operation(sdk_client)
            payload = await result if hasattr(result, "__await__") else result
        except gmt.APIStatusError as error:
            message = self._extract_error(error.body) or error.message or "GetMyTG request failed"
            raise GetMyTGRequestError(status_code=error.status_code, error=message) from error
        except (gmt.APIConnectionError, gmt.APITimeoutError) as error:
            raise GetMyTGError(f"GetMyTG network error: {error}") from error
        except gmt.APIResponseValidationError as error:
            message = self._extract_error(error.body) or str(error)
            raise GetMyTGError(f"GetMyTG invalid response: {message}") from error
        except gmt.GmtError as error:
            if auth_required and not self.is_configured:
                raise GetMyTGConfigError("GetMyTG API key is not configured") from error
            raise GetMyTGError(f"GetMyTG SDK error: {error}") from error

        return self._mapping(self._serialize_payload(payload), "GetMyTG response must be a JSON object")

    @staticmethod
    def _serialize_payload(payload: object) -> object:
        if isinstance(payload, Mapping):
            return dict(payload)
        to_dict = getattr(payload, "to_dict", None)
        if callable(to_dict):
            return to_dict(
                mode="json",
                use_api_names=True,
                exclude_unset=False,
                exclude_none=False,
            )
        return payload

    @staticmethod
    def _extract_error(payload: object) -> str | None:
        if not isinstance(payload, Mapping):
            return None
        for key in ("error", "message", "detail"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value
            if isinstance(value, Mapping):
                nested = GetMyTGClient._extract_error(value)
                if nested:
                    return nested
        return None

    @staticmethod
    def _mapping(value: object, message: str) -> JsonDict:
        if not isinstance(value, Mapping):
            raise GetMyTGError(message)
        return dict(value)
