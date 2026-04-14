"""Маршруты кошелька: баланс, история, пополнение."""

from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Request, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse

from cerber_bot.web.deps import get_container, get_current_user_id, notify_user, templates

router = APIRouter(prefix="/wallet", tags=["wallet"])


@router.get("", response_class=HTMLResponse)
async def wallet_index(request: Request):
    user_id = get_current_user_id(request)
    container = get_container(request)
    wallet = await container.store_service.get_wallet_snapshot(user_id, limit=20)
    return templates.TemplateResponse(request, "wallet/index.html", context={
        "wallet": wallet,
        "session": request.session,
    })


@router.post("/topup", response_class=HTMLResponse)
async def wallet_topup(request: Request, amount: str = Form(...)):
    user_id = get_current_user_id(request)
    container = get_container(request)

    try:
        parsed = Decimal(amount)
    except (InvalidOperation, ValueError):
        wallet = await container.store_service.get_wallet_snapshot(user_id)
        return templates.TemplateResponse(request, "wallet/index.html", context={
            "wallet": wallet,
            "error": "Некорректная сумма",
            "session": request.session,
        })

    class FakeUser:
        def __init__(self, tid, session):
            self.id = tid
            self.username = session.get("username")
            self.first_name = session.get("first_name", "")
            self.last_name = None
            self.language_code = "ru"
            self.is_bot = False

    try:
        link = await container.payment_service.create_top_up_link(
            FakeUser(user_id, request.session), amount=parsed,
        )
        await notify_user(
            request, user_id,
            f"💳 Создана ссылка на пополнение через веб\n"
            f"Сумма: {link.amount:.2f} {link.currency}",
        )
        return templates.TemplateResponse(request, "wallet/topup.html", context={
            "link": link,
            "session": request.session,
        })
    except Exception as exc:
        wallet = await container.store_service.get_wallet_snapshot(user_id)
        return templates.TemplateResponse(request, "wallet/index.html", context={
            "wallet": wallet,
            "error": str(exc),
            "session": request.session,
        })
