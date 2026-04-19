"""Пользовательские тексты CEER Bot (интерфейс на русском языке)."""

from __future__ import annotations

from decimal import Decimal


class START_TEXT:
    BASE_CAPTION = (
        "<b>CEER</b> — игровой бот для Telegram-чатов\n"
        "Играй с друзьями прямо в чате. Баланс синхронизирован с CERBER.\n"
        "Выбери раздел ниже 👇"
    )
    NEW_USER_NOTE = "\n\n✅ Ваш профиль создан."
    RETURNING_USER_NOTE = "\n\nРады видеть снова!"
    TELEGRAM_USER_NOT_FOUND = "Не удалось определить Telegram-пользователя."

    @classmethod
    def welcome_caption(cls, created: bool) -> str:
        return cls.BASE_CAPTION + (cls.NEW_USER_NOTE if created else cls.RETURNING_USER_NOTE)


class MAIN_MENU_TEXT:
    PROFILE = "👤 Профиль"
    BALANCE = "💰 Баланс"
    ADD_TO_CHAT = "➕ Добавить в чат"
    RULES = "📋 Правила"
    SUPPORT = "🆘 Поддержка"


class PROFILE_TEXT:
    HEADER = "<b>👤 Ваш профиль</b>"
    NO_PROFILE = "Профиль не найден. Введите /start для регистрации."

    @classmethod
    def format(cls, username: str | None, first_name: str | None, balance: Decimal, currency: str) -> str:
        name = f"@{username}" if username else (first_name or "—")
        return (
            f"{cls.HEADER}\n\n"
            f"Имя: <b>{name}</b>\n"
            f"Баланс: <b>{balance:.2f} {currency}</b>"
        )


class BALANCE_TEXT:
    NO_PROFILE = "Профиль не найден. Введите /start для регистрации."

    @classmethod
    def format(cls, balance: Decimal, currency: str) -> str:
        return f"💰 Ваш баланс: <b>{balance:.2f} {currency}</b>"


class CHAT_EVENTS_TEXT:
    HELLO = (
        "👋 Привет! Я <b>CEER</b> — игровой бот.\n"
        "Используйте /game чтобы начать игру."
    )
    NO_RIGHTS = "⚠️ Мне нужны права администратора для корректной работы."


class GAME_TEXT:
    CHOOSE = "🎮 Выберите игру:"
    PRIVATE_ONLY = "Эта команда доступна только в чатах (не в ЛС)."


class POKER_TEXT:
    RULES = (
        "<b>♠️ Покер-дуэль</b>\n\n"
        "Простая дуэль: вы и бот тянете по одной карте.\n"
        "Старшая карта забирает ставку. При равенстве — возврат.\n\n"
        "Введите ставку (например: <code>5</code>):"
    )
    INVALID_BET = "❌ Некорректная ставка. Введите число больше нуля."
    BET_TOO_LOW = "❌ Минимальная ставка: <b>{min_bet} {currency}</b>"
    BET_TOO_HIGH = "❌ Максимальная ставка: <b>{max_bet} {currency}</b>"
    INSUFFICIENT = "❌ Недостаточно средств. Ваш баланс: <b>{balance:.2f} {currency}</b>"
    CANCEL = "Игра отменена."

    @classmethod
    def result_win(cls, player_card: str, bot_card: str, amount: Decimal, new_balance: Decimal, currency: str) -> str:
        return (
            f"🃏 Ваша карта: <b>{player_card}</b> | Карта бота: <b>{bot_card}</b>\n\n"
            f"🎉 Вы выиграли <b>+{amount:.2f} {currency}</b>!\n"
            f"Баланс: <b>{new_balance:.2f} {currency}</b>"
        )

    @classmethod
    def result_lose(cls, player_card: str, bot_card: str, amount: Decimal, new_balance: Decimal, currency: str) -> str:
        return (
            f"🃏 Ваша карта: <b>{player_card}</b> | Карта бота: <b>{bot_card}</b>\n\n"
            f"😔 Вы проиграли <b>-{amount:.2f} {currency}</b>.\n"
            f"Баланс: <b>{new_balance:.2f} {currency}</b>"
        )

    @classmethod
    def result_draw(cls, player_card: str, bot_card: str, currency: str) -> str:
        return (
            f"🃏 Ваша карта: <b>{player_card}</b> | Карта бота: <b>{bot_card}</b>\n\n"
            f"🤝 Ничья — ставка возвращена."
        )


class RULES_TEXT:
    BODY = (
        "<b>📋 Правила CEER</b>\n\n"
        "• Баланс единый с CERBER — пополняй там.\n"
        "• Минимальная ставка задаётся администратором.\n"
        "• Игры доступны только в чатах, не в ЛС.\n"
        "• Результаты честные — карты разыгрываются случайно.\n"
        "• Бот не несёт ответственности за проигрыши.\n\n"
        "Удачи! 🍀"
    )
