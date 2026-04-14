"""Зависимости FastAPI для CERBER Web.

Предоставляет доступ к контейнеру, текущему пользователю и шаблонам.
"""

import hashlib
import hmac
import json
import logging
from pathlib import Path
from urllib.parse import parse_qs

from fastapi import Request, HTTPException
from fastapi.templating import Jinja2Templates

from cerber_bot.container import AppContainer

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

logger = logging.getLogger(__name__)


def get_container(request: Request) -> AppContainer:
    return request.app.state.container


def get_current_user_id(request: Request) -> int:
    """Вернуть telegram_id из сессии или 401."""
    user_id = request.session.get("telegram_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Не авторизован")
    return int(user_id)


def get_optional_user_id(request: Request) -> int | None:
    """Вернуть telegram_id или None."""
    user_id = request.session.get("telegram_id")
    return int(user_id) if user_id else None


def verify_telegram_login(data: dict, bot_token: str) -> bool:
    """Проверить подпись Telegram Login Widget."""
    check_hash = data.get("hash", "")
    filtered = {k: v for k, v in data.items() if k != "hash" and v}
    check_string = "\n".join(f"{k}={filtered[k]}" for k in sorted(filtered))
    secret_key = hashlib.sha256(bot_token.encode()).digest()
    computed = hmac.new(secret_key, check_string.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(computed, check_hash)


def verify_webapp_init_data(init_data: str, bot_token: str) -> dict | None:
    """Проверить подпись Telegram Mini App initData.

    Возвращает распарсенные данные при успехе, None при ошибке.
    https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
    """
    parsed = {k: v[0] for k, v in parse_qs(init_data, keep_blank_values=True).items()}
    received_hash = parsed.pop("hash", "")
    if not received_hash:
        return None

    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(calculated_hash, received_hash):
        return None

    # Распарсить user JSON
    user_data = parsed.get("user")
    if user_data:
        parsed["user"] = json.loads(user_data)

    return parsed


def get_bot(request: Request):
    """Вернуть экземпляр aiogram Bot из app state или None."""
    return getattr(request.app.state, "bot", None)


async def notify_user(request: Request, user_id: int, text: str) -> None:
    """Отправить уведомление пользователю через Telegram бота.

    Не выбрасывает исключений — ошибки логируются.
    """
    bot = get_bot(request)
    if bot is None:
        return
    try:
        await bot.send_message(user_id, text)
    except Exception as exc:
        logger.warning("Failed to send notification to %s: %s", user_id, exc)
