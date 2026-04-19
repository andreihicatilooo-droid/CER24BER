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


class TTT_TEXT:
    ASK_BET = (
        "<b>❌⭕ Крестики-нолики</b>\n\n"
        "Игра один на один. Введите ставку (или 0 чтобы играть без ставки):\n"
        "<i>Минимальная: {min_bet}, Максимальная: {max_bet} {currency}</i>"
    )
    INVALID_BET = "❌ Некорректная ставка. Введите число ≥ 0."
    BET_TOO_LOW = "❌ Минимальная ставка: <b>{min_bet} {currency}</b>"
    BET_TOO_HIGH = "❌ Максимальная ставка: <b>{max_bet} {currency}</b>"
    INSUFFICIENT = "❌ Недостаточно средств. Баланс: <b>{balance:.2f} {currency}</b>"
    CANCEL = "Игра отменена."

    @staticmethod
    def invite(creator_name: str, bet: Decimal, currency: str) -> str:
        bet_str = f" — ставка <b>{bet:.2f} {currency}</b>" if bet > 0 else " — без ставки"
        return (
            f"⚔️ <b>{creator_name}</b> вызывает на <b>крестики-нолики</b>{bet_str}!\n"
            "Нажми кнопку ниже чтобы принять вызов."
        )

    @staticmethod
    def board(game_x: str, game_o: str, turn_name: str, bet: Decimal, currency: str) -> str:
        bet_str = f"Ставка: <b>{bet:.2f} {currency}</b>\n" if bet > 0 else ""
        return (
            f"❌⭕ <b>Крестики-нолики</b>\n"
            f"{bet_str}"
            f"✕ {game_x}  |  ◯ {game_o}\n\n"
            f"Ход: <b>{turn_name}</b>"
        )

    @staticmethod
    def win(winner_name: str, bet: Decimal, currency: str, new_balance: Decimal) -> str:
        reward = f"\n🏆 +<b>{bet * 2:.2f} {currency}</b> → баланс: <b>{new_balance:.2f}</b>" if bet > 0 else ""
        return f"🎉 Победил <b>{winner_name}</b>!{reward}"

    DRAW = "🤝 <b>Ничья!</b> Ставки возвращены."
    NOT_YOUR_TURN = "Сейчас не ваш ход!"
    NOT_A_PLAYER = "Вы не участник этой игры."
    GAME_NOT_FOUND = "Игра не найдена или уже завершена."
    ALREADY_ACCEPTED = "Игра уже принята."
    CANNOT_ACCEPT_OWN = "Нельзя принять свой собственный вызов."


class BJ_TEXT:
    ASK_BET = (
        "<b>🃏 Блэкджек</b>\n\n"
        "Игра для двоих. Карты открытые. Ближе к 21 — побеждает!\n"
        "Туз = 11 (или 1 при перебое). J/Q/K = 10.\n\n"
        "Введите ставку (0 — без ставки):\n"
        "<i>Мин: {min_bet}, Макс: {max_bet} {currency}</i>"
    )
    INVALID_BET    = "❌ Некорректная ставка. Введите число ≥ 0."
    BET_TOO_LOW    = "❌ Минимальная ставка: <b>{min_bet} {currency}</b>"
    BET_TOO_HIGH   = "❌ Максимальная ставка: <b>{max_bet} {currency}</b>"
    INSUFFICIENT   = "❌ Недостаточно средств. Баланс: <b>{balance:.2f} {currency}</b>"
    CANCEL         = "Игра отменена."
    NOT_YOUR_TURN  = "Сейчас не ваш ход!"
    NOT_A_PLAYER   = "Вы не участник этой игры."
    GAME_NOT_FOUND = "Игра не найдена или уже завершена."
    ALREADY_ACCEPTED  = "Игра уже принята."
    CANNOT_ACCEPT_OWN = "Нельзя принять свой собственный вызов."

    @staticmethod
    def invite(creator_name: str, bet: Decimal, currency: str) -> str:
        bet_str = f" — ставка <b>{bet:.2f} {currency}</b>" if bet > 0 else " — без ставки"
        return (
            f"🃏 <b>{creator_name}</b> вызывает на <b>Блэкджек</b>{bet_str}!\n"
            "Нажми кнопку чтобы принять вызов."
        )

    @staticmethod
    def board(
        p1_name: str, hand1: list, score1: int,
        p2_name: str, hand2: list, score2: int,
        active_player: int,
        bet: Decimal, currency: str,
    ) -> str:
        from ceer_bot.games.blackjack import hand_display
        bet_str  = f"Ставка: <b>{bet:.2f} {currency}</b>\n" if bet > 0 else ""
        bust1    = " 💥" if score1 > 21 else ""
        bust2    = " 💥" if score2 > 21 else ""
        arrow1   = " ← ход" if active_player == 1 else ""
        arrow2   = " ← ход" if active_player == 2 else ""
        turn_name = p1_name if active_player == 1 else p2_name
        return (
            f"🃏 <b>Блэкджек</b>\n{bet_str}"
            f"──────────────────\n"
            f"✕ {p1_name}: {hand_display(hand1)}  [{score1}{bust1}]{arrow1}\n"
            f"◯ {p2_name}: {hand_display(hand2)}  [{score2}{bust2}]{arrow2}\n"
            f"──────────────────\n"
            f"Ход: <b>{turn_name}</b>"
        )

    @staticmethod
    def result(
        winner_name: str | None,
        p1_name: str, hand1: list, score1: int,
        p2_name: str, hand2: list, score2: int,
        bet: Decimal, currency: str, new_balance: Decimal,
    ) -> str:
        from ceer_bot.games.blackjack import hand_display
        bust1 = " 💥" if score1 > 21 else ""
        bust2 = " 💥" if score2 > 21 else ""
        if winner_name:
            reward = (
                f"\n🏆 +<b>{bet * 2:.2f} {currency}</b> → баланс: <b>{new_balance:.2f}</b>"
                if bet > 0 else ""
            )
            outcome = f"🎉 Победил <b>{winner_name}</b>!{reward}"
        else:
            outcome = "🤝 <b>Ничья!</b> Ставки возвращены."
        return (
            f"🃏 <b>Блэкджек — конец игры</b>\n"
            f"──────────────────\n"
            f"✕ {p1_name}: {hand_display(hand1)}  [{score1}{bust1}]\n"
            f"◯ {p2_name}: {hand_display(hand2)}  [{score2}{bust2}]\n"
            f"──────────────────\n"
            f"{outcome}"
        )


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
