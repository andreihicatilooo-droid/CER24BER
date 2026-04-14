"""Маршруты заказов: список и детали."""

from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse

from cerber_bot.web.deps import get_container, get_current_user_id, templates

router = APIRouter(prefix="/orders", tags=["orders"])


@router.get("", response_class=HTMLResponse)
async def orders_list(request: Request, page: int = Query(1, ge=1)):
    user_id = get_current_user_id(request)
    container = get_container(request)
    orders, page_info = await container.store_service.get_orders_page(user_id, page=page, per_page=10)
    return templates.TemplateResponse(request, "orders/index.html", context={
        "orders": orders,
        "page_info": page_info,
        "session": request.session,
    })


@router.get("/{order_id}", response_class=HTMLResponse)
async def order_detail(request: Request, order_id: int):
    user_id = get_current_user_id(request)
    container = get_container(request)
    order = await container.store_service.get_order_view(user_id, order_id)
    return templates.TemplateResponse(request, "orders/detail.html", context={
        "order": order,
        "session": request.session,
    })
