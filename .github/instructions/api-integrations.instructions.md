---
description: "Use when working on API integrations: NicePay payments, GiftAPI catalog and orders, or adding a new external service. Load the corresponding hint file from doc/api/ before writing any integration code. Apply when editing integrations/, services/, or adding new providers."
applyTo: "src/cerber_bot/integrations/**"
---

# Правила работы с внешними API

Папка `doc/api/` содержит AI-friendly hint-файлы для каждого подключённого сервиса.
**Перед написанием кода интеграции — прочитай соответствующий hint-файл.**

## Карта hint-файлов

| Сервис | Hint-файл | Применять при работе с |
|---|---|---|
| NicePay (платежи) | `doc/api/nicepayapi.json` | `integrations/nicepay.py`, `services/payments.py`, `nicepay_webhook.py` |
| GiftAPI (каталог, заказы) | `doc/api/giftapi-hint.json` | `integrations/giftapi.py`, `services/giftapi.py`, `providers/giftapi_catalog.py` |

## Когда читать hint-файл

- При изменении существующего клиента интеграции
- При добавлении нового метода API
- При реализации подписи запросов (HMAC)
- При обработке вебхуков / callback'ов
- При добавлении нового провайдера каталога

## Формат hint-файла (стандарт проекта)

Каждый `*-hint.json` или `*api.json` в папке `doc/api/` должен содержать:

```json
{
  "name": "service-name",
  "generated_at": "YYYY-MM-DD",
  "description": "Краткое описание для AI",
  "project_references": {
    "client": "src/cerber_bot/integrations/...",
    "service": "src/cerber_bot/services/...",
    "tests": "tests/test_..."
  },
  "reference": {
    "base_urls": {},
    "authentication": {},
    "money_format": {},
    "endpoints": {},
    "error_codes": {}
  },
  "current_project_state": {
    "implemented": [],
    "not_implemented_yet": [],
    "existing_env_vars": []
  },
  "implementation_rules": [],
  "copilot_prompt_lines": []
}
```

## Как добавить hint-файл для нового сервиса

1. Создать `doc/api/{service}-hint.json` по шаблону выше.
2. Заполнить `reference` из документации API сервиса.
3. Заполнить `project_references` путями к файлам в проекте.
4. Написать `copilot_prompt_lines` — список ключевых фактов на русском для быстрой загрузки в контекст.
5. Добавить запись в таблицу «Карта hint-файлов» выше.

## Правила реализации интеграций (общие)

- Клиент API (`integrations/`) — только HTTP-вызовы, без бизнес-логики.
- Сервис (`services/`) — оркестрация, бизнес-правила, вызывает клиента.
- Провайдер (`integrations/providers/`) — реализует `CatalogProvider`, регистрируется в `registry.py`.
- Настройки подключения — только через `config.py → Settings`, значения из `.env`.
- Новые env-переменные — синхронизировать с `.env.example` и `launcher.py → ENV_SECTIONS`.
- Подписи HMAC — всегда использовать `hmac.compare_digest()` для сравнения (constant-time).
- Секреты (токены, ключи) — никогда не логировать и не коммитить.
