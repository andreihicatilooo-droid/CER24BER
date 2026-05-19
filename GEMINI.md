# CERBER Workspace — Gemini Code Assist Instructions

You are an expert AI software engineering assistant working on the **CERBER** project.

## 🏗️ Project Overview
This repository contains two main components:
1. **`src/cerber_core/`**: Go/PostgreSQL billing microservice.
2. **`src/cerber_bot/`**: Python/aiogram3 Telegram bot.

---

## 🟢 CERBER CORE (Go)
**Stack**: Go 1.22, Gin, sqlx, PostgreSQL 16.

- **DB Isolation**: Strict separation between `users-db` (users, auth) and `billing-db` (accounts, transactions, payments). Never cross-connect them.
- **Security & Crypto**: 
  - API Auth via `X-API-Key` + `X-API-Secret` headers.
  - **All API request/response bodies** must be **AES-GCM-256** decrypted/encrypted via `internal/crypto` (except `/auth/register` and `/auth/login`).
- **Identity**: External APIs use `user_hash` (hex SHA-256). Never expose raw UUIDs (`user_id`).
- **Code Standards**:
  - **Transactions**: Use `sql.LevelSerializable` + `SELECT ... FOR UPDATE` for financial transactions.
  - **Error handling**: `fmt.Errorf("...: %w", err)`. Never swallow errors.
  - **DI**: Inject dependencies via constructors. No global variables.
  - **NO STUBS**: No `panic("not implemented")` or `// TODO` in generated code. Provide complete implementations.
  - **Docs**: Mandatory `swaggo/swag` annotations for every handler.
  - **Tests**: Unit tests are mandatory for all generated files (Happy path, error paths).

---

## 🐍 CERBER BOT (Python)
**Stack**: Python 3.11+, aiogram 3, FastAPI (Jinja2 for Web UI), SQLAlchemy 2.0.

- **Code Style**: 
  - Use `from __future__ import annotations`.
  - SQLAlchemy 2.0 `Mapped[]` syntax only (no classic `Column()`).
  - Async everywhere (`async def`, `await`, `AsyncSession`).
  - Immutable DTOs via `@dataclass(slots=True, frozen=True)`.
- **Architecture**:
  - Custom DI using `AppContainer` (no external DI frameworks).
  - Services handle business rules and session lifecycle (`commit`). Repositories handle DB queries only.
  - **Migrations**: No Alembic. Use `apply_lightweight_migrations()` in `db/session.py` for SQLite schema changes.
- **Integrations**:
  - **GiftAPI**: Uses float USD. Pass `meta.next_cursor` for pagination. HMAC-SHA256 signature required.
  - **NicePay**: Uses integer minor units.
- **Language & Conventions**:
  - **Russian** is required for user-facing texts (in `texts.py`), docstrings, and AI responses.
  - Code, variables, and paths remain in English.

---

## 📚 API & Documentation References
- Always consult `doc/api/*.json` (e.g., `giftapi-hint.json`, `nicepayapi.json`, `cerber-core-hint.json`) for exact external service schemas and authentication formulas before writing integration code.
- See `EXTENDING.md` for guides on adding new providers, handlers, or models.

---

## ⚠️ Critical Constraints (No Improvisation)
- If DB schema, migrations, or business logic is ambiguous — **stop and ask**. Do not invent behavior.
- Do not write partial implementations.
- Do not modify files outside the explicit task scope unless fixing a compile error caused by your changes.

---

## 📝 Commit Standards (Conventional Commits)

When outputting commit messages, adhere to these formats:

**For `cerber_core` (English):**
```
<type>(cerber-core): <short description>

- <change 1>
```

**For `cerber_bot` (Russian):**
Append this block at the end of your response after editing files:
```
---
📝 **Commit:**
<type>(<scope>): <краткое описание на русском>

- <деталь 1>
```
Types: `feat`, `fix`, `refactor`, `test`, `chore`, `docs`, `migrate`.