"""Маршруты кошелька: баланс, история, пополнение."""

from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Request, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse

from cerber_bot.web.deps import build_fake_user, get_container, get_current_user_id, notify_user, templates

router = APIRouter(prefix="/wallet", tags=["wallet"])


@router.get("", response_class=HTMLResponse)
async def wallet_index(request: Request):
    user_id = get_current_user_id(request)
    container = get_container(request)
    wallet = await container.store_service.get_wallet_snapshot(user_id, limit=20)
    ps = container.payment_service
    return templates.TemplateResponse(request, "wallet/index.html", context={
        "wallet": wallet,
        "session": request.session,
        "show_nicepay": ps.is_nicepay_link_configured or ps.is_h2h_mode,
        "show_rukassa": ps.is_rukassa_mode,
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
            "show_nicepay": container.payment_service.is_nicepay_link_configured or container.payment_service.is_h2h_mode,
            "show_rukassa": container.payment_service.is_rukassa_mode,
        })

    try:
        link = await container.payment_service.create_top_up_link(
            build_fake_user(user_id, request.session), amount=parsed,
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
            "show_nicepay": container.payment_service.is_nicepay_link_configured or container.payment_service.is_h2h_mode,
            "show_rukassa": container.payment_service.is_rukassa_mode,
        })


@router.post("/topup/nicepay", response_class=HTMLResponse)
async def wallet_topup_nicepay(request: Request, amount: str = Form(...)):
    """Пополнение через NicePay (явный выбор при активных обоих провайдерах)."""
    user_id = get_current_user_id(request)
    container = get_container(request)

    try:
        parsed = Decimal(amount)
    except (InvalidOperation, ValueError):
        wallet = await container.store_service.get_wallet_snapshot(user_id)
        ps = container.payment_service
        return templates.TemplateResponse(request, "wallet/index.html", context={
            "wallet": wallet,
            "error": "Некорректная сумма",
            "session": request.session,
            "show_nicepay": ps.is_nicepay_link_configured or ps.is_h2h_mode,
            "show_rukassa": ps.is_rukassa_mode,
        })

    try:
        link = await container.payment_service.create_top_up_link(
            build_fake_user(user_id, request.session), amount=parsed, force_provider="nicepay",
        )
        await notify_user(
            request, user_id,
            f"💳 Создана ссылка NicePay через веб\n"
            f"Сумма: {link.amount:.2f} {link.currency}",
        )
        return templates.TemplateResponse(request, "wallet/topup.html", context={
            "link": link,
            "session": request.session,
        })
    except Exception as exc:
        wallet = await container.store_service.get_wallet_snapshot(user_id)
        ps = container.payment_service
        return templates.TemplateResponse(request, "wallet/index.html", context={
            "wallet": wallet,
            "error": str(exc),
            "session": request.session,
            "show_nicepay": ps.is_nicepay_link_configured or ps.is_h2h_mode,
            "show_rukassa": ps.is_rukassa_mode,
        })


@router.post("/topup/rukassa", response_class=HTMLResponse)
async def wallet_topup_rukassa(request: Request, amount: str = Form(...)):
    """Пополнение через Rukassa (явный выбор при активных обоих провайдерах)."""
    user_id = get_current_user_id(request)
    container = get_container(request)

    try:
        parsed = Decimal(amount)
    except (InvalidOperation, ValueError):
        wallet = await container.store_service.get_wallet_snapshot(user_id)
        ps = container.payment_service
        return templates.TemplateResponse(request, "wallet/index.html", context={
            "wallet": wallet,
            "error": "Некорректная сумма",
            "session": request.session,
            "show_nicepay": ps.is_nicepay_link_configured or ps.is_h2h_mode,
            "show_rukassa": ps.is_rukassa_mode,
        })

    try:
        # force_provider не передаём — Rukassa выбирается по умолчанию если активна
        link = await container.payment_service.create_top_up_link(
            build_fake_user(user_id, request.session), amount=parsed,
        )
        await notify_user(
            request, user_id,
            f"💰 Создана ссылка Rukassa через веб\n"
            f"Сумма: {link.amount:.2f} {link.currency}",
        )
        return templates.TemplateResponse(request, "wallet/topup.html", context={
            "link": link,
            "session": request.session,
        })
    except Exception as exc:
        wallet = await container.store_service.get_wallet_snapshot(user_id)
        ps = container.payment_service
        return templates.TemplateResponse(request, "wallet/index.html", context={
            "wallet": wallet,
            "error": str(exc),
            "session": request.session,
            "show_nicepay": ps.is_nicepay_link_configured or ps.is_h2h_mode,
            "show_rukassa": ps.is_rukassa_mode,
        })
