# Расширение CERBER Bot

Руководство по добавлению нового функционала: провайдеров каталога, платёжных шлюзов, обработчиков и текстов.

---

## Содержание

- [Новый провайдер каталога](#новый-провайдер-каталога)
- [Новый платёжный шлюз](#новый-платёжный-шлюз)
- [Новый раздел бота (handler)](#новый-раздел-бота-handler)
- [Настройка текстов](#настройка-текстов)
- [Миграции базы данных](#миграции-базы-данных)
- [Добавление новой модели](#добавление-новой-модели)
- [Архитектурные соглашения](#архитектурные-соглашения)

---

## Новый провайдер каталога

Провайдер — это класс, который загружает товары из внешнего источника и возвращает их в формате `list[Product]`.

### Шаг 1. Создайте файл провайдера

```
src/cerber_bot/integrations/providers/my_provider.py
```

### Шаг 2. Наследуйтесь от `CatalogProvider` или `BaseHttpCatalogProvider`

**Простой провайдер (без HTTP):**

```python
from decimal import Decimal
from cerber_bot.integrations.base import CatalogProvider
from cerber_bot.integrations.schemas import Product


class MyCatalogProvider(CatalogProvider):
    name = "my_source"

    async def fetch_products(self) -> list[Product]:
        return [
            Product(
                external_id="my-1",
                provider=self.name,
                title="Товар",
                price=Decimal("100.00"),
                currency="RUB",
                category="Тестовые",
            ),
        ]
```

**HTTP-провайдер (с запросом к API):**

```python
from cerber_bot.integrations.http import BaseHttpCatalogProvider
from cerber_bot.integrations.schemas import Product


class MyCatalogProvider(BaseHttpCatalogProvider):
    def __init__(self, base_url, http_client, token=None):
        super().__init__(
            name="my_source",
            base_url=base_url,
            http_client=http_client,
            token=token,
        )

    async def fetch_products(self) -> list[Product]:
        data = await self.get_json("/api/products")
        return [self._map(item) for item in data]

    def _map(self, item: dict) -> Product:
        from decimal import Decimal
        return Product(
            external_id=str(item["id"]),
            provider=self.name,
            title=item["name"],
            price=Decimal(str(item["price"])),
            currency=item.get("currency", "RUB"),
            category=item.get("category"),
            in_stock=item.get("stock"),
        )
```

### Шаг 3. Добавьте настройки в `config.py`

```python
# config.py — внутри класса Settings
my_provider_url: str = ""
my_provider_token: str = ""
```

### Шаг 4. Зарегистрируйте провайдер в `registry.py`

Откройте `src/cerber_bot/integrations/registry.py` и добавьте в функцию `build_providers`:

```python
from cerber_bot.integrations.providers.my_provider import MyCatalogProvider

# Внутри build_providers(), перед return:
if settings.my_provider_url:
    providers.append(
        MyCatalogProvider(
            base_url=settings.my_provider_url,
            http_client=http_client,
            token=settings.my_provider_token,
        )
    )
```

### Шаг 5. Добавьте переменные в `.env`

```env
MY_PROVIDER_URL=https://api.example.com
MY_PROVIDER_TOKEN=your-token-here
```

Провайдер автоматически появится в витрине при следующем обновлении каталога.

---

## Новый платёжный шлюз

Платежи в CERBER организованы через `PaymentService` и webhook-сервер.

### Шаг 1. Создайте клиент

По аналогии с `integrations/nicepay.py`, создайте `integrations/my_pay.py`:

```python
import httpx
from dataclasses import dataclass


@dataclass
class MyPayLink:
    payment_id: str
    url: str


class MyPayClient:
    def __init__(self, merchant_id: str, secret: str, http_client: httpx.AsyncClient):
        self.merchant_id = merchant_id
        self.secret = secret
        self.http = http_client

    async def create_payment(self, amount: str, currency: str, order_id: str) -> MyPayLink:
        # Ваша логика создания ссылки на оплату
        ...

    def verify_callback(self, data: dict) -> bool:
        # Проверка подписи callback
        ...
```

### Шаг 2. Адаптируйте `PaymentService`

В `services/payments.py` добавьте метод для нового шлюза или замените вызовы `NicePayClient`.  Ключевой контракт:

1. Создать pending-запись в `wallet_payments`.
2. Запросить ссылку на оплату у шлюза.
3. По callback проверить подпись и зачислить баланс через `_credit_wallet()`.

### Шаг 3. Добавьте webhook-обработчик

Создайте FastAPI-маршрут в `src/cerber_bot/web/routes/` для callback нового шлюза и подключите его в `src/cerber_bot/web/app.py` рядом с другими webhook-роутами.

---

## Новый раздел бота (handler)

### Шаг 1. Создайте файл обработчика

```
src/cerber_bot/handlers/my_section.py
```

### Шаг 2. Определите builder-функцию

Каждый handler-модуль экспортирует функцию `build_*_router(container)`:

```python
from aiogram import Router
from aiogram.types import CallbackQuery

from cerber_bot.container import AppContainer


def build_my_section_router(container: AppContainer) -> Router:
    router = Router(name="my_section")

    @router.callback_query(lambda c: c.data == "my_section:menu")
    async def show_menu(callback: CallbackQuery) -> None:
        await callback.message.edit_text("Меню моего раздела")
        await callback.answer()

    return router
```

### Шаг 3. Подключите роутер в `main.py`

```python
from cerber_bot.handlers.my_section import build_my_section_router

# Внутри run(), после других include_router:
dispatcher.include_router(build_my_section_router(container))
```

### Шаг 4. Добавьте кнопку в меню

Добавьте кнопку в `keyboards/main_menu.py`:

```python
InlineKeyboardButton(text="📌 Мой раздел", callback_data="my_section:menu"),
```

---

## Настройка текстов

Все тексты бота собраны в `src/cerber_bot/texts.py`.  Каждый класс покрывает раздел:

| Класс | Раздел |
|-------|--------|
| `START_TEXT` | Приветствие по /start |
| `MAIN_MENU_TEXT` | Кнопки главного меню |
| `STOREFRONT_TEXT` | Витрина: категории, товары, карточки |
| `PAYMENT_TEXT` | Кошелёк, пополнение |
| `DEAL_HANDLER_TEXT` | Сделки, диспуты |
| `MENU_TEXT` | Профиль, вывод, статистика |
| `GIFTAPI_TEXT` | Прямой доступ к GiftAPI |

Чтобы изменить текст, найдите нужный класс и отредактируйте строку.  Все тексты на русском.

---

## Миграции базы данных

SQLite не поддерживает полноценный `ALTER TABLE`, поэтому миграции в `db/session.py` выполняются через `try/except`:

```python
# session.py — init_database()
async with engine.begin() as conn:
    try:
        await conn.execute(text("ALTER TABLE telegram_users ADD COLUMN new_field TEXT DEFAULT ''"))
    except Exception:
        pass  # Колонка уже существует
```

Для PostgreSQL рекомендуется перейти на Alembic:

```powershell
pip install alembic
alembic init migrations
```

---

## Добавление новой модели

### Шаг 1. Определите модель в `db/models.py`

```python
class MyEntity(Base):
    __tablename__ = "my_entities"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("telegram_users.id"))
    value: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
```

### Шаг 2. Создайте репозиторий в `db/repositories/`

```python
# db/repositories/my_entity.py
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from cerber_bot.db.models import MyEntity


class MyEntityRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, user_id: int, value: str) -> MyEntity:
        entity = MyEntity(user_id=user_id, value=value)
        self.session.add(entity)
        await self.session.flush()
        return entity

    async def get_by_user(self, user_id: int) -> list[MyEntity]:
        result = await self.session.execute(
            select(MyEntity).where(MyEntity.user_id == user_id)
        )
        return list(result.scalars().all())
```

### Шаг 3. Создайте сервис в `services/`

```python
# services/my_entity.py
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
from cerber_bot.db.repositories.my_entity import MyEntityRepository


class MyEntityService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self.session_factory = session_factory

    async def add(self, user_id: int, value: str):
        async with self.session_factory() as session:
            repo = MyEntityRepository(session)
            entity = await repo.create(user_id, value)
            await session.commit()
            return entity
```

### Шаг 4. Подключите сервис в `container.py`

Добавьте поле в `AppContainer` и инициализируйте его в `build()`.

---

## Архитектурные соглашения

| Правило | Описание |
|---------|----------|
| Все тексты — в `texts.py` | Не хардкодьте строки в handler/service |
| Каждый router — через builder | `def build_X_router(container) -> Router` |
| Сервис владеет session_factory | Создаёт сессию внутри каждого метода |
| Repository — через session | Не хранит ссылку на session_factory |
| AppContainer — единый DI | Все сервисы собираются в `container.py` |
| Клавиатуры — в `keyboards/` | Не создавайте InlineKeyboard в handler напрямую |
| Провайдеры — в `integrations/providers/` | Возвращают `list[Product]` |
| Настройки — через `config.py` | pydantic-settings, читает .env |
