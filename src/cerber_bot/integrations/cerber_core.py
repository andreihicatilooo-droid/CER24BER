"""Клиент CERBER Core для операций биллинга и topup-сессий."""

from __future__ import annotations

import base64
import hashlib
import json
import os
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import httpx
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class CerberCoreError(RuntimeError):
    pass


class CerberCoreConfigurationError(CerberCoreError):
    pass


@dataclass(slots=True, frozen=True)
class CerberCoreTopupMethod:
    id: str
    name: str
    code: str
    fee_percent: Decimal
    min_amount: Decimal
    max_amount: Decimal
    currency: str
    is_active: bool


@dataclass(slots=True, frozen=True)
class CerberCoreTopupSession:
    id: str
    service_id: str
    user_hash: str
    method_id: str
    amount_usdt: Decimal
    amount_rub: Decimal
    rate: Decimal
    status: str
    payment_url: str
    requisites: dict[str, object]
    created_at: str
    updated_at: str


@dataclass(slots=True, frozen=True)
class CerberCoreBalance:
    balance_usdt: Decimal
    balance_rub: Decimal
    rate_usdt_rub: Decimal


@dataclass(slots=True, frozen=True)
class CerberCoreTransaction:
    id: str
    service_id: str
    user_hash: str
    type: str
    amount_usdt: Decimal
    amount_rub: Decimal
    rate: Decimal
    description: str
    created_at: str


class CerberCoreClient:
    def __init__(
        self,
        *,
        base_url: str,
        http_client: httpx.AsyncClient,
        api_key: str | None,
        secret_key: str | None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.http_client = http_client
        self.api_key = (api_key or "").strip()
        self._secret_key_raw = (secret_key or "").strip()
        self._methods_by_code: dict[str, CerberCoreTopupMethod] | None = None

    @property
    def is_configured(self) -> bool:
        return bool(self.base_url and self.api_key and self._secret_key_raw)

    def ensure_configured(self) -> None:
        if not self.is_configured:
            raise CerberCoreConfigurationError("CERBER Core billing не настроен.")

    async def register_user(self, telegram_id: int) -> dict[str, Any]:
        encrypted_user_hash = self._encrypt_user_hash(telegram_id)
        payload = await self._request(
            "POST",
            "/api/v1/user/add",
            json_body={"encrypted_user_hash": encrypted_user_hash},
        )
        if not isinstance(payload, dict):
            raise CerberCoreError("CERBER Core вернул неожиданный ответ при регистрации пользователя.")
        return payload

    async def get_balance(self, telegram_id: int) -> CerberCoreBalance:
        encrypted_user_hash = self._encrypt_user_hash(telegram_id)
        payload = await self._request(
            "GET",
            "/api/v1/balance",
            params={"encrypted_user_hash": encrypted_user_hash},
        )
        if not isinstance(payload, dict):
            raise CerberCoreError("CERBER Core вернул неожиданный ответ по балансу.")
        return CerberCoreBalance(
            balance_usdt=_to_decimal(payload.get("balance_usdt")),
            balance_rub=_to_decimal(payload.get("balance_rub")),
            rate_usdt_rub=_to_decimal(payload.get("rate_usdt_rub")),
        )

    async def list_transactions(
        self,
        telegram_id: int,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[CerberCoreTransaction, ...]:
        encrypted_user_hash = self._encrypt_user_hash(telegram_id)
        payload = await self._request(
            "GET",
            "/api/v1/balance/history",
            params={
                "encrypted_user_hash": encrypted_user_hash,
                "limit": str(limit),
                "offset": str(offset),
            },
        )
        if not isinstance(payload, list):
            raise CerberCoreError("CERBER Core вернул неожиданный ответ по истории транзакций.")
        return tuple(_to_transaction(item) for item in payload if isinstance(item, dict))

    async def list_topup_methods(self, *, force_refresh: bool = False) -> tuple[CerberCoreTopupMethod, ...]:
        if self._methods_by_code is not None and not force_refresh:
            return tuple(self._methods_by_code.values())

        payload = await self._request("GET", "/api/v1/topup/methods")
        if not isinstance(payload, list):
            raise CerberCoreError("CERBER Core вернул неожиданный список методов пополнения.")

        methods = tuple(_to_topup_method(item) for item in payload if isinstance(item, dict))
        self._methods_by_code = {method.code: method for method in methods}
        return methods

    async def get_topup_method(self, code: str) -> CerberCoreTopupMethod:
        normalized_code = code.strip()
        if not normalized_code:
            raise CerberCoreConfigurationError("Не задан код topup-метода CERBER Core.")
        methods = await self.list_topup_methods()
        method = next((item for item in methods if item.code == normalized_code), None)
        if method is None:
            raise CerberCoreConfigurationError(f"Topup-метод CERBER Core не найден: {normalized_code}")
        return method

    async def create_topup_session(
        self,
        *,
        telegram_id: int,
        amount_usdt: Decimal,
        method_code: str,
    ) -> CerberCoreTopupSession:
        self.ensure_configured()
        await self.register_user(telegram_id)
        method = await self.get_topup_method(method_code)
        encrypted_user_hash = self._encrypt_user_hash(telegram_id)
        payload = await self._request(
            "POST",
            "/api/v1/topup/create",
            json_body={
                "encrypted_user_hash": encrypted_user_hash,
                "method_id": method.id,
                "amount_usdt": float(amount_usdt),
            },
        )
        if not isinstance(payload, dict):
            raise CerberCoreError("CERBER Core вернул неожиданный ответ при создании topup-сессии.")
        return _to_topup_session(payload)

    async def confirm_topup(self, session_id: str) -> CerberCoreTopupSession:
        payload = await self._request(
            "POST",
            "/api/v1/topup/confirm",
            json_body={"session_id": session_id},
        )
        if not isinstance(payload, dict):
            raise CerberCoreError("CERBER Core вернул неожиданный ответ при подтверждении topup-сессии.")
        return _to_topup_session(payload)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        json_body: dict[str, object] | None = None,
    ) -> object:
        self.ensure_configured()
        headers = {"X-API-Key": self.api_key}
        if json_body is not None:
            headers["Content-Type"] = "application/json"

        response = await self.http_client.request(
            method,
            f"{self.base_url}{path}",
            headers=headers,
            params=params,
            json=json_body,
        )
        try:
            payload = response.json()
        except ValueError as error:
            raise CerberCoreError("CERBER Core вернул не-JSON ответ.") from error

        if isinstance(payload, dict) and "data" in payload:
            decrypted = self._decrypt_payload(str(payload["data"]))
            if response.is_error:
                raise CerberCoreError(_extract_error_message(decrypted))
            return decrypted

        if response.is_error:
            raise CerberCoreError(_extract_error_message(payload))
        return payload

    def _encrypt_user_hash(self, telegram_id: int) -> str:
        user_hash = hashlib.sha256(str(telegram_id).encode("utf-8")).hexdigest()
        aesgcm = AESGCM(self._secret_key_bytes())
        nonce = _random_nonce()
        ciphertext = aesgcm.encrypt(nonce, user_hash.encode("utf-8"), None)
        return base64.b64encode(nonce + ciphertext).decode("ascii")

    def _decrypt_payload(self, encoded: str) -> object:
        raw = base64.b64decode(encoded)
        if len(raw) < 13:
            raise CerberCoreError("CERBER Core вернул слишком короткий encrypted payload.")
        nonce = raw[:12]
        ciphertext = raw[12:]
        aesgcm = AESGCM(self._secret_key_bytes())
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)
        return json.loads(plaintext.decode("utf-8"))

    def _secret_key_bytes(self) -> bytes:
        value = self._secret_key_raw
        try:
            decoded = base64.b64decode(value)
            if len(decoded) == 32:
                return decoded
        except Exception:
            pass
        try:
            decoded = bytes.fromhex(value)
            if len(decoded) == 32:
                return decoded
        except ValueError:
            pass
        raise CerberCoreConfigurationError("CERBER Core secret key должен быть Base64 или hex длиной 32 байта.")


def _random_nonce() -> bytes:
    return os.urandom(12)


def _extract_error_message(payload: object) -> str:
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, str):
            return error
        if isinstance(error, dict):
            message = error.get("message")
            if isinstance(message, str):
                return message
    return "CERBER Core request failed."


def _to_decimal(value: object) -> Decimal:
    return Decimal(str(value or "0"))


def _to_topup_method(payload: dict[str, object]) -> CerberCoreTopupMethod:
    return CerberCoreTopupMethod(
        id=str(payload.get("id") or ""),
        name=str(payload.get("name") or ""),
        code=str(payload.get("code") or ""),
        fee_percent=_to_decimal(payload.get("fee_percent")),
        min_amount=_to_decimal(payload.get("min_amount")),
        max_amount=_to_decimal(payload.get("max_amount")),
        currency=str(payload.get("currency") or ""),
        is_active=bool(payload.get("is_active")),
    )


def _to_topup_session(payload: dict[str, object]) -> CerberCoreTopupSession:
    requisites_raw = payload.get("requisites")
    requisites: dict[str, object]
    if isinstance(requisites_raw, str) and requisites_raw:
        try:
            parsed = json.loads(requisites_raw)
            requisites = parsed if isinstance(parsed, dict) else {}
        except ValueError:
            requisites = {}
    elif isinstance(requisites_raw, dict):
        requisites = requisites_raw
    else:
        requisites = {}

    return CerberCoreTopupSession(
        id=str(payload.get("id") or ""),
        service_id=str(payload.get("service_id") or ""),
        user_hash=str(payload.get("user_hash") or ""),
        method_id=str(payload.get("method_id") or ""),
        amount_usdt=_to_decimal(payload.get("amount_usdt")),
        amount_rub=_to_decimal(payload.get("amount_rub")),
        rate=_to_decimal(payload.get("rate")),
        status=str(payload.get("status") or ""),
        payment_url=str(payload.get("payment_url") or ""),
        requisites=requisites,
        created_at=str(payload.get("created_at") or ""),
        updated_at=str(payload.get("updated_at") or ""),
    )


def _to_transaction(payload: dict[str, object]) -> CerberCoreTransaction:
    return CerberCoreTransaction(
        id=str(payload.get("id") or ""),
        service_id=str(payload.get("service_id") or ""),
        user_hash=str(payload.get("user_hash") or ""),
        type=str(payload.get("type") or ""),
        amount_usdt=_to_decimal(payload.get("amount_usdt")),
        amount_rub=_to_decimal(payload.get("amount_rub")),
        rate=_to_decimal(payload.get("rate")),
        description=str(payload.get("description") or ""),
        created_at=str(payload.get("created_at") or ""),
    )