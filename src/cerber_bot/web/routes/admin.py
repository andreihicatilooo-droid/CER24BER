"""Маршруты административной панели CERBER.

Доступ только для moderator_ids.
Управление диспутами, выводами, статистика.
"""

from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from cerber_bot.web.deps import get_container, templates

router = APIRouter(prefix="/admin", tags=["admin"])

_ADMIN_SESSION_KEY = "cerber_admin_id"


def _get_admin_id(request: Request) -> int | None:
    val = request.session.get(_ADMIN_SESSION_KEY)
    return int(val) if val else None


def _require_admin(request: Request, container) -> int:
    """Return moderator telegram_id or raise 302 to login."""
    admin_id = _get_admin_id(request)
    if admin_id is None or admin_id not in container.deal_service.moderator_ids:
        raise _redirect_login()
    return admin_id


def _redirect_login():
    from fastapi import HTTPException
    from starlette.responses import RedirectResponse as R
    return HTTPException(status_code=302, headers={"location": "/admin/login"})


@router.get("/login", response_class=HTMLResponse)
async def admin_login_page(request: Request):
    admin_id = _get_admin_id(request)
    container = get_container(request)
    if admin_id and admin_id in container.deal_service.moderator_ids:
        return RedirectResponse("/admin", status_code=302)
    return templates.TemplateResponse(request, "admin/login.html", {"session": request.session})


@router.post("/login", response_class=HTMLResponse)
async def admin_login_submit(request: Request, telegram_id: str = Form(...)):
    container = get_container(request)
    try:
        tid = int(telegram_id.strip())
    except ValueError:
        return templates.TemplateResponse(request, "admin/login.html", {
            "session": request.session,
            "error": "Некорректный Telegram ID",
        }, status_code=400)

    if tid not in container.deal_service.moderator_ids:
        return templates.TemplateResponse(request, "admin/login.html", {
            "session": request.session,
            "error": "Доступ запрещён. Ваш ID не в списке модераторов.",
        }, status_code=403)

    request.session[_ADMIN_SESSION_KEY] = tid
    return RedirectResponse("/admin", status_code=302)


@router.get("/logout")
async def admin_logout(request: Request):
    request.session.pop(_ADMIN_SESSION_KEY, None)
    return RedirectResponse("/admin/login", status_code=302)


# ── Dashboard ────────────────────────────────────────────────

@router.get("", response_class=HTMLResponse)
async def admin_dashboard(request: Request):
    container = get_container(request)
    admin_id = _require_admin(request, container)
    disputes, withdrawals = await container.deal_service.get_admin_summary()
    return templates.TemplateResponse(request, "admin/dashboard.html", {
        "session": request.session,
        "admin_id": admin_id,
        "disputes_count": disputes,
        "withdrawals_count": withdrawals,
    })


# ── Диспуты ─────────────────────────────────────────────────

@router.get("/disputes", response_class=HTMLResponse)
async def admin_disputes(request: Request):
    container = get_container(request)
    admin_id = _require_admin(request, container)
    deals = await container.deal_service.list_disputed_deals()
    return templates.TemplateResponse(request, "admin/disputes.html", {
        "session": request.session,
        "admin_id": admin_id,
        "deals": deals,
    })


@router.get("/disputes/{deal_id}", response_class=HTMLResponse)
async def admin_dispute_detail(request: Request, deal_id: int):
    container = get_container(request)
    admin_id = _require_admin(request, container)
    deal = await container.deal_service.get_deal_view_admin(deal_id)
    if deal is None:
        return templates.TemplateResponse(request, "admin/not_found.html", {
            "session": request.session,
            "admin_id": admin_id,
            "msg": f"Сделка #{deal_id} не найдена",
        }, status_code=404)
    return templates.TemplateResponse(request, "admin/dispute_detail.html", {
        "session": request.session,
        "admin_id": admin_id,
        "deal": deal,
    })


@router.post("/disputes/{deal_id}/resolve", response_class=HTMLResponse)
async def admin_dispute_resolve(
    request: Request,
    deal_id: int,
    resolution: str = Form(...),
):
    container = get_container(request)
    admin_id = _require_admin(request, container)
    error = None
    try:
        await container.deal_service.resolve_dispute(admin_id, deal_id, resolution)
        return RedirectResponse(f"/admin/disputes/{deal_id}?resolved=1", status_code=302)
    except Exception as exc:
        error = str(exc)

    deal = await container.deal_service.get_deal_view_admin(deal_id)
    return templates.TemplateResponse(request, "admin/dispute_detail.html", {
        "session": request.session,
        "admin_id": admin_id,
        "deal": deal,
        "error": error,
    })


# ── Выводы ──────────────────────────────────────────────────

@router.get("/withdrawals", response_class=HTMLResponse)
async def admin_withdrawals(request: Request):
    container = get_container(request)
    admin_id = _require_admin(request, container)
    withdrawals = await container.deal_service.list_pending_withdrawals()
    return templates.TemplateResponse(request, "admin/withdrawals.html", {
        "session": request.session,
        "admin_id": admin_id,
        "withdrawals": withdrawals,
    })


@router.post("/withdrawals/{request_id}/approve")
async def admin_withdrawal_approve(request: Request, request_id: int):
    container = get_container(request)
    admin_id = _require_admin(request, container)
    try:
        await container.deal_service.moderate_withdrawal_request(admin_id, request_id, "approve")
    except Exception:
        pass
    return RedirectResponse("/admin/withdrawals?action=approved", status_code=302)


@router.post("/withdrawals/{request_id}/reject")
async def admin_withdrawal_reject(request: Request, request_id: int):
    container = get_container(request)
    admin_id = _require_admin(request, container)
    try:
        await container.deal_service.moderate_withdrawal_request(admin_id, request_id, "reject")
    except Exception:
        pass
    return RedirectResponse("/admin/withdrawals?action=rejected", status_code=302)


# ── Просмотр произвольной сделки ────────────────────────────

@router.get("/deals/{deal_id}", response_class=HTMLResponse)
async def admin_deal_view(request: Request, deal_id: int):
    container = get_container(request)
    admin_id = _require_admin(request, container)
    deal = await container.deal_service.get_deal_view_admin(deal_id)
    if deal is None:
        return templates.TemplateResponse(request, "admin/not_found.html", {
            "session": request.session,
            "admin_id": admin_id,
            "msg": f"Сделка #{deal_id} не найдена",
        }, status_code=404)
    return templates.TemplateResponse(request, "admin/deal_view.html", {
        "session": request.session,
        "admin_id": admin_id,
        "deal": deal,
    })
