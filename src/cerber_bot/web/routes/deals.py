"""Маршруты гарант-сделок: дашборд, список, создание, действия, чат, вывод."""

from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Request, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse

from cerber_bot.web.deps import build_fake_user, get_container, get_current_user_id, notify_user, templates

router = APIRouter(prefix="/deals", tags=["deals"])


@router.get("", response_class=HTMLResponse)
async def deals_dashboard(request: Request):
    user_id = get_current_user_id(request)
    container = get_container(request)
    dashboard = await container.deal_service.get_dashboard(user_id)
    cards, page_info = await container.deal_service.get_deals_page(user_id, page=1, per_page=10)
    return templates.TemplateResponse(request, "deals/index.html", context={
        "dashboard": dashboard,
        "deals": cards,
        "page_info": page_info,
        "session": request.session,
    })


@router.get("/list", response_class=HTMLResponse)
async def deals_list(request: Request, page: int = Query(1, ge=1)):
    user_id = get_current_user_id(request)
    container = get_container(request)
    cards, page_info = await container.deal_service.get_deals_page(user_id, page=page, per_page=10)
    return templates.TemplateResponse(request, "deals/list.html", context={
        "deals": cards,
        "page_info": page_info,
        "session": request.session,
    })


@router.get("/create", response_class=HTMLResponse)
async def deal_create_form(request: Request):
    get_current_user_id(request)
    container = get_container(request)
    return templates.TemplateResponse(request, "deals/create.html", context={
        "networks": container.deal_service.withdrawal_networks,
        "session": request.session,
    })


@router.post("/create", response_class=HTMLResponse)
async def deal_create(
    request: Request,
    partner: str = Form(...),
    amount: str = Form(...),
    terms: str = Form(...),
):
    user_id = get_current_user_id(request)
    container = get_container(request)

    try:
        parsed_amount = Decimal(amount)
        result = await container.deal_service.create_deal_request(
            build_fake_user(user_id, request.session),
            seller_identifier=partner.strip(),
            amount=parsed_amount,
            terms=terms.strip(),
        )
        await notify_user(
            request, user_id,
            f"🤝 Сделка #{result.deal.deal_id} создана через веб\n"
            f"Сумма: {parsed_amount:.2f}\nУсловия: {terms.strip()[:100]}",
        )
        return RedirectResponse(f"/deals/{result.deal.deal_id}", status_code=302)
    except Exception as exc:
        return templates.TemplateResponse(request, "deals/create.html", context={
            "error": str(exc),
            "networks": container.deal_service.withdrawal_networks,
            "session": request.session,
        })


# ── Вывод USDT ──────────────────────────────────────────────

@router.get("/withdrawal/create", response_class=HTMLResponse)
async def withdrawal_form(request: Request):
    user_id = get_current_user_id(request)
    container = get_container(request)
    wallet = await container.store_service.get_wallet_snapshot(user_id)
    return templates.TemplateResponse(request, "deals/withdrawal.html", context={
        "wallet": wallet,
        "networks": container.deal_service.withdrawal_networks,
        "min_amount": container.deal_service.withdrawal_min_amount_usdt,
        "session": request.session,
    })


@router.post("/withdrawal/create", response_class=HTMLResponse)
async def withdrawal_create(
    request: Request,
    amount: str = Form(...),
    network: str = Form(...),
    address: str = Form(...),
):
    user_id = get_current_user_id(request)
    container = get_container(request)

    try:
        parsed = Decimal(amount)
        result = await container.deal_service.create_withdrawal_request(
            build_fake_user(user_id, request.session),
            amount_usdt=parsed,
            network=network,
            address=address.strip(),
        )
        return RedirectResponse("/deals", status_code=302)
    except Exception as exc:
        wallet = await container.store_service.get_wallet_snapshot(user_id)
        return templates.TemplateResponse(request, "deals/withdrawal.html", context={
            "wallet": wallet,
            "networks": container.deal_service.withdrawal_networks,
            "min_amount": container.deal_service.withdrawal_min_amount_usdt,
            "error": str(exc),
            "session": request.session,
        })


# ── Сделка по ID ────────────────────────────────────────────

@router.get("/{deal_id}", response_class=HTMLResponse)
async def deal_detail(request: Request, deal_id: int):
    user_id = get_current_user_id(request)
    container = get_container(request)
    deal = await container.deal_service.get_deal_view(user_id, deal_id)
    if deal is None:
        return templates.TemplateResponse(request, "deals/not_found.html", context={
            "session": request.session,
        }, status_code=404)
    return templates.TemplateResponse(request, "deals/detail.html", context={
        "deal": deal,
        "user_id": user_id,
        "session": request.session,
    })


@router.post("/{deal_id}/accept")
async def deal_accept(request: Request, deal_id: int):
    user_id = get_current_user_id(request)
    container = get_container(request)
    try:
        await container.deal_service.accept_deal(user_id, deal_id)
    except Exception:
        pass
    return RedirectResponse(f"/deals/{deal_id}", status_code=302)


@router.post("/{deal_id}/decline")
async def deal_decline(request: Request, deal_id: int):
    user_id = get_current_user_id(request)
    container = get_container(request)
    try:
        await container.deal_service.decline_deal(user_id, deal_id)
    except Exception:
        pass
    return RedirectResponse(f"/deals/{deal_id}", status_code=302)


@router.post("/{deal_id}/confirm")
async def deal_confirm(request: Request, deal_id: int):
    user_id = get_current_user_id(request)
    container = get_container(request)
    try:
        await container.deal_service.confirm_success(user_id, deal_id)
    except Exception:
        pass
    return RedirectResponse(f"/deals/{deal_id}", status_code=302)


@router.post("/{deal_id}/dispute")
async def deal_dispute(request: Request, deal_id: int):
    user_id = get_current_user_id(request)
    container = get_container(request)
    try:
        await container.deal_service.open_dispute(user_id, deal_id)
    except Exception:
        pass
    return RedirectResponse(f"/deals/{deal_id}", status_code=302)


@router.post("/{deal_id}/moderator")
async def deal_moderator(request: Request, deal_id: int):
    user_id = get_current_user_id(request)
    container = get_container(request)
    try:
        await container.deal_service.request_moderator(user_id, deal_id)
    except Exception:
        pass
    return RedirectResponse(f"/deals/{deal_id}", status_code=302)


@router.post("/{deal_id}/message")
async def deal_send_message(request: Request, deal_id: int, message: str = Form("")):
    user_id = get_current_user_id(request)
    container = get_container(request)
    if message.strip():
        try:
            await container.deal_service.record_chat_message(
                telegram_id=user_id,
                deal_id=deal_id,
                content_type="text",
                body=message.strip(),
            )
        except Exception:
            pass
    return RedirectResponse(f"/deals/{deal_id}", status_code=302)
