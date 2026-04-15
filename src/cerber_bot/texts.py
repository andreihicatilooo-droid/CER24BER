"""Централизованные пользовательские тексты.

Все строки интерфейса, уведомления и ошибки хранятся в одном месте.
Разбиты на классы по назначению:  UI-меню, витрина, сделки, платежи и т.д.
"""

from __future__ import annotations


class COMMON_TEXT:
    YES_RU = "да"
    NO_RU = "нет"
    YES_EN = "yes"
    NO_EN = "no"
    NOT_AVAILABLE = "n/a"
    UNKNOWN = "unknown"
    NETWORK_NOT_AVAILABLE = "network n/a"
    PACKAGE_PLACEHOLDER = "package"
    CUSTOM_PRICE = "custom price"


class START_TEXT:
    BASE_CAPTION = (
        "<b>CERBER</b>\n"
        "Цифровой магазин с каталогом GiftAPI, гарантом сделок, персональным балансом и историей операций.\n"
        "Открой меню ниже, чтобы перейти в витрину, кошелек, гарант-сделки и вывод в USDT."
    )
    NEW_USER_NOTE = "\n\nВаш профиль создан и сохранен в базе данных."
    RETURNING_USER_NOTE = "\n\nРады видеть вас снова."
    TELEGRAM_USER_NOT_FOUND = "Не удалось определить Telegram-пользователя."

    @classmethod
    def welcome_caption(cls, created: bool) -> str:
        return cls.BASE_CAPTION + (cls.NEW_USER_NOTE if created else cls.RETURNING_USER_NOTE)


class MAIN_MENU_TEXT:
    STORE = "Магазин"
    SEARCH = "Поиск"
    WALLET = "Кошелек"
    DEALS = "Гарант сделки"
    ORDERS = "Мои заказы"
    PROFILE = "Профиль"
    REFRESH = "Обновить каталог"
    SUPPORT = "Поддержка"
    WEB_APP = "🌐 Веб-магазин"


class GIFTAPI_MENU_TEXT:
    OVERVIEW = "Профиль и баланс"
    CATEGORIES = "Категории"
    PRODUCTS = "Товары"
    PRODUCT_LOOKUP = "Товар по UUID"
    ORDERS = "Заказы"
    ORDER_LOOKUP = "Заказ по UUID"
    CREATE_ORDER = "Создать заказ"
    ESIM_STATUS = "eSIM статус"
    BACK = "Назад"


class STORE_KEYBOARD_TEXT:
    CATEGORIES = "Категории"
    SEARCH = "Поиск"
    WALLET = "Кошелек"
    ORDERS = "Мои заказы"
    HOME = "Домой"
    BACK = "Назад"
    BACK_TO_LIST = "Назад к списку"
    CUSTOM_AMOUNT = "Своя сумма"
    PAY_WITH_NICEPAY = "Оплатить через NicePay"
    PAGINATION_PREVIOUS = "◀"
    PAGINATION_PLACEHOLDER = "·"
    PAGINATION_NEXT = "▶"
    PRICE_ON_REQUEST = "цена по запросу"
    PRICE_FROM_TEMPLATE = "от {amount}"
    BUY_TEMPLATE = "Купить {offer_name} • {price}"
    CATEGORY_TEMPLATE = "{category_name} ({product_count})"
    PRODUCT_TEMPLATE = "{product_name} • {price_label}"
    ORDER_TEMPLATE = "#{order_id} {product_name} • {total_amount}"
    PAGE_TEMPLATE = "{page}/{total_pages}"

    @classmethod
    def top_up_amount(cls, amount: str) -> str:
        return f"+{amount}"

    @classmethod
    def price_from(cls, amount: str) -> str:
        return cls.PRICE_FROM_TEMPLATE.format(amount=amount)

    @classmethod
    def buy_offer(cls, offer_name: str, price: str) -> str:
        return cls.BUY_TEMPLATE.format(offer_name=offer_name, price=price)

    @classmethod
    def category_card(cls, category_name: str, product_count: int) -> str:
        return cls.CATEGORY_TEMPLATE.format(category_name=category_name, product_count=product_count)

    @classmethod
    def product_card(cls, product_name: str, price_label: str) -> str:
        return cls.PRODUCT_TEMPLATE.format(product_name=product_name, price_label=price_label)

    @classmethod
    def order_card(cls, order_id: int, product_name: str, total_amount: str) -> str:
        return cls.ORDER_TEMPLATE.format(order_id=order_id, product_name=product_name, total_amount=total_amount)

    @classmethod
    def page_info(cls, page: int, total_pages: int) -> str:
        return cls.PAGE_TEMPLATE.format(page=page, total_pages=total_pages)


class DEAL_KEYBOARD_TEXT:
    CREATE_DEAL = "Создать сделку"
    MY_DEALS = "Мои сделки"
    WITHDRAW_USDT = "Запрос вывода USDT"
    WALLET = "Кошелек"
    MAIN_MENU = "Главное меню"
    DEAL_HOME = "Гарант"
    ACCEPT = "Принять"
    DECLINE = "Отклонить"
    CANCEL_DEAL = "Отменить сделку"
    DEAL_CHAT = "Написать в чат сделки"
    CONFIRM_SUCCESS = "Подтвердить выполнение"
    OPEN_DISPUTE = "Открыть диспут"
    CALL_MODERATOR = "Позвать модератора"
    OPEN_DEAL = "Открыть сделку"
    CANCEL_REQUEST = "Отменить заявку"
    MOD_RELEASE = "Решение: в пользу продавца"
    MOD_REFUND = "Решение: возврат покупателю"
    APPROVE_WITHDRAWAL = "Одобрить вывод"
    REJECT_WITHDRAWAL = "Отклонить вывод"
    PAGINATION_PREVIOUS = "◀"
    PAGINATION_PLACEHOLDER = "·"
    PAGINATION_NEXT = "▶"
    PAGE_TEMPLATE = "{page}/{total_pages}"
    DEAL_CARD_TEMPLATE = "#{deal_id} {status} • {amount} • {counterpart}"
    CANCEL_WITHDRAW_TEMPLATE = "Отменить вывод #{request_id}"
    STATUS_LABELS = {
        "pending_acceptance": "ожидает принятия",
        "active": "активна",
        "disputed": "диспут",
        "completed": "завершена",
        "declined": "отклонена",
        "canceled": "отменена",
        "refunded": "возврат",
    }

    @classmethod
    def page_info(cls, page: int, total_pages: int) -> str:
        return cls.PAGE_TEMPLATE.format(page=page, total_pages=total_pages)

    @classmethod
    def deal_card(cls, deal_id: int, status: str, amount: str, counterpart: str) -> str:
        return cls.DEAL_CARD_TEMPLATE.format(
            deal_id=deal_id,
            status=status,
            amount=amount,
            counterpart=counterpart,
        )

    @classmethod
    def cancel_withdraw(cls, request_id: int) -> str:
        return cls.CANCEL_WITHDRAW_TEMPLATE.format(request_id=request_id)


class MENU_TEXT:
    PROFILE_NOT_FOUND = "Профиль еще не найден. Отправьте /start, чтобы зарегистрироваться."
    PROFILE_OPENED = "Профиль открыт"
    CATALOG_REFRESHING = "Обновляю каталог..."
    CATALOG_NOT_REFRESHED_TITLE = "<b>Каталог не обновлен</b>"
    SUPPORT_CONTACT_MISSING = "контакт поддержки не настроен"
    SUPPORT_CONTACT_TEMPLATE = "Связь с поддержкой: {support_url}"
    CONTACTS_SENT = "Контакты отправлены"
    PROFILE_TITLE = "<b>Профиль CERBER</b>"
    PROFILE_USERNAME_UNKNOWN = "не указан"
    PROFILE_FIRST_NAME_UNKNOWN = "не указано"
    PROFILE_LAST_NAME_UNKNOWN = "не указана"
    PROFILE_LANGUAGE_UNKNOWN = "не указан"
    PROFILE_TELEGRAM_ID = "Telegram ID: {telegram_id}"
    PROFILE_USERNAME = "Username: {username}"
    PROFILE_FIRST_NAME = "Имя: {first_name}"
    PROFILE_LAST_NAME = "Фамилия: {last_name}"
    PROFILE_LANGUAGE = "Язык: {language}"
    PROFILE_AVAILABLE = "Доступно: {amount}"
    PROFILE_HELD = "Заблокировано: {amount}"
    PROFILE_TOTAL = "Всего: {amount}"
    PROFILE_EQUIVALENT = "Эквивалент: {usdt_amount} | {rub_amount}"
    PROFILE_ORDER_COUNT = "Заказов: {count}"
    PROFILE_TOTAL_DEALS = "Сделок всего: {count}"
    PROFILE_OPEN_DEALS = "Активных сделок: {count}"
    PROFILE_DEALS_VOLUME = "Оборот сделок: {amount}"
    PROFILE_PENDING_WITHDRAWALS = "Выводов в работе: {count}"
    PROFILE_CREATED = "Создан: {created_at}"
    PROFILE_LAST_SEEN = "Последняя активность: {last_seen}"
    DEV_BALANCE_BUTTON = "Dev: баланс"
    DEV_BALANCE_TITLE = "<b>Dev: операции с балансом</b>"
    DEV_BALANCE_AVAILABLE = "Доступно: {amount}"
    DEV_BALANCE_HELD = "Заблокировано: {amount}"
    DEV_BALANCE_TOTAL = "Всего: {amount}"
    DEV_BALANCE_HINT = "Меняется только доступный баланс. Заблокированные средства сделок и выводов не затрагиваются."
    DEV_BALANCE_TOP_UP = "Пополнить"
    DEV_BALANCE_DEBIT = "Списать"
    DEV_BALANCE_BACK = "Назад в профиль"
    DEV_BALANCE_MENU_OPENED = "Dev-меню открыто"
    DEV_BALANCE_ACCESS_DENIED = "Dev-меню недоступно."
    DEV_BALANCE_TOP_UP_PROMPT = "Введите сумму для пополнения доступного баланса. Например: 25 или 25.50"
    DEV_BALANCE_DEBIT_PROMPT = "Введите сумму для списания с доступного баланса. Например: 25 или 25.50"
    DEV_BALANCE_INVALID_AMOUNT = "Не удалось распознать сумму. Используйте формат 25 или 25.50."
    DEV_BALANCE_AMOUNT_POSITIVE = "Сумма должна быть больше нуля."
    DEV_BALANCE_UPDATED = "Баланс обновлен: {operation} {amount}. Доступно сейчас: {balance}."
    DEV_BALANCE_CREDIT_OPERATION = "пополнение"
    DEV_BALANCE_DEBIT_OPERATION = "списание"
    REFRESH_REPORT_TITLE = "<b>Каталог обновлен</b>"
    REFRESH_REPORT_CATEGORIES = "Категорий доступно: {count}"
    REFRESH_REPORT_PRODUCTS = "Товаров в витрине: {count}"
    REFRESH_REPORT_HINT = "Откройте магазин, чтобы увидеть свежие остатки и цены."

    @classmethod
    def support_contact(cls, support_url: str) -> str:
        return cls.SUPPORT_CONTACT_TEMPLATE.format(support_url=support_url)

    @classmethod
    def catalog_not_refreshed(cls, error_text: str) -> str:
        return f"{cls.CATALOG_NOT_REFRESHED_TITLE}\n{error_text}"

    @classmethod
    def dev_balance_updated(cls, operation: str, amount: str, balance: str) -> str:
        return cls.DEV_BALANCE_UPDATED.format(operation=operation, amount=amount, balance=balance)


class GIFTAPI_TEXT:
    CALLBACK_OPENED = "GiftAPI открыт"
    CALLBACK_ERROR = "Ошибка GiftAPI"
    CALLBACK_OVERVIEW_LOADED = "Профиль GiftAPI загружен"
    CALLBACK_CATEGORIES_LOADED = "Категории загружены"
    CALLBACK_PRODUCTS_LOADED = "Товары загружены"
    CALLBACK_PRODUCT_UUID_READY = "Жду UUID товара"
    CALLBACK_ORDERS_LOADED = "Заказы загружены"
    CALLBACK_ORDER_UUID_READY = "Жду UUID заказа"
    CALLBACK_ORDER_JSON_READY = "Жду JSON заказа"
    CALLBACK_ESIM_READY = "Жду ICCID"
    CALLBACK_NOT_CONFIGURED = "GiftAPI не настроен"
    CALLBACK_MAIN_MENU = "Возврат в главное меню"
    PRODUCT_LOOKUP_PROMPT = "Отправьте UUID товара GiftAPI, и бот загрузит полную карточку с SKU, ценами и обязательными полями."
    ORDER_LOOKUP_PROMPT = "Отправьте UUID заказа GiftAPI, и бот покажет детальный статус, позиции и выданные delivery_data."
    ESIM_PROMPT = "Отправьте ICCID eSIM, и бот запросит статус, остаток трафика и пакеты через GiftAPI."
    MAIN_MENU_TITLE = "<b>Главное меню CERBER</b>"
    ACTION_CANCELED = "Действие отменено."
    PRODUCT_UUID_INVALID = "UUID товара не распознан. Отправьте UUID еще раз."
    ORDER_UUID_INVALID = "UUID заказа не распознан. Отправьте UUID еще раз."
    ESIM_ICCID_INVALID = "ICCID не распознан. Отправьте ICCID еще раз."
    ORDER_JSON_RETRY = "Отправьте JSON еще раз."
    ERROR_TITLE = "<b>GiftAPI вернул ошибку</b>"
    MENU_STATUS_CONNECTED = "подключен"
    MENU_STATUS_NOT_CONFIGURED = "не настроен"
    MENU_INTRO_TEMPLATE = (
        "<b>GiftAPI</b>\n"
        "Отдельный раздел для работы с партнерским сервисом GiftAPI: каталог, баланс, заказы и eSIM.\n"
        "Текущий статус интеграции: <b>{status}</b>."
    )
    OVERVIEW_TITLE = "<b>GiftAPI: профиль партнера</b>"
    UUID = "UUID: {value}"
    NAME = "Название: {value}"
    EMAIL = "Email: {value}"
    CURRENCY = "Валюта: {value}"
    STATUS = "Статус: {value}"
    STATUS_ACTIVE = "active"
    STATUS_INACTIVE = "inactive"
    BALANCE_TITLE = "<b>Баланс</b>"
    BALANCE_CURRENT = "Текущий: {amount}"
    BALANCE_AVAILABLE = "Доступно: {amount}"
    BALANCE_RESERVED = "Резерв: {amount}"
    BALANCE_OVERDRAFT = "Овердрафт: {value}"
    BALANCE_OVERDRAFT_LIMIT = "Лимит овердрафта: {amount}"
    RECENT_TRANSACTIONS_TITLE = "<b>Последние операции</b>"
    RECENT_TRANSACTION = "{created_at} | {transaction_type} | {amount} | после: {balance_after}"
    CATEGORIES_TITLE = "<b>GiftAPI: категории</b>"
    CATEGORIES_TOTAL = "Всего категорий: {count}"
    CATEGORIES_EMPTY = "Категории пока не получены."
    CATEGORY_ROW = "{category_id} | {name} | атрибутов: {attributes_count}{suffix}"
    CATEGORY_PARENT_SUFFIX = " | parent={parent_id}"
    CATEGORIES_LIMIT = "Показаны первые {limit} категорий."
    PRODUCTS_TITLE = "<b>GiftAPI: товары</b>"
    PRODUCTS_LOADED = "Загружено товаров: {count}"
    PRODUCTS_EMPTY = "Товары не найдены."
    TYPE = "Тип: {value}"
    CATEGORY = "Категория: {value}"
    DENOMINATION = "Номинал: {value}"
    SKU_PREVIEW = "SKU: {preview}"
    PRODUCTS_HAS_MORE = "У GiftAPI есть следующая страница. При необходимости добавим пагинацию отдельно."
    PRODUCTS_DETAIL_HINT = "Для полной карточки используйте кнопку «Товар по UUID»."
    REQUIRED_FIELDS_TITLE = "<b>Обязательные поля заказа</b>"
    REQUIRED_FIELD = "{code} | {name} | {field_type} | required={required}{validation}"
    SKU_TITLE = "<b>SKU</b>"
    SKU_ROW = "{sku_id} | {name} | {price_text} | stock={stock}"
    SKU_LIMIT = "Показаны первые {limit} SKU."
    ORDERS_TITLE = "<b>GiftAPI: заказы</b>"
    ORDERS_LOADED = "Загружено заказов: {count}"
    ORDERS_EMPTY = "Заказы не найдены."
    ORDER_TITLE = "<b>{external_id}</b>"
    ORDER_STATUS = "Статус: {value}"
    ORDER_TOTAL = "Сумма: {amount}"
    ORDER_CREATED = "Создан: {created_at}"
    ORDER_ITEMS_COUNT = "Позиций: {count}"
    ORDERS_HAS_MORE = "У GiftAPI есть следующая страница истории заказов."
    ORDERS_DETAIL_HINT = "Для полного заказа используйте кнопку «Заказ по UUID»."
    ORDER_DETAIL_TITLE = "<b>GiftAPI: заказ {external_id}</b>"
    ORDER_ITEMS_TITLE = "<b>Позиции</b>"
    ORDER_ITEM = "{sku_name} | qty={quantity} | {status} | {price_text}"
    ORDER_ITEM_ERROR = "Ошибка: {error_message}"
    CREATED_ORDER_TITLE = "<b>GiftAPI: заказ создан</b>"
    CREATED_ORDER_EXTERNAL_ID = "Внешний ID: {external_id}"
    DELIVERY_DATA_TITLE = "Delivery data:"
    ESIM_TITLE = "<b>GiftAPI: eSIM статус</b>"
    ESIM_ICCID = "ICCID: {iccid}"
    ESIM_RENEWABLE = "Можно продлить: {value}"
    ESIM_LAST_BUNDLE = "Последний пакет: {value}"
    ESIM_TRAFFIC = "Трафик: {value}"
    ESIM_QR = "QR: {value}"
    ESIM_LINK = "Ссылка: {value}"
    ESIM_ACTIVE_PACKAGES_TITLE = "<b>Активные пакеты</b>"
    ESIM_ACTIVE_PACKAGE = "{package_name} | остаток {balance}"
    ESIM_COVERAGE_TITLE = "<b>Покрытие</b>"
    ESIM_COVERAGE_ROW = "{country} | {network}"
    ORDER_CREATION_TITLE = "<b>GiftAPI: создание заказа</b>"
    ORDER_CREATION_BODY = "Отправьте JSON payload в формате API. Бот сам подпишет запрос HMAC и отправит его в сервис."
    ORDER_CREATION_CANCEL = "Для отмены отправьте текст: отмена"
    CUSTOM_AMOUNT_TEMPLATE = "custom amount {details}"
    CUSTOM_AMOUNT_MARKUP = "markup"
    VALIDATION_MIN = "min={value}"
    VALIDATION_MAX = "max={value}"
    VALIDATION_REGEX = "regex={value}"
    VALIDATION_OPTIONS = "options={count}"
    VALIDATION_SEPARATOR = "; "
    VALIDATION_TEMPLATE = " | {parts}"
    CANCEL_COMMANDS = frozenset({"cancel", "отмена"})

    @classmethod
    def menu_intro(cls, status: str) -> str:
        return cls.MENU_INTRO_TEMPLATE.format(status=status)

    @classmethod
    def giftapi_error(cls, error_text: str) -> str:
        return f"{cls.ERROR_TITLE}\n{error_text}"

    @classmethod
    def order_json_retry(cls, error_text: str) -> str:
        return f"{error_text}\n\n{cls.ORDER_JSON_RETRY}"

    @classmethod
    def custom_amount(cls, details: str) -> str:
        return cls.CUSTOM_AMOUNT_TEMPLATE.format(details=details)

    @classmethod
    def validation_text(cls, parts: str) -> str:
        return cls.VALIDATION_TEMPLATE.format(parts=parts)


class STOREFRONT_TEXT:
    CALLBACK_HOME_UNAVAILABLE = "Витрина временно недоступна"
    CALLBACK_HOME_OPENED = "Главная витрина"
    CALLBACK_CATEGORIES_UNAVAILABLE = "Категории недоступны"
    CALLBACK_CATEGORIES_OPENED = "Категории открыты"
    CALLBACK_PRODUCTS_UNAVAILABLE = "Товары недоступны"
    CALLBACK_CATEGORY_PRODUCTS = "Товары категории"
    CALLBACK_SEARCH_READY = "Жду поисковый запрос"
    CALLBACK_SEARCH_UNAVAILABLE = "Поиск недоступен"
    CALLBACK_PRODUCT_UNAVAILABLE = "Карточка товара недоступна"
    CALLBACK_PRODUCT_OPENED = "Карточка товара"
    CALLBACK_REOPEN_PRODUCT = "Откройте товар заново"
    CALLBACK_SCREEN_UNAVAILABLE = "Экран недоступен"
    CALLBACK_WALLET_OPENED = "Кошелек открыт"
    CALLBACK_PAYMENT_CREATING = "Создаю ссылку на оплату..."
    CALLBACK_TOP_UP_AMOUNT_READY = "Жду сумму"
    CALLBACK_PURCHASE_FAILED = "Покупка не выполнена"
    CALLBACK_ORDER_CREATED = "Заказ создан"
    CALLBACK_ORDERS_HISTORY = "История заказов"
    CALLBACK_ORDER_NOT_FOUND = "Заказ не найден"
    CALLBACK_ORDER_DETAILS = "Детали заказа"
    SEARCH_PROMPT = "Введите название товара, бренда или часть категории для поиска по каталогу."
    SEARCH_EMPTY = "Запрос пустой. Введите хотя бы 2 символа."
    TOP_UP_CUSTOM_PROMPT = (
        "Введите сумму пополнения в валюте внутреннего кошелька. "
        "Поддерживаются десятичные значения, например `25` или `25.50`."
    )
    SEARCH_TITLE = "<b>Поиск</b>"
    SEARCH_ENTER_FIRST = "Сначала введите поисковый запрос."
    STORE_TITLE = "<b>CERBER Store</b>"
    STORE_DESCRIPTION = "Цифровые товары и подарочные карты подключены через интеграцию GiftAPI."
    STORE_CATEGORIES = "Категорий: {count}"
    STORE_PRODUCTS = "Товаров в каталоге: {count}"
    STORE_AVAILABLE = "Доступно: {amount}"
    STORE_HELD = "Заблокировано: {amount}"
    STORE_TOTAL = "Всего: {amount}"
    STORE_EQUIVALENT = "Эквивалент: {usdt_amount} | {rub_amount}"
    STORE_ORDER_COUNT = "Ваших заказов: {count}"
    STORE_HINT = "Выберите категорию, найдите товар по названию или пополните внутренний баланс для покупки."
    CATEGORIES_TITLE = "<b>Категории CERBER</b>"
    PAGE_OF = "Страница {page} из {total_pages}"
    CATEGORIES_EMPTY = "Категории пока не найдены."
    CATEGORY_ROW = "• {name} — {count} товаров"
    PRODUCTS_EMPTY = "Ничего не найдено по текущему фильтру."
    PRODUCT_CATEGORY = "Категория: {value}"
    PRODUCT_TYPE = "Тип: {value}"
    PRODUCT_PRICE = "Цена: {value}"
    PRODUCT_SKU = "SKU: {sku_count} | доступно для покупки: {buyable_sku_count}"
    PRODUCT_STOCK = "Остаток: {stock}"
    PRODUCT_DENOMINATION = "Модель номинала: {value}"
    PRODUCT_FIELDS_TITLE = "<b>Поля заказа</b>"
    PRODUCT_FIELD = "• {name} ({code})"
    PRODUCT_OFFERS_TITLE = "<b>Предложения</b> | страница {page}/{total_pages}"
    PRODUCT_OFFERS_EMPTY = "Нет SKU для отображения."
    PRODUCT_OFFER_AVAILABLE = "доступен"
    PRODUCT_OFFER_UNAVAILABLE = "недоступен"
    PRODUCT_OFFER_PRICE = "Цена: {value}"
    PRODUCT_OFFER_STOCK = "Остаток: {stock}"
    PRODUCT_OFFER_MAX = "Макс. в заказе: {value}"
    PRODUCT_OFFER_STATUS = "Статус: {value}"
    WALLET_TITLE = "Ваш кошелек CERBER"
    WALLET_AVAILABLE = "Доступно: {amount}"
    WALLET_HELD = "Заблокировано: {amount}"
    WALLET_TOTAL = "Всего: {amount}"
    WALLET_EQUIVALENT = "Эквивалент: {usdt_amount} | {rub_amount}"
    WALLET_RATE = "Курс: 1 USDT ≈ {amount}"
    WALLET_ORDER_COUNT = "Заказов оформлено: {count}"
    WALLET_NICEPAY_INFO = "Пополнение работает через NicePay: баланс зачисляется только после финального callback от платежного сервиса."
    WALLET_RECENT_TITLE = "<b>Последние операции</b>"
    WALLET_RECENT_EMPTY = "Операций пока нет. Используйте кнопки ниже, чтобы пополнить баланс."
    WALLET_TRANSACTION = "• {created_at} | {transaction_type} | {amount}"
    ORDERS_TITLE = "<b>Мои заказы</b>"
    ORDERS_EMPTY = "Заказов пока нет. Найдите товар и оформите первую покупку."
    ORDER_TITLE = "<b>#{order_id} {product_name}</b>"
    ORDER_SKU = "SKU: {sku_name}"
    ORDER_STATUS = "Статус: {status}"
    ORDER_TOTAL = "Сумма: {amount}"
    ORDER_CREATED = "Создан: {created_at}"
    ORDER_DETAIL_TITLE = "<b>Заказ #{order_id}</b>"
    ORDER_EXTERNAL_ID = "Внешний ID: {external_id}"
    ORDER_PROVIDER_ID = "ID у поставщика: {provider_order_id}"
    ORDER_PROVIDER = "Провайдер: {provider}"
    ORDER_PRODUCT = "Товар: {product_name}"
    ORDER_DELIVERY_TITLE = "<b>Delivery data</b>"
    ORDER_ERROR = "Ошибка: {error_message}"
    PURCHASE_TITLE = "<b>Покупка успешно оформлена</b>"
    PURCHASE_ORDER = "Заказ #{order_id} | статус: {status}"
    PURCHASE_PRODUCT = "Товар: {product_name}"
    PURCHASE_SKU = "SKU: {sku_name}"
    PURCHASE_CHARGED = "Списано: {amount}"
    PURCHASE_BALANCE_AFTER = "Баланс после покупки: {amount}"
    PURCHASE_DELIVERY_TITLE = "<b>Код / данные доставки</b>"
    ERROR_TITLE = "<b>Операция не выполнена</b>"
    ENTER_TOP_UP_AMOUNT = "Введите сумму пополнения."
    INVALID_TOP_UP_AMOUNT = "Не удалось распознать сумму. Используйте формат 25 или 25.50."
    PAYMENT_LINK_TITLE = "<b>Ссылка на оплату сформирована</b>"
    PAYMENT_LINK_AMOUNT = "Сумма: {amount}"
    PAYMENT_LINK_ESTIMATED = "Ожидаемое зачисление: {amount}"
    PAYMENT_LINK_ID = "NicePay ID: {payment_id}"
    PAYMENT_LINK_EXPIRES = "Действует до: {expires_at}"
    PAYMENT_LINK_AUTO_UPDATE = "После успешной оплаты NicePay пришлет callback, и баланс обновится автоматически."
    PAYMENT_LINK_EXPIRES_UNKNOWN = "не указано"
    PRODUCT_TITLE_PREFIX = "Поиск: {query}"
    CATALOG_TITLE = "Каталог CERBER"

    @classmethod
    def search_enter_first(cls) -> str:
        return f"{cls.SEARCH_TITLE}\n{cls.SEARCH_ENTER_FIRST}"

    @classmethod
    def store_error(cls, error_text: str) -> str:
        return f"{cls.ERROR_TITLE}\n{error_text}"


class PAYMENT_TEXT:
    SUCCESS_TITLE = "<b>Платеж NicePay подтвержден</b>"
    SUCCESS_AMOUNT = "Оплачено: {amount}"
    SUCCESS_CREDITED = "Зачислено в кошелек: {amount}"
    SUCCESS_BALANCE = "Баланс кошелька: {amount}"
    METHOD = "Метод: {method}"
    SUCCESS_HINT = "Баланс обновлен автоматически, можно возвращаться в каталог."
    ERROR_TITLE = "<b>Платеж NicePay завершился с ошибкой</b>"
    ERROR_AMOUNT = "Сумма: {amount}"
    ERROR_HINT = "Средства не были зачислены на внутренний баланс."
    CALLBACK_JSON_OBJECT_REQUIRED = "NicePay callback body must be a JSON object."
    CALLBACK_SUCCESS_RESPONSE = "Success"


class GIFTAPI_CLIENT_TEXT:
    HINT = "Подсказка: {hint}"
    MISSING_BASE_URL = "Не задан GIFTAPI_BASE_URL."
    MISSING_TOKEN = "Не задан GIFTAPI_TOKEN."
    MISSING_SECRET = "Не задан GIFTAPI_SECRET для подписи заказов."


class NICEPAY_TEXT:
    MISSING_CREDENTIALS = "Не заданы NICEPAY_MERCHANT_ID и NICEPAY_SECRET. Без них NicePay не сможет создать ссылку на оплату."
    CREATE_PAYMENT_FAILED = "Не удалось создать платеж NicePay."
    CALLBACK_HASH_REQUIRED = "NicePay callback не содержит hash."
    INVALID_HASH = "Invalid hash"
    PAYMENT_NOT_CREATED = "NicePay не создал платеж."


class PAYMENT_SERVICE_TEXT:
    UNSUPPORTED_CURRENCY = "Валюта {currency} не поддерживается NicePay. Доступно: {available}."
    MIN_TOP_UP = "Минимальная сумма пополнения: {amount}."
    MAX_TOP_UP = "Максимальная сумма пополнения: {amount}."
    FOREIGN_MERCHANT = "NicePay callback пришел с чужим merchant_id."
    PAYMENT_NOT_FOUND = "Платеж не найден в локальной системе."
    WRONG_PROVIDER = "Платеж создан не через NicePay и не может быть обработан этим callback."
    CURRENCY_MISMATCH = "Валюта платежа не совпадает с валютой кошелька."
    AMOUNT_MISMATCH = "NicePay вернул сумму, не совпадающую с локальным счетом."
    PAYMENT_ID_MISMATCH = "NicePay payment_id не совпадает с локальным платежом."
    UNKNOWN_STATUS = "NicePay вернул неизвестный финальный статус: {status}."
    DESCRIPTION_SUFFIX = " Amount: {amount}"
    CREDIT_DESCRIPTION_DIRECT = "Пополнение через NicePay на {paid_text}"
    CREDIT_DESCRIPTION_CONVERTED = "Пополнение через NicePay: оплачено {paid_text}, зачислено {credited_text}"

    @classmethod
    def unsupported_currency(cls, currency: str, available: str) -> str:
        return cls.UNSUPPORTED_CURRENCY.format(currency=currency, available=available)

    @classmethod
    def min_top_up(cls, amount: str) -> str:
        return cls.MIN_TOP_UP.format(amount=amount)

    @classmethod
    def max_top_up(cls, amount: str) -> str:
        return cls.MAX_TOP_UP.format(amount=amount)

    @classmethod
    def unknown_status(cls, status: str) -> str:
        return cls.UNKNOWN_STATUS.format(status=status)

    @classmethod
    def description_suffix(cls, amount: str) -> str:
        return cls.DESCRIPTION_SUFFIX.format(amount=amount)

    @classmethod
    def credit_description_direct(cls, paid_text: str) -> str:
        return cls.CREDIT_DESCRIPTION_DIRECT.format(paid_text=paid_text)

    @classmethod
    def credit_description_converted(cls, paid_text: str, credited_text: str) -> str:
        return cls.CREDIT_DESCRIPTION_CONVERTED.format(paid_text=paid_text, credited_text=credited_text)


class GIFTAPI_SERVICE_TEXT:
    CONFIGURATION_MESSAGE_PREFIX = "GiftAPI еще не настроен. Заполните переменные окружения: "
    INVALID_ORDER_JSON = "Ожидается корректный JSON payload заказа."
    ORDER_JSON_OBJECT = "JSON заказа должен быть объектом."
    ORDER_ITEM_OBJECT = "Поле item должно быть объектом."
    ORDER_FIELDS_OBJECT = "Поле item.fields должно быть объектом."
    ORDER_METADATA_OBJECT = "Поле metadata должно быть объектом или null."
    REQUIRED_FIELD = "Поле {field_name} обязательно."

    @classmethod
    def configuration_message(cls, missing: list[str]) -> str:
        return cls.CONFIGURATION_MESSAGE_PREFIX + ", ".join(missing) + "."

    @classmethod
    def required_field(cls, field_name: str) -> str:
        return cls.REQUIRED_FIELD.format(field_name=field_name)


class STORE_SERVICE_TEXT:
    INSUFFICIENT_FUNDS = "Недостаточно средств. Доступно {available}, требуется {required}."
    REASON_DYNAMIC_PRICE = "цена рассчитывается динамически"
    REASON_OUT_OF_STOCK = "нет в наличии"
    REASON_CUSTOM_AMOUNT = "нужна произвольная сумма"
    REASON_CUSTOMER_DATA = "нужны дополнительные данные покупателя"
    TOP_UP_AMOUNT_POSITIVE = "Сумма пополнения должна быть больше нуля."
    TOP_UP_DESCRIPTION = "Пополнение баланса на {amount}"
    BALANCE_ADJUSTMENT_NON_ZERO = "Сумма изменения должна быть больше нуля."
    MANUAL_CREDIT_DESCRIPTION = "Ручное пополнение разработчиком на {amount}"
    MANUAL_DEBIT_DESCRIPTION = "Ручное списание разработчиком на {amount}"
    SKU_NOT_FOUND = "SKU не найден в карточке товара."
    SKU_NOT_BUYABLE = "Этот SKU пока нельзя купить через бота."
    USER_NOT_FOUND_AFTER_AUTH = "Пользователь не найден в локальной базе после авторизации."
    SEARCH_QUERY_TOO_SHORT = "Поисковый запрос должен содержать минимум 2 символа."
    PURCHASE_LABEL = "Покупка {product_name}"

    @classmethod
    def insufficient_funds(cls, available: str, required: str) -> str:
        return cls.INSUFFICIENT_FUNDS.format(available=available, required=required)

    @classmethod
    def top_up_description(cls, amount: str) -> str:
        return cls.TOP_UP_DESCRIPTION.format(amount=amount)

    @classmethod
    def manual_credit_description(cls, amount: str) -> str:
        return cls.MANUAL_CREDIT_DESCRIPTION.format(amount=amount)

    @classmethod
    def manual_debit_description(cls, amount: str) -> str:
        return cls.MANUAL_DEBIT_DESCRIPTION.format(amount=amount)

    @classmethod
    def purchase_label(cls, product_name: str) -> str:
        return cls.PURCHASE_LABEL.format(product_name=product_name)


class DEAL_SERVICE_TEXT:
    DEAL_AMOUNT_POSITIVE = "Сумма сделки должна быть больше нуля."
    DEAL_TERMS_TOO_SHORT = "Опишите полные условия сделки, минимум 10 символов."
    PARTNER_NOT_FOUND = "Партнер не найден. Второй пользователь должен сначала запустить бота и быть зарегистрирован в базе."
    DEAL_WITH_SELF = "Нельзя создать сделку с самим собой."
    HOLD_INSUFFICIENT_FUNDS = "Недостаточно средств для блокировки. Доступно {available}."
    DEAL_HOLD_DESCRIPTION = "Блокировка средств по сделке #{deal_id}"
    DEAL_CREATED_MESSAGE = "Сделка создана и ожидает подтверждения второй стороны."
    DEAL_NOT_FOUND = "Сделка не найдена."
    ACCEPT_ONLY_SECOND_PARTY = "Принять сделку может только второй пользователь."
    DEAL_CANNOT_ACCEPT = "Эту сделку уже нельзя принять."
    SELLER_NOT_FOUND = "Продавец не найден в локальной базе."
    DEAL_ACCEPTED_MESSAGE = "Сделка подтверждена. Можно передавать товар, реквизиты или другие данные через чат сделки."
    DEAL_WRONG_STATUS = "Сделка уже перешла в другой статус."
    DEAL_PERMISSION_DENIED = "Недостаточно прав для этой сделки."
    BUYER_NOT_FOUND = "Покупатель не найден в локальной базе."
    DEAL_HELD_UNAVAILABLE = "Заблокированные средства по сделке уже недоступны."
    DEAL_HOLD_RETURN_DESCRIPTION = "Возврат блокировки по сделке #{deal_id}"
    DEAL_CANCELED_MESSAGE = "Сделка отменена, средства возвращены покупателю."
    MODERATOR_ONLY_ACTIVE_OR_DISPUTE = "Модератора можно позвать только в активной сделке или при споре."
    MODERATOR_REQUESTED_MESSAGE = "По сделке запрошено подключение модератора."
    DISPUTE_ONLY_ACTIVE = "Открыть спор можно только по активной сделке."
    DISPUTE_OPENED_MESSAGE = "По сделке открыт спор. Средства останутся заблокированными до решения."
    CONFIRM_ONLY_BUYER = "Подтвердить успешность сделки может только покупатель, который блокировал средства."
    DEAL_CANNOT_CONFIRM = "Эту сделку уже нельзя завершить подтверждением."
    DEAL_PARTICIPANTS_NOT_FOUND = "Участники сделки не найдены в локальной базе."
    DEAL_CREDIT_DESCRIPTION = "Зачисление по сделке #{deal_id}"
    DEAL_CONFIRMED_MESSAGE = "Покупатель подтвердил успешное выполнение сделки. Средства переведены второй стороне."
    MODERATOR_ONLY = "Эта команда доступна только модератору."
    UNKNOWN_MODERATION_ACTION = "Неизвестный тип модераторского решения."
    MODERATION_ONLY_DISPUTED = "Модераторское решение можно применить только к спорной сделке."
    DISPUTE_HELD_UNAVAILABLE = "Заблокированные средства по спору уже недоступны."
    DISPUTE_REFUND_DESCRIPTION = "Возврат по спору сделки #{deal_id}"
    MODERATOR_REFUND_MESSAGE = "Модератор решил спор в пользу покупателя. Средства возвращены на баланс."
    MODERATOR_RELEASE_DESCRIPTION = "Зачисление по решению модератора, сделка #{deal_id}"
    MODERATOR_RELEASE_MESSAGE = "Модератор решил спор в пользу продавца. Средства перечислены второй стороне."
    DEAL_CHAT_EMPTY = "Нельзя отправить пустое сообщение в сделке."
    CHAT_ONLY_ACTIVE_OR_DISPUTE = "Переписка доступна только в активной сделке или споре."
    SENDER_NOT_FOUND = "Отправитель не найден в локальной базе."
    MIN_WITHDRAWAL_AMOUNT = "Минимальная сумма вывода: {amount}."
    UNSUPPORTED_NETWORK = "Сеть не поддерживается. Доступно: {networks}."
    INVALID_USDT_ADDRESS = "Введите корректный адрес кошелька USDT."
    OPEN_WITHDRAWAL_EXISTS = "У вас уже есть активная заявка на вывод. Дождитесь обработки или отмените ее."
    WITHDRAWAL_INSUFFICIENT_FUNDS = "Недостаточно средств для вывода. Доступно {available}."
    WITHDRAWAL_REQUEST_DESCRIPTION = "Заявка на вывод {amount} в сеть {network}"
    WITHDRAWAL_NOT_FOUND = "Заявка на вывод не найдена."
    WITHDRAWAL_CANNOT_CANCEL = "Эту заявку уже нельзя отменить."
    USER_NOT_FOUND = "Пользователь не найден в локальной базе."
    WITHDRAWAL_FUNDS_UNAVAILABLE = "Средства по заявке уже недоступны для возврата."
    WITHDRAWAL_CANCELED_BY_USER = "Отменено пользователем"
    WITHDRAWAL_CANCEL_REFUND_DESCRIPTION = "Возврат средств по отмененной заявке #{request_id}"
    UNKNOWN_WITHDRAWAL_ACTION = "Неизвестное действие над заявкой на вывод."
    WITHDRAWAL_ALREADY_PROCESSED = "Эта заявка уже была обработана."
    WITHDRAWAL_OWNER_NOT_FOUND = "Пользователь заявки не найден в локальной базе."
    WITHDRAWAL_HELD_UNAVAILABLE = "Заблокированные средства по заявке уже недоступны."
    WITHDRAWAL_APPROVED_BY_MODERATOR = "Одобрено модератором {moderator_id}"
    WITHDRAWAL_REJECTED_BY_MODERATOR = "Отклонено модератором {moderator_id}"
    WITHDRAWAL_REJECT_REFUND_DESCRIPTION = "Возврат средств по отклоненной заявке #{request_id}"
    SYSTEM_SENDER = "Система"
    UNKNOWN_USER = "неизвестный пользователь"
    WALLET_CURRENCY_MISMATCH = "Кошелек пользователя ведется в {current_currency}, а операция требует {required_currency}."
    USER_NOT_IN_DEAL = "Указанный пользователь не участвует в этой сделке."

    @classmethod
    def hold_insufficient_funds(cls, available: str) -> str:
        return cls.HOLD_INSUFFICIENT_FUNDS.format(available=available)

    @classmethod
    def deal_hold_description(cls, deal_id: int) -> str:
        return cls.DEAL_HOLD_DESCRIPTION.format(deal_id=deal_id)

    @classmethod
    def deal_hold_return_description(cls, deal_id: int) -> str:
        return cls.DEAL_HOLD_RETURN_DESCRIPTION.format(deal_id=deal_id)

    @classmethod
    def deal_credit_description(cls, deal_id: int) -> str:
        return cls.DEAL_CREDIT_DESCRIPTION.format(deal_id=deal_id)

    @classmethod
    def dispute_refund_description(cls, deal_id: int) -> str:
        return cls.DISPUTE_REFUND_DESCRIPTION.format(deal_id=deal_id)

    @classmethod
    def moderator_release_description(cls, deal_id: int) -> str:
        return cls.MODERATOR_RELEASE_DESCRIPTION.format(deal_id=deal_id)

    @classmethod
    def minimum_withdrawal_amount(cls, amount: str) -> str:
        return cls.MIN_WITHDRAWAL_AMOUNT.format(amount=amount)

    @classmethod
    def unsupported_network(cls, networks: str) -> str:
        return cls.UNSUPPORTED_NETWORK.format(networks=networks)

    @classmethod
    def withdrawal_insufficient_funds(cls, available: str) -> str:
        return cls.WITHDRAWAL_INSUFFICIENT_FUNDS.format(available=available)

    @classmethod
    def withdrawal_request_description(cls, amount: str, network: str) -> str:
        return cls.WITHDRAWAL_REQUEST_DESCRIPTION.format(amount=amount, network=network)

    @classmethod
    def withdrawal_cancel_refund_description(cls, request_id: int) -> str:
        return cls.WITHDRAWAL_CANCEL_REFUND_DESCRIPTION.format(request_id=request_id)

    @classmethod
    def withdrawal_approved_by_moderator(cls, moderator_id: int) -> str:
        return cls.WITHDRAWAL_APPROVED_BY_MODERATOR.format(moderator_id=moderator_id)

    @classmethod
    def withdrawal_rejected_by_moderator(cls, moderator_id: int) -> str:
        return cls.WITHDRAWAL_REJECTED_BY_MODERATOR.format(moderator_id=moderator_id)

    @classmethod
    def withdrawal_reject_refund_description(cls, request_id: int) -> str:
        return cls.WITHDRAWAL_REJECT_REFUND_DESCRIPTION.format(request_id=request_id)

    @classmethod
    def wallet_currency_mismatch(cls, current_currency: str, required_currency: str) -> str:
        return cls.WALLET_CURRENCY_MISMATCH.format(
            current_currency=current_currency,
            required_currency=required_currency,
        )


class DEAL_HANDLER_TEXT:
    CALLBACK_MENU = "Меню сделок"
    NEW_DEAL_PARTNER_PROMPT = "Введите username партнера или его Telegram ID. Пользователь должен уже запустить бота."
    CALLBACK_WAIT_USER = "Жду пользователя"
    ENTER_PARTNER = "Введите username или Telegram ID пользователя."
    ENTER_DEAL_AMOUNT = "Введите сумму сделки. Она будет заблокирована на вашем балансе до завершения."
    ENTER_DEAL_TERMS = "Теперь отправьте полные условия сделки: что передается, сроки и критерии выполнения."
    CALLBACK_MY_DEALS = "Мои сделки"
    CALLBACK_DEAL_UNAVAILABLE = "Сделка недоступна"
    CALLBACK_DEAL_OPENED = "Сделка открыта"
    CALLBACK_ACCEPT_FAILED = "Не удалось принять"
    DEAL_ACCEPTED_NOTIFICATION = "Вторая сторона приняла сделку. Чат открыт, можно передавать данные или товар."
    CALLBACK_DEAL_ACCEPTED = "Сделка принята"
    CHAT_PROMPT = "Отправьте следующее сообщение, фото или файл. Бот перешлет его второй стороне и добавит в журнал сделки. Для отмены напишите 'отмена'."
    CALLBACK_WAIT_MESSAGE = "Жду сообщение"
    CHAT_CANCELED = "Отправка сообщения отменена."
    DEAL_CONTEXT_LOST = "Контекст сделки потерян. Откройте сделку заново."
    ATTACHMENT_FORWARD_FAILED = "Не удалось переслать вложение автоматически. Краткое содержание: {preview}"
    CALLBACK_COMPLETE_FAILED = "Не удалось завершить"
    DEAL_COMPLETED_NOTIFICATION = "Сделка подтверждена как успешная. Средства зачислены на ваш баланс."
    CALLBACK_DEAL_COMPLETED = "Сделка завершена"
    CALLBACK_DISPUTE_FAILED = "Не удалось открыть спор"
    DISPUTE_OPENED_NOTIFICATION = "По сделке открыт спор. Средства останутся заблокированными до решения."
    MODERATOR_REASON_DISPUTE = "Открыт спор по сделке"
    CALLBACK_DISPUTE_OPENED = "Спор открыт"
    CALLBACK_MODERATOR_FAILED = "Не удалось вызвать модератора"
    MODERATOR_REQUESTED_NOTIFICATION = "По сделке запрошено подключение модератора."
    MODERATOR_REASON_REQUESTED = "По сделке запросили модератора"
    CALLBACK_MODERATOR_REQUESTED = "Модератор запрошен"
    CALLBACK_MODERATION_FAILED = "Не удалось применить решение"
    CALLBACK_MODERATION_APPLIED = "Решение применено"
    WITHDRAW_PROMPT = "Введите сумму вывода в USDT. После этого выберете сеть и отправьте адрес кошелька."
    CALLBACK_WAIT_AMOUNT = "Жду сумму"
    WITHDRAW_NETWORK_PROMPT = "Выберите сеть вывода USDT."
    CALLBACK_ENTER_WITHDRAW_AMOUNT_FIRST = "Сначала введите сумму вывода"
    WITHDRAW_ADDRESS_PROMPT = "Отправьте адрес кошелька для сети {network}. Для отмены напишите 'отмена'."
    CALLBACK_WAIT_ADDRESS = "Жду адрес"
    CALLBACK_WITHDRAW_CANCEL_FAILED = "Не удалось отменить заявку"
    CALLBACK_WITHDRAW_CANCELED = "Заявка отменена"
    CALLBACK_WITHDRAW_PROCESS_FAILED = "Не удалось обработать вывод"
    CALLBACK_WITHDRAW_PROCESSED = "Заявка обработана"
    CALLBACK_CLOSE_FAILED = "Не удалось закрыть"
    DEAL_CLOSED_NOTIFICATION = "Сделка закрыта, заблокированные средства возвращены покупателю."
    CALLBACK_STATUS_UPDATED = "Статус обновлен"
    MISSING_MODERATORS = "Модераторы через бота пока не настроены. Для ручного разбора используйте: {support}"
    DASHBOARD_TITLE = "<b>Гарант сделки</b>"
    DASHBOARD_AVAILABLE = "Доступно: {amount}"
    DASHBOARD_HELD = "Заблокировано: {amount}"
    DASHBOARD_TOTAL = "Всего в системе: {amount}"
    DASHBOARD_EQUIVALENT = "Эквивалент: {usdt_amount} | {rub_amount}"
    DASHBOARD_STATS_TITLE = "<b>Статистика</b>"
    DASHBOARD_TOTAL_DEALS = "Всего сделок: {count}"
    DASHBOARD_OPEN_DEALS = "Активных и спорных: {count}"
    DASHBOARD_COMPLETED_DEALS = "Успешно завершено: {count}"
    DASHBOARD_DISPUTES = "Споров сейчас: {count}"
    DASHBOARD_TURNOVER = "Оборот: {amount} | {usdt_amount}"
    DASHBOARD_WITHDRAWALS = "Активных заявок на вывод: {count}"
    DASHBOARD_OPEN_WITHDRAWAL_TITLE = "<b>Открытый вывод</b>"
    DASHBOARD_OPEN_WITHDRAWAL = "#{request_id} • {amount} • {network}"
    DASHBOARD_NO_MODERATORS = "Модераторы в боте пока не настроены: споры и выводы будут требовать ручной обработки через поддержку."
    DEALS_PAGE_TITLE = "<b>Мои сделки</b>"
    PAGE_OF = "Страница {page} из {total_pages}"
    DEALS_EMPTY = "Сделок пока нет. Начните новую сделку из меню гаранта."
    DEAL_CARD_TITLE = "<b>#{deal_id}</b> {counterpart}"
    DEAL_CARD_ROLE = "Роль: {role}"
    DEAL_CARD_STATUS = "Статус: {status}"
    DEAL_CARD_AMOUNT = "Сумма: {amount}"
    DEAL_CARD_UPDATED = "Обновлено: {updated_at}"
    DEAL_VIEW_TITLE = "<b>Сделка #{deal_id}</b>"
    DEAL_VIEW_MY_ROLE = "Ваша роль: {role}"
    DEAL_VIEW_STATUS = "Статус: {status}"
    DEAL_VIEW_BUYER = "Покупатель: {buyer}"
    DEAL_VIEW_SELLER = "Продавец: {seller}"
    DEAL_VIEW_AMOUNT = "Сумма: {amount}"
    DEAL_VIEW_EQUIVALENT = "Эквивалент: {usdt_amount} | {rub_amount}"
    DEAL_VIEW_CREATED = "Создана: {created_at}"
    DEAL_VIEW_ACCEPTED = "Принята: {accepted_at}"
    DEAL_VIEW_DISPUTED = "Спор открыт: {disputed_at}"
    DEAL_VIEW_COMPLETED = "Завершена: {completed_at}"
    DEAL_VIEW_RESOLUTION = "Решение: {resolution}"
    DEAL_VIEW_TERMS_TITLE = "<b>Условия</b>"
    DEAL_VIEW_MESSAGES_TITLE = "<b>Последние сообщения</b>"
    DEAL_VIEW_NO_MESSAGES = "Сообщений пока нет."
    DEAL_VIEW_MESSAGE_ROW = "• {created_at} | {sender} | {body}"
    DEAL_INVITATION_TITLE = "<b>Новая заявка на гарант-сделку</b>"
    DEAL_INVITATION_BUYER = "Покупатель: {buyer}"
    DEAL_INVITATION_AMOUNT = "Сумма: {amount}"
    DEAL_INVITATION_TERMS_TITLE = "<b>Условия</b>"
    DEAL_INVITATION_HINT = "После принятия откроется чат сделки, а средства уже заблокированы у покупателя."
    DEAL_STATUS_NOTIFICATION_TITLE = "<b>Обновление по сделке #{deal_id}</b>"
    DEAL_STATUS_NOTIFICATION_STATUS = "Статус: {status}"
    DEAL_MESSAGE_NOTIFICATION_TITLE = "<b>Новое сообщение по сделке #{deal_id}</b>"
    DEAL_MESSAGE_NOTIFICATION_FROM = "От: {sender}"
    WITHDRAW_REQUEST_TITLE = "<b>Заявка на вывод #{request_id}</b>"
    WITHDRAW_REQUEST_STATUS = "Статус: {status}"
    WITHDRAW_REQUEST_AMOUNT_USDT = "Сумма к выводу: {amount}"
    WITHDRAW_REQUEST_HELD = "Заблокировано: {amount}"
    WITHDRAW_REQUEST_NETWORK = "Сеть: {network}"
    WITHDRAW_REQUEST_ADDRESS = "Адрес: {address}"
    WITHDRAW_REQUEST_CREATED = "Создана: {created_at}"
    WITHDRAW_REQUEST_COMMENT = "Комментарий: {comment}"
    WITHDRAW_STATUS_NOTIFICATION_TITLE = "<b>Статус вывода #{request_id}</b>"
    WITHDRAW_STATUS_NOTIFICATION_STATUS = "Новый статус: {status}"
    WITHDRAW_STATUS_NOTIFICATION_AMOUNT = "Сумма: {amount}"
    MODERATOR_ALERT_TITLE = "<b>Требуется модератор</b>"
    MODERATOR_ALERT_DEAL = "Сделка: #{deal_id}"
    MODERATOR_ALERT_BUYER = "Покупатель: {buyer}"
    MODERATOR_ALERT_SELLER = "Продавец: {seller}"
    MODERATOR_ALERT_AMOUNT = "Сумма: {amount}"
    MODERATOR_ALERT_STATUS = "Статус: {status}"
    MODERATOR_WITHDRAW_TITLE = "<b>Новая заявка на вывод</b>"
    MODERATOR_WITHDRAW_ID = "Заявка: #{request_id}"
    MODERATOR_WITHDRAW_USER = "Пользователь: {telegram_id}"
    MODERATOR_WITHDRAW_AMOUNT = "Сумма: {amount}"
    MODERATOR_WITHDRAW_NETWORK = "Сеть: {network}"
    MODERATOR_WITHDRAW_ADDRESS = "Адрес: {address}"
    MODERATION_RESULT_TITLE = "<b>Решение модератора применено</b>"
    MODERATION_RESULT_DEAL = "Сделка: #{deal_id}"
    MODERATION_RESULT_STATUS = "Статус: {status}"
    MODERATION_RESULT_RESOLUTION = "Решение: {resolution}"
    MODERATION_NOTIFICATION_TITLE = "<b>Модератор завершил разбор сделки #{deal_id}</b>"
    OPERATION_FAILED_TITLE = "<b>Операция не выполнена</b>"
    ENTER_AMOUNT_NUMERIC = "Введите сумму числом."
    INVALID_AMOUNT = "Не удалось распознать сумму. Используйте формат 25 или 25.50."
    ROLE_BUYER = "покупатель"
    ROLE_SELLER = "продавец"
    DEAL_STATUS_LABELS = {
        "pending_acceptance": "ожидает подтверждения",
        "active": "активна",
        "disputed": "спор",
        "completed": "завершена",
        "declined": "отклонена",
        "canceled": "отменена",
        "refunded": "возврат покупателю",
    }
    WITHDRAWAL_STATUS_LABELS = {
        "requested": "ожидает обработки",
        "approved": "одобрена",
        "rejected": "отклонена",
        "canceled": "отменена",
    }
    CONTENT_WITH_CAPTION = "[{content_type}] {caption}"
    CONTENT_SUMMARIES = {
        "photo": "[photo] Фото без подписи",
        "document": "[document] Файл без подписи",
        "video": "[video] Видео без подписи",
        "voice": "[voice] Голосовое сообщение",
        "audio": "[audio] Аудиофайл",
        "sticker": "[sticker] Стикер",
    }
    CONTENT_EMPTY = "[{content_type}] Сообщение без текста"
    CANCEL_COMMANDS = frozenset({"отмена", "cancel", "/cancel"})
    ACTION_CANCELED = "Действие отменено."
    RESOLUTION_UNSPECIFIED = "не указано"

    @classmethod
    def attachment_forward_failed(cls, preview: str) -> str:
        return cls.ATTACHMENT_FORWARD_FAILED.format(preview=preview)

    @classmethod
    def withdraw_address_prompt(cls, network: str) -> str:
        return cls.WITHDRAW_ADDRESS_PROMPT.format(network=network)

    @classmethod
    def missing_moderators(cls, support: str) -> str:
        return cls.MISSING_MODERATORS.format(support=support)

    @classmethod
    def deal_status_notification_title(cls, deal_id: int) -> str:
        return cls.DEAL_STATUS_NOTIFICATION_TITLE.format(deal_id=deal_id)

    @classmethod
    def deal_message_notification_title(cls, deal_id: int) -> str:
        return cls.DEAL_MESSAGE_NOTIFICATION_TITLE.format(deal_id=deal_id)

    @classmethod
    def moderator_notification_title(cls, deal_id: int) -> str:
        return cls.MODERATION_NOTIFICATION_TITLE.format(deal_id=deal_id)

    @classmethod
    def deal_status_label(cls, value: str) -> str:
        return cls.DEAL_STATUS_LABELS.get(value, value)

    @classmethod
    def withdrawal_status_label(cls, value: str) -> str:
        return cls.WITHDRAWAL_STATUS_LABELS.get(value, value)

    @classmethod
    def content_with_caption(cls, content_type: str, caption: str) -> str:
        return cls.CONTENT_WITH_CAPTION.format(content_type=content_type, caption=caption)

    @classmethod
    def content_empty(cls, content_type: str) -> str:
        return cls.CONTENT_EMPTY.format(content_type=content_type)

    @classmethod
    def deal_error(cls, error_text: str) -> str:
        return f"{cls.OPERATION_FAILED_TITLE}\n{error_text}"


class ADMIN_TEXT:
    """Тексты для административного бота."""

    ACCESS_DENIED = "Доступ запрещён. Вы не в списке модераторов."

    WELCOME = (
        "<b>CERBER Admin</b>\n"
        "Административная панель для модерации сделок, выводов и оповещений.\n"
        "Используйте меню ниже."
    )

    DASHBOARD_TITLE = "<b>Панель управления</b>"
    DASHBOARD_DISPUTES = "Открытых диспутов: {count}"
    DASHBOARD_WITHDRAWALS = "Заявок на вывод: {count}"

    DISPUTES_TITLE = "<b>Диспуты</b>"
    DISPUTES_EMPTY = "Нет открытых диспутов."
    DISPUTE_CARD = (
        "#{deal_id} • {amount}\n"
        "Покупатель: {buyer} | Продавец: {seller}\n"
        "Открыт: {disputed_at}"
    )

    WITHDRAWALS_TITLE = "<b>Заявки на вывод</b>"
    WITHDRAWALS_EMPTY = "Нет ожидающих заявок."
    WITHDRAWAL_CARD = (
        "#{request_id} • {amount} • {network}\n"
        "Пользователь: {telegram_id}\n"
        "Адрес: {address}"
    )

    DEAL_VIEW_TITLE = "<b>Сделка #{deal_id}</b>"
    DEAL_VIEW_BUYER = "Покупатель: {buyer}"
    DEAL_VIEW_SELLER = "Продавец: {seller}"
    DEAL_VIEW_AMOUNT = "Сумма: {amount}"
    DEAL_VIEW_STATUS = "Статус: {status}"
    DEAL_VIEW_TERMS = "Условия:\n{terms}"
    DEAL_VIEW_CREATED = "Создана: {created_at}"
    DEAL_VIEW_DISPUTED = "Спор открыт: {disputed_at}"
    DEAL_VIEW_MESSAGES_TITLE = "<b>Последние сообщения:</b>"
    DEAL_VIEW_NO_MESSAGES = "Сообщений нет."
    DEAL_VIEW_MESSAGE_ROW = "{created_at} [{sender}]: {body}"

    MODERATION_APPLIED = "Решение применено."
    WITHDRAWAL_PROCESSED = "Заявка обработана."

    CALLBACK_WAIT = "Загрузка..."

    BTN_DISPUTES = "Диспуты"
    BTN_WITHDRAWALS = "Заявки на вывод"
    BTN_HOME = "Главная"
    BTN_RELEASE = "В пользу продавца"
    BTN_REFUND = "Возврат покупателю"
    BTN_APPROVE_WITHDRAWAL = "Одобрить"
    BTN_REJECT_WITHDRAWAL = "Отклонить"
    BTN_OPEN_DEAL = "Подробнее"
    BTN_BACK_TO_LIST = "Назад к списку"

    # Чат модератора в диспуте
    BTN_WRITE_TO_CHAT = "✍ Написать в чат"
    BTN_REFRESH_DEAL = "🔄 Обновить"
    CHAT_INPUT_PROMPT = (
        "Введите сообщение для участников сделки #{deal_id}:\n"
        "Покупатель: {buyer} • Продавец: {seller}"
    )
    CHAT_SENT = "Сообщение отправлено участникам сделки #{deal_id}."
    CHAT_RELAY_NOTIFICATION = "📨 <b>Сообщение от модератора</b> по сделке #{deal_id}:\n\n{body}"
    DEAL_VIEW_MESSAGE_MOD_ROW = "{created_at} [⚖ Мод]: {body}"
    CHAT_DEAL_NOT_ACTIVE = "Сообщение нельзя отправить — сделка уже не активна."

    # Управление балансом пользователей
    BTN_USERS = "👤 Пользователи"
    BTN_BALANCE_ADD = "➕ Начислить"
    BTN_BALANCE_SUB = "➖ Списать"
    BTN_BACK_TO_USER = "↩ Назад к профилю"
    USERS_FIND_PROMPT = "Введите Telegram ID или @username пользователя:"
    USER_NOT_FOUND = "Пользователь не найден."
    USER_PROFILE_TITLE = "<b>Пользователь #{telegram_id}</b>"
    USER_PROFILE_NAME = "Имя: {name}"
    USER_PROFILE_USERNAME = "Username: @{username}"
    USER_PROFILE_BALANCE = "Доступно: {balance} {currency}"
    USER_PROFILE_HELD = "Заблокировано: {held} {currency}"
    BALANCE_DELTA_PROMPT = (
        "Текущий баланс: <b>{balance} {currency}</b>\n\n"
        "Введите сумму изменения:\n"
        "<code>+100</code> — начислить 100\n"
        "<code>-50</code> — списать 50"
    )
    BALANCE_ADJUSTED = "✓ Баланс изменён: {old} → <b>{new} {currency}</b>"
    BALANCE_DELTA_INVALID = "Неверный формат. Введите число, например <code>+100</code> или <code>-50</code>."
    BALANCE_NEGATIVE_ERROR = "Недостаточно средств — баланс не может стать отрицательным."

    # Статус системы
    BTN_STATUS = "⚙ Статус"
    STATUS_TITLE = "<b>⚙ Статус системы</b>"
    STATUS_SERVICES_HEADER = "\n<b>Сервисы:</b>"
    STATUS_SERVICE_OK = "  ✅ {name}"
    STATUS_SERVICE_FAIL = "  ❌ {name}: {reason}"
    STATUS_LOGS_HEADER = "\n<b>Лог {name} (последние {n} строк):</b>"
    STATUS_LOG_EMPTY = "<i>(лог пуст)</i>"
    STATUS_LOG_NOT_FOUND = "<i>(файл не найден)</i>"
    BTN_LOG_BOT = "📄 Лог бота"
    BTN_LOG_ERR = "🔴 Ошибки"
    BTN_LOG_TUNNEL = "🌐 Туннель"
    BTN_CHECK_SERVICES = "🔌 Проверить сервисы"