"""Маршруты раздела CRP в вебе."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from cerber_bot.web.deps import get_container, get_current_user_id, templates

router = APIRouter(prefix="/reputation", tags=["reputation"])


@router.get("", response_class=HTMLResponse)
async def reputation_index(request: Request):
    user_id = get_current_user_id(request)
    container = get_container(request)
    profile = await container.user_service.get_profile(user_id)
    reputation = await container.reputation_service.get_user_reputation(user_id)
    deal_dashboard = await container.deal_service.get_dashboard(user_id)
    reviews = await container.reputation_service.get_reviews_for_user(user_id, limit=20)
    return templates.TemplateResponse(request, "reputation/index.html", context={
        "profile": profile,
        "reputation": reputation,
        "deal_stats": deal_dashboard.statistics,
        "reviews": reviews,
        "session": request.session,
    })
