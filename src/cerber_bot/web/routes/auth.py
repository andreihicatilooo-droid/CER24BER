"""Маршруты авторизации через Telegram Login Widget и Mini App."""

import time

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from cerber_bot.web.deps import get_container, get_optional_user_id, templates, verify_telegram_login, verify_webapp_init_data

router = APIRouter(tags=["auth"])


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    user_id = get_optional_user_id(request)
    if user_id:
        return RedirectResponse("/store", status_code=302)
    container = get_container(request)
    return templates.TemplateResponse(request, "login.html", context={
        "bot_username": container.settings.bot_username or "",
    })


@router.get("/login/callback")
async def telegram_callback(request: Request):
    container = get_container(request)
    data = dict(request.query_params)

    if not verify_telegram_login(data, container.settings.bot_token):
        return templates.TemplateResponse(request, "login.html", context={
            "error": "Ошибка проверки авторизации Telegram",
            "bot_username": container.settings.bot_username or "",
        }, status_code=403)

    auth_date = int(data.get("auth_date", 0))
    if abs(time.time() - auth_date) > 86400:
        return templates.TemplateResponse(request, "login.html", context={
            "error": "Срок авторизации истёк. Попробуйте снова.",
            "bot_username": container.settings.bot_username or "",
        }, status_code=403)

    telegram_id = int(data["id"])
    first_name = data.get("first_name", "")
    username = data.get("username", "")
    photo_url = data.get("photo_url", "")

    # Ensure user exists in DB
    user = await container.store_service.get_wallet_snapshot(telegram_id)

    request.session["telegram_id"] = telegram_id
    request.session["first_name"] = first_name
    request.session["username"] = username
    request.session["photo_url"] = photo_url

    return RedirectResponse("/store", status_code=302)


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/", status_code=302)


@router.post("/auth/telegram-webapp")
async def telegram_webapp_auth(request: Request, init_data: str = Form(...)):
    """Авторизация через Telegram Mini App initData."""
    container = get_container(request)
    data = verify_webapp_init_data(init_data, container.settings.bot_token)

    if data is None:
        return JSONResponse({"ok": False, "error": "Invalid signature"}, status_code=403)

    auth_date = int(data.get("auth_date", 0))
    if abs(time.time() - auth_date) > 86400:
        return JSONResponse({"ok": False, "error": "Expired"}, status_code=403)

    user = data.get("user", {})
    telegram_id = user.get("id")
    if not telegram_id:
        return JSONResponse({"ok": False, "error": "No user"}, status_code=400)

    telegram_id = int(telegram_id)

    # Ensure user exists in DB
    await container.store_service.get_wallet_snapshot(telegram_id)

    # Сессия уже авторизована — не перенаправлять
    if request.session.get("telegram_id") == telegram_id:
        return JSONResponse({"ok": True, "redirect": ""})

    request.session["telegram_id"] = telegram_id
    request.session["first_name"] = user.get("first_name", "")
    request.session["username"] = user.get("username", "")
    request.session["photo_url"] = user.get("photo_url", "")

    return JSONResponse({"ok": True, "redirect": "/store"})
