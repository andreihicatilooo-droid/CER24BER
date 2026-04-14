"""FastAPI-приложение CERBER Web.

Создаёт приложение, подключает маршруты, шаблоны и middleware.
"""

from pathlib import Path

from aiogram import Bot
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from cerber_bot.container import AppContainer
from cerber_bot.web.routes import auth, store, wallet, orders, deals, profile

WEB_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = WEB_DIR / "templates"
STATIC_DIR = WEB_DIR / "static"


def create_web_app(container: AppContainer, bot: Bot | None = None) -> FastAPI:
    """Создать и настроить FastAPI-приложение."""
    app = FastAPI(title="CERBER Store", docs_url=None, redoc_url=None)

    app.add_middleware(
        SessionMiddleware,
        secret_key=container.settings.bot_token,
        session_cookie="cerber_session",
        max_age=86400 * 7,
    )

    app.state.container = container
    app.state.bot = bot

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.exception_handler(401)
    async def auth_redirect(request: Request, exc):
        return RedirectResponse("/", status_code=302)

    app.include_router(auth.router)
    app.include_router(store.router)
    app.include_router(wallet.router)
    app.include_router(orders.router)
    app.include_router(deals.router)
    app.include_router(profile.router)

    return app
