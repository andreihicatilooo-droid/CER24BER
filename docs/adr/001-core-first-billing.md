# ADR-001: Core-first billing

**Status:** Accepted
**Date:** 2026-06-11
**Decision:** Вариант **B — Core-first**

## Контекст

Сейчас в `cerber_bot` параллельно работают:

- **Локальный кошелёк** — поля `TelegramUser.balance` / `held_balance`, таблица `wallet_transactions`, пополнение через NicePay/Rukassa с зачислением в SQLite/Postgres бота.
- **Cerber Core** (Go) — единый billing API: баланс в USDT, topup-сессии, `hold` / `unblock` / `transfer` / `withdrawal`, audit log в `transactions`.

Гибрид создаёт расхождения балансов, дублирует платёжную логику и усложняет escrow/вывод.

## Решение

**Cerber Core — единственный источник истины для денег.**
Бот хранит только:

| Данные | Где живут |
|--------|-----------|
| Баланс USDT, история операций | `cerber_core` (billing-db) |
| Профиль Telegram, заказы, сделки, UI-состояние | `cerber_bot` DB |
| «Заблокировано в escrow» (для UI) | производная от активных `escrow_deals`, не из `held_balance` |

Локальные `balance` / `held_balance` в ORM — **legacy**, только на период миграции; новые операции идут через `LedgerService` → `CerberCoreClient`.

## Маппинг операций

| Сценарий бота | Core API | `operation_id` |
|---------------|----------|----------------|
| Регистрация `/start` | `POST /api/v1/user/add` | — |
| Показ кошелька | `GET /api/v1/balance` | — |
| История | `GET /api/v1/balance/history` | — |
| Пополнение | `POST /api/v1/topup/create` → confirm | session id |
| Покупка в витрине | `POST /api/v1/balance/adjust` (delta −) | `purchase:{order_id}` |
| Escrow: создание | `POST /api/v1/balance/hold` | `deal:{id}:hold` |
| Escrow: отмена / отклонение | `POST /api/v1/balance/unblock` | `deal:{id}:unblock` |
| Escrow: успех | `POST /api/v1/balance/adjust` (+ seller) | `deal:{id}:release` |
| Escrow: refund модератором | `POST /api/v1/balance/unblock` | `deal:{id}:refund` |
| P2P перевод (если нужен) | `POST /api/v1/balance/transfer` | `transfer:{uuid}` |
| Вывод USDT | `POST /api/v1/withdrawal/create` | `withdrawal:{id}` |
| Отклонение вывода | `POST /api/v1/withdrawal/cancel` | `withdrawal:{id}:cancel` |
| Admin adjust | `POST /api/v1/balance/adjust` | `admin:{admin_id}:{uuid}` |

### Escrow и «held» в UI

В Core `hold` списывает USDT с доступного баланса (нет отдельного поля `held_balance`).
Для отображения «заблокировано» бот суммирует суммы активных сделок пользователя из `escrow_deals`, а не читает `TelegramUser.held_balance`.

### Валюты

- **Ledger Core:** USDT.
- **UI бота:** USD/RUB/USDT через `ExchangeRateService` (как сейчас для витрины).
- Конвертация перед вызовом Core: wallet amount → USDT по курсу Core (`rate_usdt_rub`) или exchange service.

## Конфигурация

```env
BILLING_MODE=core_first          # local — только dev/legacy
CERBER_CORE_ENABLED=true         # синоним для core_first
CERBER_CORE_BASE_URL=http://localhost:8080
CERBER_CORE_API_KEY=...
CERBER_CORE_SECRET_KEY=...       # AES-256 key, base64 или hex
CERBER_CORE_TOPUP_METHOD_CODE=card_ru
```

При `BILLING_MODE=core_first` бот **не стартует** без валидных Core credentials.

NicePay/Rukassa в Core-first режиме:

- **Предпочтительно:** topup только через Core (`/api/v1/topup/*`), webhook confirm на Core admin.
- **Переходный период:** bot-side webhook → `LedgerService` credit через `adjust` с idempotent `operation_id`.

## Фазы миграции

### Фаза 1 — Foundation (текущий PR)

- [x] ADR-001
- [x] `CerberCoreClient`: hold, unblock, transfer, withdrawal
- [x] `LedgerService` — единая точка входа для billing
- [x] `BILLING_MODE`, fail-fast при `core_first`
- [x] Unit-тесты client + ledger

### Фаза 2 — Read path

- [x] `WalletReadService` + `StoreService.get_wallet()` → Core balance + escrow-held из deals
- [x] `DealService._build_balance_view` → Core через `WalletReadService`
- [x] `UserService.register_or_update` → `register_user` в Core
- [x] Web/TG кошелёк используют `get_wallet_snapshot` (без изменений handlers)

### Фаза 3 — Write path: payments

- [x] `PaymentService._complete_paid_topup` — Core confirm без local credit в core-first
- [x] NicePay / Rukassa / Stars webhook → только `confirm_topup` + balance из `LedgerService`
- [x] Legacy `BILLING_MODE=local` сохраняет local credit + optional Core confirm

### Фаза 4 — Write path: commerce

- [x] `StoreService.purchase_offer` → Core debit через `LedgerService.debit_usdt`
- [x] `TgAccountService.buy_account` / `refund` → Core debit/credit
- [x] Исправлен порядок инициализации `exchange_rate_service` в `AppContainer.build`
- [x] Тесты: `test_store_service_core_first_*`, `test_tgaccount_service_core_first_*`

### Фаза 5 — Escrow & withdrawal

- [x] `DealService` → hold/unblock/release через `LedgerService`
- [x] Withdrawal → Core withdrawal API (`create_withdrawal` / `cancel_withdrawal`)
- [x] `DealService` в `AppContainer` получает `ledger_service`
- [x] Тесты: `test_deal_service_core_first_*`
- [ ] Удалить мутации `user.balance` / `held_balance` из legacy `BILLING_MODE=local` (оставлено для dev)

### Фаза 6 — Cleanup

- [x] `UserService.adjust_balance` и admin UI → Core через `LedgerService`
- [x] `StoreService.top_up_balance` заблокирован в core-first (только платёжные методы)
- [x] Deprecation-комментарии на `TelegramUser.balance` / `wallet_transactions`
- [x] Скрипт миграции `scripts/sync_local_balances_to_core.py`
- [x] README и `.env.example`: core-first как default для prod
- [ ] `ceer_bot`: Core balance для игровых ставок (отдельная задача)
- [ ] Integration test topup → purchase → escrow на docker-compose

## Runtime

Core-first требует поднятого Core:

```powershell
docker compose up -d billing-db users-db migrator api
python -m cerber_bot
```

Launcher: добавить компонент `core` (docker compose profile) — отдельная задача.

## Риски

| Риск | Митигация |
|------|-----------|
| Core недоступен | healthcheck при старте; retry + понятная ошибка пользователю |
| Расхождение при миграции | one-time script: sync local → Core по telegram_id |
| Idempotency | всегда передавать `operation_id` |
| Held UI без Core held field | сумма активных deals |

## Критерии готовности

- [x] Все money paths в core-first идут через `LedgerService`
- [x] Нет прямых `user.balance +=` в core-first services
- [ ] Integration test: topup → purchase → escrow → release на docker-compose
- [x] README и `.env.example` описывают Core-first как default для prod
