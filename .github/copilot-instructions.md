# Руководство по проекту — CERBER Bot

## Обзор

Асинхронный Telegram-бот магазин со сделками (escrow), мультивалютным кошельком, интеграцией GiftAPI, платежами NicePay и веб-панелью на FastAPI. Русскоязычный пользовательский интерфейс и документация.

## Архитектура

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
python -m cerber_bot

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
- **AI contour role matrix**: `CERBER` is the universal user-facing companion and may answer itself or route directly without automatically involving `CERBER Router`. `CERBER Router` is a narrow dispatcher for explicit agent-selection questions only. `CERBER Discovery` turns raw ideas into a brief plus directions. `CERBER Planner` stops at plan/TODO before implementation. `CERBER Executor` executes only an already clear task. `CERBER Architect`, `CERBER Interface`, and `CERBER Cleanup` own architectural choices, UI/text flows, and cleanup slices respectively.
- **AI contour handoff policy**: `CERBER` routes straight to the next role when it is obvious. `CERBER Router` is used only when the routing question itself is the task or trigger overlap must be resolved. `CERBER Discovery` ends with a recommended next agent instead of planning or coding. `CERBER Planner` hands off only after a plan/TODO is agreed. Unresolved architecture goes through `CERBER Architect`; UI/text-only slices go through `CERBER Interface`; debt-cleanup slices go through `CERBER Cleanup`; implementation of a clear task goes to `CERBER Executor`.
- **AI contour tool policy**: `CERBER` stays on the minimal toolset `read + search + agent`; `CERBER Discovery` stays on `read + search` only. Do not widen these toolsets without a specific task proving the current scope is insufficient.
- **AI contour skill policy**: there are no always-on skills for `CERBER` or `CERBER Discovery`. `idea-to-brief` is the optional shared ideation workflow for raw ideas and vague product requests; `plan-to-todo` is conditionally mandatory only after `CERBER Planner` has already produced an approved plan that must be written into a TODO contour; `sync-ai-contour` is the reusable maintenance workflow for syncing neighboring discovery surfaces and touched operator-docs touchpoints inside the real AI change-set; `smoke-ai-customizations` is the reusable close-out workflow for repeatable file/scenario smoke-checks over the touched AI surfaces after those edits.
- **Skill availability**: when these skills are present in `.github/skills/`, keep them narrow: `idea-to-brief` for ideation, `plan-to-todo` for Planner → TODO, `sync-ai-contour` for surface sync, `smoke-ai-customizations` for smoke-checks. Agents should remain functional without pretending that any of these skills is always-on, and prompts/hooks should not be pre-emptively used in place of the matching skill.
- **Workspace prompt policy**: workspace prompts in `.github/prompts/` are thin operator entry points, not a new always-on instruction layer. `route-request` enters `CERBER Router`; `brief-idea` enters the shared ideation flow via `CERBER Discovery`; `sync-ai-policy` enters the `sync-ai-contour` maintenance workflow via `CERBER`; `smoke-ai-customizations` enters the repeatable close-out smoke-check workflow via `CERBER`. Keep prompts single-task focused, with distinct `description` and short `argument-hint`, do not duplicate full agent or skill instructions inside them, and do not let prompts replace the underlying sync/smoke workflows.
- **AI customization hook policy**: workspace hooks are allowed only as a narrow guard/reminder layer for edits inside `.github/agents/`, `.github/skills/`, `.github/prompts/`, `.github/hooks/`, `.github/instructions/`, and `.github/copilot-instructions.md`. Keep the hook contour to a targeted `PreToolUse` guard and a short `PostToolUse` reminder; do not attach hooks to every prompt/session and do not run long validation inside hooks.
- **AI contour sync policy**: when a change touches agent, skill, prompt, hook, instruction, or contour-policy discovery/routing, update neighboring discovery surfaces in the same change — relevant `description`, `argument-hint`, role boundaries, handoff notes, and related TODO/policy/docs touchpoints. Do not patch one contour file in isolation if it changes how the contour is found or routed.
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
