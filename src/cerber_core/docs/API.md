# CERBER CORE — REST API Reference

**Base URL:** `http://localhost:8080`  
**Encryption:** AES-GCM-256 — все тела запросов и ответов шифруются  
**Wire format:** `Base64( nonce[12 bytes] || ciphertext || GCM-tag[16 bytes] )`

---

## Аутентификация

### Admin-эндпоинты

```
X-Admin-Key: <ADMIN_KEY из .env>
```

### API-эндпоинты (`/api/v1/*`)

```
X-API-Key: <raw_api_key полученный при создании сервиса>
Content-Type: application/json
```

---

## Формат ответов

Все ответы `/api/v1/*` зашифрованы:

```json
{
  "data": "<Base64(nonce || ciphertext || tag)>"
}
```

Расшифровка выполняется `secret_key` сервиса (AES-GCM-256).  
Ошибки также возвращаются в зашифрованном виде.

---

## Эндпоинты

### 1. Создать сервис

**`POST /admin/services`**

Создаёт нового потребителя API. Ключи возвращаются **один раз** — сохрани их немедленно.

**Заголовки:**
```
X-Admin-Key: <ADMIN_KEY>
Content-Type: application/json
```

**Тело запроса:**
```json
{
  "name": "my-service"
}
```

**Ответ `201 Created`:**
```json
{
  "id":         "717e4b0a-9633-4863-9c9d-0f15a3b4c12e",
  "name":       "my-service",
  "api_key":    "Npl+E2xD86yAiZUPGtpjKKsMp+QDbl5SkmC9E+ziF0k=",
  "secret_key": "rnD76v+iMukGKRZZUW9oSt189axZ1+WGIIkTeL7rAIo=",
  "note":       "Store api_key and secret_key securely — they will not be shown again."
}
```

> `api_key` — используется в заголовке `X-API-Key`  
> `secret_key` — используется для шифрования/расшифровки тел запросов и ответов (Base64, 32 байта)

---

### 2. Зарегистрировать пользователя

**`POST /api/v1/user/add`**

Регистрирует `user_hash` в биллинговом реестре. Идемпотентен — повторный вызов вернёт существующую запись.

**Заголовки:**
```
X-API-Key: <api_key>
Content-Type: application/json
```

**Тело запроса (plaintext перед шифрованием):**
```json
{
  "encrypted_user_hash": "<AES-GCM-256( user_hash, secret_key )>"
}
```

> `user_hash` — hex SHA-256 от `user_id`. Вычисляется на стороне клиента:  
> `user_hash = SHA256(user_id).hexdigest()`

**Ответ `200 OK` (расшифровать поле `data`):**
```json
{
  "user_hash":  "e3b0c44298fc1c149afbf4c8996fb924...",
  "status":     "active",
  "created_at": "2026-04-30T12:00:00Z"
}
```

**Ошибки:**

| HTTP | Причина |
|------|---------|
| 400  | Невалидное тело / не удалось расшифровать `encrypted_user_hash` |
| 401  | Отсутствует или неверный `X-API-Key` |
| 500  | Внутренняя ошибка сервера |

---

### 3. Получить баланс

**`GET /api/v1/balance?encrypted_user_hash=<value>`**

Возвращает баланс USDT и эквивалент в RUB по текущему курсу.

**Заголовки:**
```
X-API-Key: <api_key>
```

**Query-параметры:**

| Параметр | Тип | Описание |
|----------|-----|----------|
| `encrypted_user_hash` | string | AES-GCM-256( user_hash, secret_key ) → Base64 |

**Ответ `200 OK` (расшифровать `data`):**
```json
{
  "balance_usdt": 100.50,
  "balance_rub":  9045.00,
  "rate_usdt_rub": 90.0
}
```

**Ошибки:**

| HTTP | Причина |
|------|---------|
| 400  | Не удалось расшифровать `encrypted_user_hash` |
| 401  | Неверный `X-API-Key` |
| 500  | Внутренняя ошибка |

---

### 4. Список методов пополнения

**`GET /api/v1/topup/methods`**

Возвращает все активные способы пополнения баланса.

**Заголовки:**
```
X-API-Key: <api_key>
```

**Ответ `200 OK` (расшифровать `data`):**
```json
[
  {
    "id":          "uuid",
    "name":        "СБП",
    "code":        "sbp",
    "fee_percent": 1.5,
    "min_amount":  10.0,
    "max_amount":  10000.0,
    "currency":    "RUB",
    "is_active":   true
  }
]
```

---

### 5. Создать сессию пополнения

**`POST /api/v1/topup/create`**

Инициирует платёж. Возвращает реквизиты для оплаты.

**Заголовки:**
```
X-API-Key: <api_key>
Content-Type: application/json
```

**Тело запроса (plaintext перед шифрованием):**
```json
{
  "encrypted_user_hash": "<AES-GCM-256( user_hash, secret_key )>",
  "method_id":           "uuid-метода-из-/topup/methods",
  "amount_usdt":         50.0
}
```

**Ответ `201 Created` (расшифровать `data`):**
```json
{
  "id":          "uuid-сессии",
  "service_id":  "uuid-сервиса",
  "user_hash":   "e3b0c44298...",
  "method_id":   "uuid",
  "amount_usdt": 50.0,
  "amount_rub":  4500.0,
  "rate":        90.0,
  "status":      "pending",
  "payment_url": "",
  "requisites":  "{\"account\":\"4276...\",\"bank\":\"CerberBank\",\"amount_rub\":\"4500.00\",\"comment\":\"Pay abc12345\"}",
  "created_at":  "2026-04-30T12:00:00Z",
  "updated_at":  "2026-04-30T12:00:00Z"
}
```

**Статусы сессии:**

| Статус | Описание |
|--------|----------|
| `pending`   | Ожидает оплаты |
| `confirmed` | Оплата подтверждена, баланс зачислен |
| `failed`    | Платёж отклонён |
| `expired`   | Истёк срок ожидания |

**Ошибки:**

| HTTP | Причина |
|------|---------|
| 400  | Невалидное тело / неверные параметры |
| 401  | Неверный `X-API-Key` |
| 500  | Внутренняя ошибка |

---

### 6. Статус сессии пополнения

**`GET /api/v1/topup/status?session_id=<uuid>`**

**Заголовки:**
```
X-API-Key: <api_key>
```

**Query-параметры:**

| Параметр | Тип | Описание |
|----------|-----|----------|
| `session_id` | UUID | ID сессии из ответа `/topup/create` |

**Ответ `200 OK` (расшифровать `data`):**
```json
{
  "session_id":  "uuid-сессии",
  "status":      "pending",
  "amount_usdt": 50.0,
  "amount_rub":  4500.0,
  "updated_at":  "2026-04-30T12:01:00Z"
}
```

**Ошибки:**

| HTTP | Причина |
|------|---------|
| 400  | Отсутствует `session_id` |
| 401  | Неверный `X-API-Key` |
| 404  | Сессия не найдена |

---

## Шифрование — пример на Python

```python
import base64, hashlib, uuid
from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes

secret_key = base64.b64decode("rnD76v+iMukGKRZZUW9oSt189axZ1+WGIIkTeL7rAIo=")

# 1. Вычислить user_hash
user_id   = str(uuid.uuid4())
user_hash = hashlib.sha256(user_id.encode()).hexdigest()

# 2. Зашифровать для отправки
nonce  = get_random_bytes(12)
cipher = AES.new(secret_key, AES.MODE_GCM, nonce=nonce)
ct, tag = cipher.encrypt_and_digest(user_hash.encode())
encrypted_user_hash = base64.b64encode(nonce + ct + tag).decode()

# 3. Расшифровать ответ
def decrypt(secret_key: bytes, data_b64: str) -> dict:
    import json
    raw = base64.b64decode(data_b64)
    nonce, body = raw[:12], raw[12:]
    ct, tag = body[:-16], body[-16:]
    cipher = AES.new(secret_key, AES.MODE_GCM, nonce=nonce)
    return json.loads(cipher.decrypt_and_verify(ct, tag))
```

---

## Схема данных

### Таблица `services` (billing-db)
| Поле | Тип | Описание |
|------|-----|----------|
| `id` | UUID | Идентификатор |
| `name` | text | Название |
| `api_key_hash` | text | HMAC-SHA256(raw_api_key, MASTER_HMAC_KEY) |
| `secret_key_encrypted` | text | AES-GCM(secret_bytes, MASTER_AES_KEY) |
| `is_active` | bool | Активен |

### Таблица `users` (billing-db)
| Поле | Тип | Описание |
|------|-----|----------|
| `user_hash` | text (PK) | SHA-256 от user_id |
| `status` | text | `active` / `blocked` |

### Таблица `service_balances` (billing-db)
| Поле | Тип | Описание |
|------|-----|----------|
| `id` | UUID | Идентификатор |
| `service_id` | UUID | FK → services |
| `user_hash` | text | SHA-256 пользователя |
| `balance_usdt` | numeric | Баланс в USDT |

---

## Тестирование

Запустить интерактивный клиент:
```bash
pip install requests pycryptodome
python test_api.py
```

Быстрый старт:
1. `docker compose up -d` — запустить сервисы
2. Пункт **1** — ввести `ADMIN_KEY` из `.env`
3. Пункт **2** — создать сервис, применить ключи
4. Пункт **9** — автоматически создать пользователя
5. Пункт **4** — проверить баланс
6. Пункт **5** — посмотреть методы пополнения
