# Project Guidelines — CERBER Bot

## Overview

Async Telegram bot storefront with escrow deals, multi-currency wallet, GiftAPI integration, NicePay payments, and a FastAPI web dashboard. Russian-language UI and documentation.

## Architecture

```
src/cerber_bot/
├── main.py / container.py   # Bootstrap & DI (AppContainer dataclass)
├── config.py                # Single Settings(BaseSettings) from .env
├── texts.py                 # All user-facing strings (Russian)
├── handlers/                # aiogram 3 Routers (build_*_router() factories)
├── keyboards/               # InlineKeyboardMarkup builders
├── services/                # Business logic, async, raise custom exceptions
├── db/
│   ├── models.py            # SQLAlchemy 2.0 Mapped[] models
│   ├── session.py           # Engine + session factory + init_database()
│   └── repositories/        # Repository pattern, receive AsyncSession
├── integrations/
│   ├── giftapi.py           # GiftAPI client (HMAC-SHA256 signing)
│   ├── nicepay.py           # NicePay client (payment links + webhook verify)
│   ├── providers/           # CatalogProvider implementations
│   └── registry.py          # build_providers() based on Settings flags
└── web/                     # FastAPI app, Jinja2 templates, Telegram Login auth
```

**DI**: Hand-written `AppContainer` dataclass with `build()` classmethod — no external DI framework. Container is passed to all router factories.

**Entry point**: `python -m cerber_bot` → `__main__.py` → `main.run()`.

## Code Style

- **Python ≥ 3.11**, use `from __future__ import annotations` for forward refs.
- **Docstrings and comments in Russian** — match existing modules.
- **Immutable DTOs**: `@dataclass(slots=True, frozen=True)` for service-layer data objects.
- **SQLAlchemy 2.0**: Use `Mapped[]` / `mapped_column()` syntax, never classic `Column()`.
- **Async everywhere**: `async def`, `async with session_factory() as session:`, `await`.
- **Custom exceptions** per service (e.g., `StoreServiceError`, `InsufficientBalanceError`) — handlers catch and translate to user-friendly Telegram messages.
- **User-facing text** goes in `texts.py`, not inline in handlers.

## Conventions

### Handlers

- Each handler module exports `build_*_router(container: AppContainer) -> Router`.
- Use aiogram 3 callback-query and FSM patterns for multi-step flows.
- Keyboard callback data uses short prefixes (`storep`, `storew`, etc.) with JSON-encoded payloads.

### Services

- Receive dependencies (`session_factory`, `http_client`, external clients) in `__init__`.
- Return domain objects (dataclasses or ORM models), never raw dicts.
- Repositories handle DB queries; services handle orchestration and business rules.
- Callers (services) manage session lifecycle and `commit()` — repositories do not commit.

### Integrations / Providers

- New catalog sources subclass `CatalogProvider` (or `BaseHttpCatalogProvider`) and implement `fetch_products()`.
- Register new providers in `integrations/registry.py` → `build_providers()`.
- See [EXTENDING.md](../EXTENDING.md) for step-by-step guides on adding providers, payment gateways, handlers, and models.

### Web

- FastAPI routes in `web/routes/`, each module creates an `APIRouter`.
- Auth via Telegram Login Widget; session stored in signed cookie.
- Templates in `web/templates/` extend `base.html`.

## Build and Test

```powershell
# Install (editable)
pip install -e ".[dev]"

# Run bot
python -m cerber_bot          # or .\start.ps1

# Run tests
python -m pytest tests/       # asyncio_mode = "auto", pythonpath = ["src"]
```

Tests use temporary SQLite DBs (`tmp_path`), stub clients (e.g., `StubNicePayClient`), and pytest-asyncio auto mode.

## Pitfalls

- **Catalog refresh**: Call only `store_service.refresh_catalog()` — never double-refresh via `catalog_service` directly, or GiftAPI returns 429 and Telegram callback answers expire.
- **Database migrations**: No Alembic — `init_database()` uses `create_all()` and `apply_lightweight_migrations()` for SQLite ALTER TABLE. Adding columns requires updating the lightweight migration function.
- **.env credentials**: Never commit real tokens. Use `.env.example` with placeholders only.
- **Webhook fallback**: Bot startup tries webhook reset 3× before falling back to polling — be aware when testing locally.

## AI Assistant Behavior

- **Language**: Always respond in Russian. Code, identifiers, and file paths remain in their original language.
- **Commit summary**: After any file edits, append a commit message block at the very end of the response:

```
---
📝 **Commit:**
тип(scope): краткое описание на русском

- деталь 1
- деталь 2
```

Commit types: `feat`, `fix`, `refactor`, `chore`, `docs`, `style`, `test`.
Example: `feat(handlers): добавить кнопку «Избранное» в главное меню`
