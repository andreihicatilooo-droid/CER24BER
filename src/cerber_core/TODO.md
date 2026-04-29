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

- [ ] [P1] Инициализировать два независимых подключения к БД
  - Изменяемые файлы: `internal/db/db.go`, `cmd/api/main.go`
  - Критерии приемки: `db.Connect` возвращает два `*sqlx.DB` (`billingDB`, `usersDB`); репозитории users подключены к `usersDB`, остальные — к `billingDB`

---

## Миграции БД

- [ ] [P2] Создать схему `users-db` (только таблица пользователей с `user_hash`)
  - Изменяемые файлы: `migrations/users_db/001_init.sql`
  - Критерии приемки: таблица `users` содержит поля `id`, `user_hash` (TEXT NOT NULL UNIQUE), `email`, `password_hash`, `created_at`; `user_hash` индексирован

- [ ] [P2] Добавить `secret_key` в таблицу `services` (billing-db)
  - Изменяемые файлы: `migrations/002_service_secret_key.sql`
  - Критерии приемки: колонка `secret_key TEXT NOT NULL DEFAULT ''` добавлена в таблицу `services`

- [ ] [P2] Обновить таблицу `accounts`: заменить `user_id` на `user_hash`
  - Изменяемые файлы: `migrations/003_accounts_user_hash.sql`
  - Критерии приемки: в таблице `accounts` колонка `user_id` переименована / заменена на `user_hash TEXT NOT NULL`; FK на `users` удалён (разные БД); индекс по `user_hash` создан

---

## Модели и Репозитории

- [ ] [P3] Добавить `UserHash` и `SecretKey` в модели
  - Изменяемые файлы: `internal/model/user.go`, `internal/model/service.go`
  - Критерии приемки: `model.User` содержит поле `UserHash string \`db:"user_hash"\``; `model.Service` содержит поле `SecretKey string \`db:"secret_key" json:"-"\``

- [ ] [P3] Заменить `UserID` на `UserHash` в `model.Account`
  - Изменяемые файлы: `internal/model/account.go`
  - Критерии приемки: поле `UserID` заменено на `UserHash string \`db:"user_hash" json:"user_hash"\``

- [ ] [P3] Обновить `UserRepo`: хранить и искать по `user_hash`
  - Изменяемые файлы: `internal/repository/user.go`
  - Критерии приемки: методы `Create` сохраняют `user_hash`; добавлен метод `FindByHash(ctx, userHash) (*model.User, error)`

- [ ] [P3] Обновить `AccountRepo`: использовать `user_hash` вместо `user_id`
  - Изменяемые файлы: `internal/repository/account.go`
  - Критерии приемки: `FindByUserID` переименован в `FindByUserHash`; SQL-запросы используют колонку `user_hash`

- [ ] [P3] Обновить `ServiceRepo`: хранить и возвращать `secret_key`
  - Изменяемые файлы: `internal/repository/service.go`
  - Критерии приемки: `Create` и `FindByAPIKey` включают поле `secret_key`

---

## Криптография

- [ ] [P4] Реализовать пакет AES-GCM-256 (`internal/crypto`)
  - Изменяемые файлы: `internal/crypto/aes_gcm.go`
  - Критерии приемки: экспортированные функции `Encrypt(key []byte, plaintext []byte) ([]byte, error)` и `Decrypt(key []byte, ciphertext []byte) ([]byte, error)` реализованы через `crypto/aes` + `cipher.NewGCM`; nonce генерируется через `crypto/rand`; покрыты unit-тестами

- [ ] [P4] Реализовать Middleware для AES-GCM (decrypt request / encrypt response)
  - Изменяемые файлы: `internal/middleware/crypto.go`
  - Критерии приемки: `CryptoMiddleware(serviceRepo)` — gin.HandlerFunc: (1) читает тело запроса, расшифровывает AES-GCM-256 ключом `service.SecretKey`; (2) подменяет `c.Request.Body` расшифрованными данными; (3) перехватывает ответ через `gin.ResponseWriter`, шифрует тело и отдаёт зашифрованный ответ; применяется только к маршрутам с `APIKeyAuth`

- [ ] [P4] Сохранять `SecretKey` сервиса в контекст Gin после `APIKeyAuth`
  - Изменяемые файлы: `internal/middleware/auth.go`
  - Критерии приемки: после успешной проверки API-ключа в контекст добавляется `service_secret_key`; добавлена вспомогательная функция `ServiceSecretKey(c *gin.Context) []byte`

---

## Бизнес-логика (API)

- [ ] [P5] Генерировать `user_hash` при регистрации пользователя
  - Изменяемые файлы: `internal/service/auth.go`
  - Критерии приемки: `RegisterUser` генерирует `user_hash = hex(SHA-256(user_id + salt))`; сохраняет в `users-db`; возвращает `user_hash` вместо `id` во внешних ответах

- [ ] [P5] Генерировать `secret_key` при создании сервиса
  - Изменяемые файлы: `internal/service/auth.go`, `internal/handler/auth.go`
  - Критерии приемки: `CreateService` генерирует 32-байтный `secret_key` через `crypto/rand`; сохраняет в `services`; возвращает клиенту единственный раз в открытом виде

- [ ] [P5] Использовать `user_hash` во всех операциях с балансом
  - Изменяемые файлы: `internal/service/balance.go`, `internal/handler/balance.go`
  - Критерии приемки: `CreateAccount`, `GetBalancesByUser` принимают и используют `user_hash` из контекста JWT (`claims.UserHash`); `model.Account.UserHash` передаётся в репозиторий

- [ ] [P5] Подключить `CryptoMiddleware` к защищённым группам маршрутов
  - Изменяемые файлы: `internal/router/router.go`
  - Критерии приемки: `CryptoMiddleware` применён к группам `/balance` и `/deposit` после `APIKeyAuth`; маршруты `/auth/register` и `/auth/login` остаются без шифрования

- [ ] [P5] Использовать `user_hash` в JWT-клеймах
  - Изменяемые файлы: `internal/service/jwt.go`, `internal/middleware/auth.go`
  - Критерии приемки: `Claims` содержит `UserHash string`; `JWTAuth` middleware сохраняет `user_hash` в контекст; все обращения к `middleware.UserID` заменены на `middleware.UserHash`

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
