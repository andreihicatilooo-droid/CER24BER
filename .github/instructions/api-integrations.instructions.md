---
description: "Use when working on API integrations: NicePay payments, GiftAPI catalog and orders, or adding a new external service. Load the corresponding hint file from doc/api/ before writing any integration code. Apply when editing integrations/, services/, or adding new providers."
applyTo: "src/cerber_bot/integrations/**"
---

# Правила работы с внешними API

Папка `doc/api/` содержит AI-friendly Markdown-файлы документации для каждого подключённого сервиса.
**Перед написанием кода интеграции — прочитай соответствующий .md файл или `doc/api/README.md`.**

## Карта hint-файлов

| Сервис | Hint-файл | Применять при работе с |
|---|---|---|
| NicePay (платежи) | `doc/api/nicepayapi.md` | `integrations/nicepay.py`, `services/payments.py`, `nicepay_webhook.py` |
| GiftAPI (каталог, заказы) | `doc/api/giftapi-hint.md` | `integrations/giftapi.py`, `services/giftapi.py`, `providers/giftapi_catalog.py` |

## Когда читать hint-файл

- При изменении существующего клиента интеграции
- При добавлении нового метода API
- При реализации подписи запросов (HMAC)
- При обработке вебхуков / callback'ов
- При добавлении нового провайдера каталога

## Формат документации API (стандарт проекта)

Каждый Markdown-файл в папке `doc/api/` должен начинаться с блока TL;DR, который ИИ считывает в первую очередь:

```markdown
# Название API

> ⚠️ **ВАЖНЫЕ ПРАВИЛА (TL;DR):**
> 1. Краткий факт о валюте
> 2. Краткий факт об авторизации (HMAC и т.п.)

## Привязка к проекту
- **client**: `src/cerber_bot/integrations/...`
```

## Как добавить hint-файл для нового сервиса

1. Создать `doc/api/{service}.md` по стандартам Markdown.
2. Заполнить `reference` из документации API сервиса.
3. Заполнить `project_references` путями к файлам в проекте.
4. Добавить блок `> ⚠️ ВАЖНЫЕ ПРАВИЛА` — список ключевых фактов на русском для быстрой загрузки в контекст.
5. Добавить запись в таблицу «Карта hint-файлов» выше.

## Правила реализации интеграций (общие)

- Клиент API (`integrations/`) — только HTTP-вызовы, без бизнес-логики.
- Сервис (`services/`) — оркестрация, бизнес-правила, вызывает клиента.
- Провайдер (`integrations/providers/`) — реализует `CatalogProvider`, регистрируется в `registry.py`.
- Настройки подключения — только через `config.py → Settings`, значения из `.env`.
- Новые env-переменные — синхронизировать с `.env.example` и `launcher.py → ENV_SECTIONS`.
- Подписи HMAC — всегда использовать `hmac.compare_digest()` для сравнения (constant-time).
- Секреты (токены, ключи) — никогда не логировать и не коммитить.
