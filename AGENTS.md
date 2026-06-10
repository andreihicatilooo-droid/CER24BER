# AGENTS.md

## Cursor Cloud specific instructions

### Product overview

CERBER is a Python monorepo (Telegram shop bot + FastAPI web UI, optional CEER game bot, optional Go `cerber_core` billing API). Primary dev surface: **`cerber_bot`** on port **8088**.

### Standard commands (see also `README.md`)

| Task | Command |
|------|---------|
| Install deps | `python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"` |
| Config | `cp .env.example .env` then set `BOT_TOKEN` |
| Run shop bot + web | `.venv/bin/python -m cerber_bot` |
| Run tests | `.venv/bin/pytest tests/` |
| Launcher (multi-component) | `.venv/bin/python launcher.py start shop` |

### Running without a real Telegram token

`python -m cerber_bot` calls Telegram `delete_webhook` on startup and exits with `TelegramUnauthorizedError` if `BOT_TOKEN` is invalid. For web-only local work, start the FastAPI app with uvicorn using the same pattern as `tests/test_web_app.py` (build `AppContainer`, then `create_web_app`).

Authenticated pages like `/wallet` work without GiftAPI; `/store` requires `GIFTAPI_TOKEN` (or a configured catalog).

### Test suite caveats (current `main`)

Some files under `tests/` may fail collection due to unresolved merge markers or stale imports (`test_rukassa_client.py`, `test_catalog_service.py`, `test_giftapi_provider.py`, `test_core_admin_split.py`). The rest of `tests/` (72 tests) passes. `src/cerber_core/test_api.py` is a standalone script (needs `requests` + `pycryptodome`) — exclude it or install those packages separately.

### Optional services

- **CEER game bot**: set `CEER_BOT_TOKEN`, run `python -m ceer_bot` (web on **8089** when `CEER_WEB_URL` is set).
- **CERBER Core (Go)**: `cd src/cerber_core && docker compose up` (Postgres + API on **8080**). Native: `go run ./cmd/api` after DBs and migrations.
- **Full Docker stack**: root `docker compose up` (bots + core + tunnel).

### Linting

No dedicated linter is configured in `pyproject.toml`. Use `pytest` as the primary automated check.
