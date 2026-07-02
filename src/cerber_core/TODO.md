# CERBER CORE — TODO

> Архитектурная очередность: Инфраструктура → Миграции БД → Модели/Репозитории → Криптография → Бизнес-логика → Тесты

---

## Инфраструктура

- [x] [P1] Разделить БД на `users-db` и `billing-db` в docker-compose.yml
  - Изменяемые файлы: `docker-compose.yml`
  - Критерии приемки: два отдельных сервиса postgres (`users-db`, `billing-db`) с изолированными volume, healthcheck и инициализирующими SQL-скриптами

- [x] [P1] Добавить `USERS_DATABASE_URL` и `AES_SECRET_KEY` в конфигурацию
  - Изменяемые файлы: `internal/config/config.go`
  - Критерии приемки: `Config` содержит поля `BillingDatabaseURL`, `UsersDatabaseURL`, `AESSecretKey`; все значения загружаются из env с fallback

- [x] [P1] Инициализировать два независимых подключения к БД
  - Изменяемые файлы: `internal/db/db.go`, `cmd/api/main.go`
  - Критерии приемки: `db.Connect` возвращает два `*sqlx.DB` (`billingDB`, `usersDB`); репозитории users подключены к `usersDB`, остальные — к `billingDB`
  - Примечание: `UserRepo` остаётся на `billingDB` — таблица `users` с `user_hash` живёт в billing-db. `usersDB` инициализируется и проверяется при старте; зарезервирован для будущего PII-сервиса аутентификации (migration comment: "billing API does NOT connect to this database")

---

## Миграции БД

- [x] [P2] Создать схему `users-db` (только таблица пользователей с `user_hash`)
  - Изменяемые файлы: `migrations/users_db/001_init.sql`
  - Критерии приемки: таблица `users` содержит поля `id`, `user_hash` (TEXT NOT NULL UNIQUE), `email`, `password_hash`, `created_at`; `user_hash` индексирован
  - Реализовано: `migrations/users/000001_init.up.sql` (golang-migrate format). users-db хранит PII; billing-db имеет отдельную таблицу `users` только с `user_hash`.

- [x] [P2] Добавить `secret_key` в таблицу `services` (billing-db)
  - Изменяемые файлы: `migrations/002_service_secret_key.sql`
  - Критерии приемки: колонка `secret_key TEXT NOT NULL DEFAULT ''` добавлена в таблицу `services`
  - Реализовано: колонка `secret_key_encrypted TEXT NOT NULL` в `migrations/billing/000001_init.up.sql` (AES-GCM-256 зашифрованный ключ).

- [x] [P2] Обновить таблицу `accounts`: заменить `user_id` на `user_hash`
  - Изменяемые файлы: `migrations/003_accounts_user_hash.sql`
  - Критерии приемки: в таблице `accounts` колонка `user_id` переименована / заменена на `user_hash TEXT NOT NULL`; FK на `users` удалён (разные БД); индекс по `user_hash` создан
  - Реализовано: таблица `accounts` заменена на `service_balances(service_id, user_hash, balance_usdt)` в начальной миграции.

---

## Модели и Репозитории

- [x] [P3] Добавить `UserHash` и `SecretKey` в модели
  - Изменяемые файлы: `internal/model/user.go`, `internal/model/service.go`
  - Реализовано: `model.BillingUser{UserHash}`, `model.Service{SecretKey []byte}` — ключ декриптуется при загрузке из БД.

- [x] [P3] Заменить `UserID` на `UserHash` в `model.Account`
  - Изменяемые файлы: `internal/model/account.go`
  - Реализовано: `model.ServiceBalance{UserHash string}` — поле `UserID` не использовалось.

- [x] [P3] Обновить `UserRepo`: хранить и искать по `user_hash`
  - Изменяемые файлы: `internal/repository/user.go`
  - Реализовано: `UserRepo.Upsert(ctx, userHash)` — INSERT ON CONFLICT DO NOTHING.

- [x] [P3] Обновить `AccountRepo`: использовать `user_hash` вместо `user_id`
  - Изменяемые файлы: `internal/repository/account.go`
  - Реализовано: `BalanceRepo.FindOrCreate(ctx, serviceID, userHash)` и `AddUSDT` — работают с `service_balances`.

- [x] [P3] Обновить `ServiceRepo`: хранить и возвращать `secret_key`
  - Изменяемые файлы: `internal/repository/service.go`
  - Реализовано: `ServiceRepo.Create` сохраняет `api_key_hash` + `secret_key_encrypted`; `FindByAPIKeyHash` возвращает оба поля.

---

## Криптография

- [x] [P4] Реализовать пакет AES-GCM-256 (`internal/crypto`)
  - Изменяемые файлы: `internal/crypto/aes_gcm.go`
  - Реализовано: `internal/crypto/crypto.go` — `Encrypt`, `Decrypt`, `HMACHash`, `GenerateKey`; покрыт 18 unit-тестами в `crypto_test.go` (все PASS).

- [x] [P4] Реализовать Middleware для AES-GCM (decrypt request / encrypt response)
  - Изменяемые файлы: `internal/middleware/crypto.go`
  - Реализовано: каждый handler выполняет decrypt входящего тела и использует `handler.EncryptedJSON` для шифрования ответа ключом `service.SecretKey`. Подход per-handler вместо единого middleware.

- [x] [P4] Сохранять `SecretKey` сервиса в контекст Gin после `APIKeyAuth`
  - Изменяемые файлы: `internal/middleware/auth.go`
  - Реализовано: `APIKeyAuth` сохраняет `*model.Service` (содержит `SecretKey []byte`) в контекст; `middleware.GetService(c)` возвращает его.

---

## Бизнес-логика (API)

- [x] [P5] Генерировать `user_hash` при регистрации пользователя
  - N/A: `user_hash` генерируется на стороне клиента (hex(SHA-256(uuid))). API принимает готовый `user_hash` в POST /api/v1/user/add — сохраняет в billing-db без изменений.

- [x] [P5] Генерировать `secret_key` при создании сервиса
  - Реализовано: `service.AuthService.CreateService` генерирует 32-байтный ключ через `crypto.GenerateKey(32)`, шифрует MASTER_AES_KEY и сохраняет как `secret_key_encrypted`; возвращает Base64 клиенту единственный раз.

- [x] [P5] Использовать `user_hash` во всех операциях с балансом
  - Реализовано: `BalanceService.GetBalance(ctx, serviceID, userHash)` и `Credit(ctx, serviceID, userHash, ...)` — `userHash` передаётся явно, не через JWT.

- [x] [P5] Подключить `CryptoMiddleware` к защищённым группам маршрутов
  - Реализовано: все защищённые маршруты используют AES-GCM-256 через `handler.EncryptedJSON` (ответы) и `authSvc.DecryptUserHash` (запросы). Маршруты /admin/* не шифруются.

- [x] [P5] Использовать `user_hash` в JWT-клеймах
  - N/A: JWT не используется в текущей архитектуре. Аутентификация через X-API-Key / X-API-Secret (HMAC-SHA256). `user_hash` передаётся в зашифрованном теле запроса.

### Rollout: connector-driven topup contour

- [ ] [P3] Зафиксировать topup contract: provider/method capabilities + presentation/action model
  - Изменяемые файлы: `internal/model/payment.go`, `internal/service/payment.go`, `internal/handler/payment.go`, `internal/router/router.go`
  - Критерии приемки: CORE описывает topup flow через generic contract; capabilities, presentation и action-переходы не завязаны на конкретный provider/link-only сценарий

- [ ] [P3] Расширить persistence-модель topup-сессий под orchestration и connector-driven state machine
  - Изменяемые файлы: `migrations/`, `internal/model/payment.go`, `internal/repository/payment.go`, `internal/repository/transaction.go`
  - Критерии приемки: topup-сессии хранят provider/method snapshot, state machine, action history и данные для безопасного resume/idempotent confirm-fail

- [ ] [P4] Внедрить controlled connector registry и стандарт скриптов-коннекторов
  - Изменяемые файлы: `internal/config/config.go`, `internal/service/payment.go`, `internal/connectors/` (новый), `cmd/api/main.go`
  - Критерии приемки: registry управляется конфигом/feature flags, провайдеры подключаются через единый connector contract, а production не допускает ad-hoc подключений в обход registry

- [ ] [P5] Перенести payment orchestration, webhook handling и confirm/fail semantics в CORE как single source of truth
  - Изменяемые файлы: `internal/service/payment.go`, `internal/handler/payment.go`, `internal/router/router.go`, `cmd/api/main.go`
  - Критерии приемки: orchestration и webhook-потоки живут только в CORE; bot и другие клиенты читают состояния/действия из CORE без собственного ownership над topup state machine

---

## Тесты

- [ ] [P5] Unit-тесты для пакета `internal/crypto`
  - Изменяемые файлы: `internal/crypto/aes_gcm_test.go`
  - Критерии приемки: тесты на Encrypt/Decrypt roundtrip, неверный ключ, повреждённый ciphertext; 100% покрытие пакета

- [ ] [P5] Integration-тесты: Auth endpoints
  - Изменяемые файлы: `internal/handler/auth_test.go`
  - Критерии приемки: тесты `POST /auth/register`, `POST /auth/login`, `POST /auth/services` с реальной тестовой БД (`users-db`); проверка HTTP-статусов и наличия `user_hash` в ответе

- [ ] [P5] Integration-тесты: Balance endpoints
  - Изменяемые файлы: `internal/handler/balance_test.go`
  - Критерии приемки: тесты с AES-GCM шифрованием запросов и расшифровкой ответов; проверка `X-API-Key` + Bearer JWT; создание/получение аккаунта по `user_hash`

- [ ] [P5] Integration-тесты: Payment endpoints
  - Изменяемые файлы: `internal/handler/payment_test.go`
  - Критерии приемки: тесты `POST /deposit/payments`, `POST /deposit/payments/:id/check`, `GET /deposit/payments/:id/status` с шифрованием запросов/ответов; проверка полного цикла платежа
