"""FastAPI приложение CEER Bot (Mini App сервер)."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

if TYPE_CHECKING:
    from ceer_bot.container import AppContainer


def create_web_app(container: "AppContainer") -> FastAPI:
    """Создаёт FastAPI приложение с подключёнными роутерами Mini App."""
    from ceer_bot.web.ttt_api import build_ttt_router
    from ceer_bot.web.durak_api import build_durak_router

    app = FastAPI(docs_url=None, redoc_url=None, title="CEER Mini App")

    # CORS для локальной разработки и Telegram WebView
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    webapps_dir = Path(__file__).resolve().parents[1] / "webapps"
    app.mount("/mini", StaticFiles(directory=str(webapps_dir), html=True), name="mini-webapps")

    app.include_router(build_ttt_router(container))
    app.include_router(build_durak_router(container))
    return app
