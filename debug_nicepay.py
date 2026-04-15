"""Отладочный скрипт для тестирования NicePay webhook."""
from __future__ import annotations

import hashlib
import json
import urllib.error
import urllib.parse
import urllib.request

# ── читаем .env вручную ─────────────────────────────────────
env: dict[str, str] = {}
with open(".env", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip().strip('"').strip("'")

NICEPAY_SECRET = env.get("NICEPAY_SECRET", "")
NICEPAY_SHOP_ID = env.get("NICEPAY_SHOP_ID", "")

BASE = "https://significance-deborah-redeem-graphics.trycloudflare.com/webhooks/nicepay"
LOCAL = "http://localhost:8088/webhooks/nicepay"


def make_hash(params: dict[str, str], secret: str) -> str:
    values = [str(v) for k, v in sorted(params.items()) if k != "hash"]
    values.append(secret)
    return hashlib.sha256("{np}".join(values).encode("utf-8")).hexdigest()


def post_json(url: str, body: dict) -> tuple[int, str]:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={"Content-Type": "application/json", "User-Agent": "CerberDebug/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()
    except Exception as e:
        return 0, str(e)


def get_url(url: str, params: dict = None) -> tuple[int, str]:
    full = url + ("?" + urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(full, headers={"User-Agent": "CerberDebug/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()
    except Exception as e:
        return 0, str(e)


SEP = "─" * 60

print()
print(f"  NicePay Debug  →  {BASE}")
print(f"  NICEPAY_SECRET : {'✅ задан (' + str(len(NICEPAY_SECRET)) + ' символов)' if NICEPAY_SECRET else '❌ не задан'}")
print(f"  NICEPAY_SHOP_ID: {'✅ ' + NICEPAY_SHOP_ID if NICEPAY_SHOP_ID else '❌ не задан'}")
print(SEP)

# ── тест 1: без параметров ──────────────────────────────────
print("[1] GET без параметров")
s, b = get_url(BASE)
print(f"    → {s}: {b}")
print()

# ── тест 2: POST без hash ───────────────────────────────────
print("[2] POST JSON без hash")
s, b = post_json(BASE, {"order_id": "test-001", "amount": "100"})
print(f"    → {s}: {b}")
print()

# ── тест 3: POST с неверным hash ────────────────────────────
print("[3] POST с неверным hash")
bad_params = {
    "result": "success",
    "payment_id": "pay_test_001",
    "merchant_id": NICEPAY_SHOP_ID or "test_merchant",
    "order_id": "debug_order_001",
    "amount": "10000",
    "amount_currency": "RUB",
    "hash": "a" * 64,
}
s, b = post_json(BASE, bad_params)
print(f"    → {s}: {b}")
print()

# ── тест 4: с правильным hash (нужен секрет) ────────────────
if NICEPAY_SECRET:
    print("[4] POST с корректной подписью (success)")
    params = {
        "result": "success",
        "payment_id": "pay_debug_001",
        "merchant_id": NICEPAY_SHOP_ID or "test",
        "order_id": "debug_order_valid",
        "amount": "10000",
        "amount_currency": "RUB",
        "method": "card",
    }
    params["hash"] = make_hash(params, NICEPAY_SECRET)
    print(f"    hash: {params['hash'][:16]}...")
    s, b = post_json(BASE, params)
    print(f"    → {s}: {b}")
    print()

    print("[5] POST с корректной подписью (fail)")
    params2 = {
        "result": "fail",
        "payment_id": "pay_debug_002",
        "merchant_id": NICEPAY_SHOP_ID or "test",
        "order_id": "debug_order_fail",
        "amount": "5000",
        "amount_currency": "RUB",
    }
    params2["hash"] = make_hash(params2, NICEPAY_SECRET)
    s, b = post_json(BASE, params2)
    print(f"    → {s}: {b}")
    print()

    print("[6] GET с query-params и корректной подписью")
    get_params = {
        "result": "success",
        "payment_id": "pay_debug_get",
        "merchant_id": NICEPAY_SHOP_ID or "test",
        "order_id": "debug_get_001",
        "amount": "1000",
        "amount_currency": "RUB",
    }
    get_params["hash"] = make_hash(get_params, NICEPAY_SECRET)
    s, b = get_url(BASE, get_params)
    print(f"    → {s}: {b}")
    print()
else:
    print("[4-6] ⚠️  Пропущены — NICEPAY_SECRET не задан")
    print()

print(SEP)
print("Готово.")
