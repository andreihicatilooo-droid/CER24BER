"""Маршруты профиля пользователя."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from cerber_bot.web.deps import get_container, get_current_user_id, templates

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("", response_class=HTMLResponse)
async def profile_index(request: Request):
    user_id = get_current_user_id(request)
    container = get_container(request)
    wallet = await container.store_service.get_wallet_snapshot(user_id)
    deal_dashboard = await container.deal_service.get_dashboard(user_id)
    user = await container.store_service._get_user(user_id) if hasattr(container.store_service, '_get_user') else None
    return templates.TemplateResponse(request, "profile/index.html", context={
        "wallet": wallet,
        "deal_stats": deal_dashboard.statistics,
        "session": request.session,
    })
