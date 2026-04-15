"""Маршруты витрины: каталог, категории, товары, поиск."""

from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse

from cerber_bot.web.deps import build_fake_user, get_container, get_current_user_id, notify_user, templates

router = APIRouter(prefix="/store", tags=["store"])


@router.get("", response_class=HTMLResponse)
async def store_index(request: Request):
    user_id = get_current_user_id(request)
    container = get_container(request)
    dashboard = await container.store_service.get_dashboard(user_id)
    categories, page_info = await container.store_service.get_categories_page(page=1, per_page=50)
    return templates.TemplateResponse(request, "store/index.html", context={
        "dashboard": dashboard,
        "categories": categories,
        "page_info": page_info,
        "session": request.session,
    })


@router.get("/category/{category_id}", response_class=HTMLResponse)
async def store_category(request: Request, category_id: int, page: int = Query(1, ge=1)):
    get_current_user_id(request)
    container = get_container(request)
    products, page_info = await container.store_service.get_products_page(
        page=page, per_page=12, category_id=category_id,
    )
    categories, _ = await container.store_service.get_categories_page(page=1, per_page=50)
    cat_name = next((c.name for c in categories if c.category_id == category_id), f"#{category_id}")
    return templates.TemplateResponse(request, "store/category.html", context={
        "products": products,
        "page_info": page_info,
        "category_id": category_id,
        "category_name": cat_name,
        "session": request.session,
    })


@router.get("/product/{product_id}", response_class=HTMLResponse)
async def store_product(request: Request, product_id: str):
    user_id = get_current_user_id(request)
    container = get_container(request)
    product = await container.store_service.get_product_view(product_id)
    wallet = await container.store_service.get_wallet_snapshot(user_id)
    return templates.TemplateResponse(request, "store/product.html", context={
        "product": product,
        "wallet": wallet,
        "session": request.session,
    })


@router.get("/search", response_class=HTMLResponse)
async def store_search(request: Request, q: str = Query(""), page: int = Query(1, ge=1)):
    get_current_user_id(request)
    container = get_container(request)
    products = ()
    page_info = None
    error = None
    if q.strip():
        try:
            products, page_info = await container.store_service.get_products_page(
                page=page, per_page=12, search_query=q.strip(),
            )
        except Exception as exc:
            error = str(exc)
    return templates.TemplateResponse(request, "store/search.html", context={
        "query": q,
        "products": products,
        "page_info": page_info,
        "error": error,
        "session": request.session,
    })


@router.post("/purchase/{product_id}/{sku_id}", response_class=HTMLResponse)
async def purchase_sku(request: Request, product_id: str, sku_id: str):
    user_id = get_current_user_id(request)
    container = get_container(request)

    try:
        result = await container.store_service.purchase_offer(
            build_fake_user(user_id, request.session), product_id=product_id, sku_id=sku_id,
        )
        await notify_user(
            request, user_id,
            f"🛒 Покупка через веб-магазин\n"
            f"<b>{result.order.product_name}</b> — {result.order.sku_name}\n"
            f"Списано: {result.charged_amount:.2f} {result.charged_currency}\n"
            f"Остаток: {result.balance_after:.2f} {result.currency}",
        )
        return templates.TemplateResponse(request, "store/purchase_result.html", context={
            "result": result,
            "error": None,
            "session": request.session,
        })
    except Exception as exc:
        return templates.TemplateResponse(request, "store/purchase_result.html", context={
            "result": None,
            "error": str(exc),
            "session": request.session,
        })
