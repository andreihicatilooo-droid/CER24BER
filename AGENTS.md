# AGENTS.md

## Cursor Cloud specific instructions

### Product overview

CERBER is a Python monorepo (Telegram commerce + games + optional Go billing). Primary dev surface is **CERBER Shop** (`cerber_bot`): Telegram bot + FastAPI web UI on port **8088**.

### System prerequisites (one-time on fresh Ubuntu VM)

`python3-venv` is required to create `.venv`:

```bash
sudo apt-get install -y python3.12-venv
```

Go **1.22+** is pre-installed and used only for `src/cerber_core` (optional billing microservice).

### Python setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # set BOT_TOKEN at minimum
```

### Running services

| Service | Command | Port | Notes |
|---------|---------|------|-------|
| Shop bot + web | `python -m cerber_bot` | 8088 | Needs valid `BOT_TOKEN`; crashes on invalid token during webhook reset |
| Launcher supervisor | `python launcher.py serve` | 8088 (+ others) | `python launcher.py doctor` checks readiness |
| CEER games bot | `python -m ceer_bot` | 8089 | Needs `CEER_BOT_TOKEN` |
| Admin bot | `python -m cerber_admin` | — | Needs `ADMIN_BOT_TOKEN` |
| CERBER Core (Go) | `cd src/cerber_core && go run ./cmd/api` | 8080 | Needs PostgreSQL via `docker compose` in repo root |

**Web-only dev (no Telegram):** `python -m cerber_bot` requires a real `BOT_TOKEN`. For local UI work without Telegram, run uvicorn against `create_web_app()` (see `/tmp/run_cerber_web.py` pattern used during env verification).

### Testing

```bash
source .venv/bin/activate
pytest tests/   # 4 modules fail collection due to removed CatalogProvider in integrations/base.py
go test ./...   # from src/cerber_core
```

Known failing test modules (pre-existing import errors): `test_catalog_service.py`, `test_core_admin_split.py`, `test_giftapi_provider.py`, `test_rukassa_client.py`. The remaining **72 tests pass**.

### Lint

No ruff/mypy/eslint configured. Use `go build ./...` in `src/cerber_core` as the Go compile check.

### Local web auth without Telegram widget

Sign a Telegram Login Widget callback with your `BOT_TOKEN` HMAC and hit `GET /login/callback`. `/wallet` works without GiftAPI; `/store` requires `GIFTAPI_TOKEN` + `GIFTAPI_SECRET`.

### Optional Docker stack

Full stack (bot + PostgreSQL + core API): configure passwords in `.env` per `docker-compose.yml`, then `docker compose up -d`.
