#!/usr/bin/env python3
"""
CERBER CORE — интерактивный консольный тест REST API.

Протокол:
  - Аутентификация: заголовок X-API-Key
  - Шифрование: AES-GCM-256 (Base64(nonce[12] || ciphertext || tag[16]))
  - Ответы API содержат поле {"data": "<encrypted>"}, кроме /admin/services

Требования:
    pip install requests pycryptodome
"""

import base64
import hashlib
import json
import os
import sys
import textwrap
import urllib.parse
from getpass import getpass

try:
    import requests
    from Crypto.Cipher import AES
    from Crypto.Random import get_random_bytes
except ImportError:
    print("Установи зависимости: pip install requests pycryptodome")
    sys.exit(1)

# ─── AES-GCM helpers ─────────────────────────────────────────────────────────

def aes_encrypt(key: bytes, plaintext: bytes) -> str:
    """Encrypt plaintext → Base64(nonce[12] || ciphertext || tag[16])."""
    nonce = get_random_bytes(12)
    cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
    ciphertext, tag = cipher.encrypt_and_digest(plaintext)
    return base64.b64encode(nonce + ciphertext + tag).decode()


def aes_decrypt(key: bytes, encoded: str) -> bytes:
    """Decrypt Base64(nonce || ciphertext || tag) → plaintext."""
    data = base64.b64decode(encoded)
    nonce, payload = data[:12], data[12:]
    ciphertext, tag = payload[:-16], payload[-16:]
    cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
    return cipher.decrypt_and_verify(ciphertext, tag)


def encrypt_user_hash(user_hash: str, secret_key: bytes) -> str:
    return aes_encrypt(secret_key, user_hash.encode())


def decrypt_response(resp_json: dict, secret_key: bytes) -> dict:
    """Decode {"data": "<encrypted>"} envelope."""
    if "data" not in resp_json:
        return resp_json
    return json.loads(aes_decrypt(secret_key, resp_json["data"]))


def key_from_hex(hex_str: str) -> bytes:
    key = bytes.fromhex(hex_str)
    if len(key) != 32:
        raise ValueError("secret_key must be 32 bytes (64 hex chars)")
    return key


# ─── Session state ────────────────────────────────────────────────────────────

class Session:
    def __init__(self):
        self.base_url: str = "http://localhost:8080"
        self.api_key: str = ""
        self.secret_key: bytes = b""
        self.admin_key: str = ""

    @property
    def headers(self) -> dict:
        return {"X-API-Key": self.api_key, "Content-Type": "application/json"}

    def configured(self) -> bool:
        return bool(self.api_key and self.secret_key)


session = Session()


# ─── API calls ────────────────────────────────────────────────────────────────

def call(method: str, path: str, *, params=None, body=None, admin=False) -> dict:
    url = session.base_url + path
    headers = session.headers.copy()
    if admin:
        headers["X-Admin-Key"] = session.admin_key

    encrypted_body = None
    if body is not None:
        encrypted_body = json.dumps(body)

    resp = requests.request(
        method,
        url,
        headers=headers,
        params=params,
        data=encrypted_body,
        timeout=10,
    )

    print(f"\n  HTTP {resp.status_code}")
    raw = resp.json()

    if "data" in raw and session.secret_key:
        try:
            decrypted = decrypt_response(raw, session.secret_key)
            return decrypted
        except Exception as e:
            print(f"  [!] Расшифровка не удалась: {e}")
            return raw
    return raw


# ─── Menu actions ─────────────────────────────────────────────────────────────

def configure():
    print("\n── Конфигурация ──────────────────────────────────")
    session.base_url = input(f"  Base URL [{session.base_url}]: ").strip() or session.base_url
    session.api_key = input("  X-API-Key: ").strip()
    hex_key = input("  Secret Key (64 hex символа): ").strip()
    try:
        session.secret_key = key_from_hex(hex_key)
        print("  ✓ Конфигурация сохранена")
    except ValueError as e:
        print(f"  ✗ {e}")


def configure_admin():
    print("\n── Конфигурация Admin ────────────────────────────")
    session.base_url = input(f"  Base URL [{session.base_url}]: ").strip() or session.base_url
    session.admin_key = input("  X-Admin-Key: ").strip()
    print("  ✓ Admin-ключ сохранён")


def admin_create_service():
    print("\n── POST /admin/services ──────────────────────────")
    name = input("  Название сервиса: ").strip()
    if not name:
        print("  Имя не может быть пустым")
        return
    result = call("POST", "/admin/services", body={"name": name}, admin=True)
    _print_result(result)
    if "api_key" in result:
        print("\n  ⚠  Сохрани ключи — они показываются один раз!")
        if input("  Применить эти ключи как текущие? [y/N]: ").lower() == "y":
            session.api_key = result["api_key"]
            try:
                session.secret_key = key_from_hex(result["secret_key"])
                print("  ✓ Ключи применены")
            except ValueError as e:
                print(f"  ✗ {e}")


def user_add():
    print("\n── POST /api/v1/user/add ─────────────────────────")
    user_hash = input("  user_hash (hex SHA-256): ").strip()
    if not user_hash:
        print("  Значение не может быть пустым")
        return
    enc = encrypt_user_hash(user_hash, session.secret_key)
    result = call("POST", "/api/v1/user/add", body={"encrypted_user_hash": enc})
    _print_result(result)


def balance_get():
    print("\n── GET /api/v1/balance ───────────────────────────")
    user_hash = input("  user_hash (hex SHA-256): ").strip()
    if not user_hash:
        print("  Значение не может быть пустым")
        return
    enc = encrypt_user_hash(user_hash, session.secret_key)
    result = call("GET", "/api/v1/balance", params={"encrypted_user_hash": enc})
    _print_result(result)


def topup_methods():
    print("\n── GET /api/v1/topup/methods ─────────────────────")
    result = call("GET", "/api/v1/topup/methods")
    _print_result(result)


def topup_create():
    print("\n── POST /api/v1/topup/create ─────────────────────")
    user_hash = input("  user_hash (hex SHA-256): ").strip()
    method_id = input("  method_id (UUID): ").strip()
    amount_str = input("  amount_usdt: ").strip()
    try:
        amount = float(amount_str)
    except ValueError:
        print("  Некорректная сумма")
        return
    enc = encrypt_user_hash(user_hash, session.secret_key)
    result = call("POST", "/api/v1/topup/create", body={
        "encrypted_user_hash": enc,
        "method_id": method_id,
        "amount_usdt": amount,
    })
    _print_result(result)


def topup_status():
    print("\n── GET /api/v1/topup/status ──────────────────────")
    session_id = input("  session_id (UUID): ").strip()
    result = call("GET", "/api/v1/topup/status", params={"session_id": session_id})
    _print_result(result)


def compute_user_hash():
    print("\n── Вычислить user_hash ───────────────────────────")
    user_id = input("  user_id (UUID): ").strip()
    h = hashlib.sha256(user_id.encode()).hexdigest()
    print(f"  user_hash = {h}")


def _print_result(data):
    formatted = json.dumps(data, ensure_ascii=False, indent=2)
    for line in formatted.splitlines():
        print("  " + line)


# ─── Main menu ────────────────────────────────────────────────────────────────

MENU = [
    ("0", "Конфигурация API-ключей (X-API-Key + secret_key)", configure),
    ("1", "Конфигурация Admin-ключа (X-Admin-Key)",           configure_admin),
    ("",  None, None),
    ("2", "POST /admin/services — создать сервис",             admin_create_service),
    ("",  None, None),
    ("3", "POST /api/v1/user/add — зарегистрировать user_hash", user_add),
    ("4", "GET  /api/v1/balance — баланс пользователя",        balance_get),
    ("",  None, None),
    ("5", "GET  /api/v1/topup/methods — методы пополнения",    topup_methods),
    ("6", "POST /api/v1/topup/create — создать сессию пополнения", topup_create),
    ("7", "GET  /api/v1/topup/status — статус сессии",         topup_status),
    ("",  None, None),
    ("8", "Вычислить user_hash из user_id",                    compute_user_hash),
    ("",  None, None),
    ("q", "Выход",                                             None),
]


def print_menu():
    print("\n╔══════════════════════════════════════════════════╗")
    print("║        CERBER CORE — API Test Console            ║")
    print("╠══════════════════════════════════════════════════╣")
    status = "✓" if session.configured() else "✗ не настроено"
    print(f"║  API URL  : {session.base_url:<37}║")
    print(f"║  X-API-Key: {(session.api_key[:34] + '...' if len(session.api_key) > 37 else session.api_key):<37}║")
    print(f"║  SecretKey: {'настроен' if session.secret_key else 'не задан':<37}║")
    print("╠══════════════════════════════════════════════════╣")
    for key, label, _ in MENU:
        if key == "":
            print("║                                                  ║")
        elif key == "q":
            print(f"║  [{key}] {label:<44}║")
        else:
            print(f"║  [{key}] {label:<44}║")
    print("╚══════════════════════════════════════════════════╝")


def main():
    print("\nCERBER CORE API Test Console")
    print("Шифрование: AES-GCM-256 | Протокол: REST/JSON")

    action_map = {key: fn for key, label, fn in MENU if key and fn}

    while True:
        print_menu()
        choice = input("\n  Выбор: ").strip().lower()
        if choice == "q":
            print("  Выход.")
            break
        action = action_map.get(choice)
        if action is None:
            print("  Неверный выбор")
            continue
        # Guard: require configuration for protected calls
        if choice not in ("0", "1", "8", "q") and not session.configured():
            print("  ✗ Сначала настройте API-ключи (пункт 0)")
            continue
        if choice == "2" and not session.admin_key:
            print("  ✗ Сначала настройте Admin-ключ (пункт 1)")
            continue
        try:
            action()
        except requests.exceptions.ConnectionError:
            print(f"\n  ✗ Не удалось подключиться к {session.base_url}")
            print("    Убедитесь, что сервис запущен (docker compose up)")
        except requests.exceptions.Timeout:
            print("\n  ✗ Таймаут запроса (10 сек)")
        except Exception as e:
            print(f"\n  ✗ Ошибка: {e}")


if __name__ == "__main__":
    main()
