"""
CERBER Bot Launcher — интерактивный запуск с анимированным ASCII-баннером.

Использование:
    python launcher.py
    python launcher.py --no-tunnel
    python launcher.py --tunnel-only
"""
from __future__ import annotations

import argparse
import math
import os
import random
import re
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

# ── Windows: включаем ANSI escape codes ───────────────────────
if sys.platform == "win32":
    os.system("")
    import msvcrt
else:
    sys.exit("Launcher поддерживает только Windows")

# ── Пути ──────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent
LOG_DIR = ROOT / "logs"
VENV_PY = ROOT / ".venv" / "Scripts" / "python.exe"
ENV_FILE = ROOT / ".env"

LOGS = {
    "bot": LOG_DIR / "bot.log",
    "bot_err": LOG_DIR / "bot_error.log",
    "tunnel": LOG_DIR / "tunnel.log",
    "launcher": LOG_DIR / "launcher.log",
}

# ── ANSI-утилиты ─────────────────────────────────────────────
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"


def rgb(r: int, g: int, b: int) -> str:
    return f"\033[38;2;{r};{g};{b}m"


def _move(row: int, col: int) -> str:
    return f"\033[{row};{col}H"


def _clear():
    sys.stdout.write("\033[2J\033[H")
    sys.stdout.flush()


def _hide_cursor():
    sys.stdout.write("\033[?25l")
    sys.stdout.flush()


def _show_cursor():
    sys.stdout.write("\033[?25h")
    sys.stdout.flush()


def _save_cursor() -> str:
    return "\033[s"


def _restore_cursor() -> str:
    return "\033[u"


def _clamp(v: int, lo: int = 0, hi: int = 255) -> int:
    return max(lo, min(hi, v))


# ── Палитра ───────────────────────────────────────────────────
C = {
    "red": rgb(255, 80, 80),
    "green": rgb(80, 255, 120),
    "yellow": rgb(255, 255, 80),
    "cyan": rgb(80, 230, 255),
    "gray": rgb(110, 110, 130),
    "dark_gray": rgb(80, 80, 80),
    "dark_yellow": rgb(200, 180, 80),
    "dark_cyan": rgb(80, 180, 180),
    "white": rgb(220, 220, 230),
}

# ── ASCII-баннер ──────────────────────────────────────────────
BANNER = [
    r"  ██████╗███████╗██████╗ ██████╗ ███████╗██████╗ ",
    r" ██╔════╝██╔════╝██╔══██╗██╔══██╗██╔════╝██╔══██╗",
    r" ██║     █████╗  ██████╔╝██████╔╝█████╗  ██████╔╝",
    r" ██║     ██╔══╝  ██╔══██╗██╔══██╗██╔══╝  ██╔══██╗",
    r" ╚██████╗███████╗██║  ██║██████╔╝███████╗██║  ██║",
    r"  ╚═════╝╚══════╝╚═╝  ╚═╝╚═════╝ ╚══════╝╚═╝  ╚═╝",
]

# Неоновый градиент: зелёный → бирюзовый (стиль кряков / warez NFO)
CRACK_GRADIENT = [
    (0, 255, 65),
    (0, 240, 90),
    (0, 220, 110),
    (0, 200, 125),
    (0, 180, 105),
    (0, 160, 85),
]

# Символы глитча, шума, «битых пикселей»
GLITCH_BLOCK = "░▒▓█▄▀▐▌╬╫╪"
GLITCH_NOISE = "!@#$%&*<>?/\\|~^;:="

# Цвета артефактов
GLITCH_COLORS = [
    (255, 0, 80),    # розовый
    (0, 255, 255),   # cyan
    (255, 0, 255),   # magenta
    (255, 255, 255), # белый
    (120, 0, 220),   # фиолетовый
    (255, 200, 0),   # тёплый жёлтый
]

# Высота области баннера (строки терминала 1..BANNER_HEIGHT)
BANNER_HEIGHT = len(BANNER) + 3  # banner + пустая строка + subtitle + separator

# Потокобезопасный вывод
_io_lock = threading.Lock()


# ── Непрерывная анимация баннера ──────────────────────────────

class BannerAnimator:
    """Фоновый поток: рисует баннер с глитч-эффектами в стиле битых пикселей."""

    def __init__(self) -> None:
        self._stop_evt = threading.Event()
        self._active = threading.Event()
        self._active.set()  # по умолчанию НЕ на паузе
        self._thread: threading.Thread | None = None
        self._frame = 0

    # ── управление ────────────────────────────────────────────

    def start(self) -> None:
        _hide_cursor()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_evt.set()
        self._active.set()
        if self._thread:
            self._thread.join(timeout=2)
        _show_cursor()

    def pause(self) -> None:
        self._active.clear()

    def resume(self) -> None:
        self._active.set()

    # ── основной цикл ────────────────────────────────────────

    def _loop(self) -> None:
        while not self._stop_evt.is_set():
            self._active.wait()
            if self._stop_evt.is_set():
                break
            self._render()
            self._frame += 1
            self._stop_evt.wait(0.08)  # ~12 FPS

    # ── рендер одного кадра ──────────────────────────────────

    def _render(self) -> None:
        f = self._frame
        buf: list[str] = []

        # === Периодические глобальные события ===
        # «Сбой развёртки» — вся картинка на 1 кадр сдвигается
        global_shift = 0
        if random.random() < 0.005:
            global_shift = random.choice([-3, -2, 2, 3])

        # «Инверсия строки» — одна случайная строка полностью глитчит
        corrupt_row = -1
        if random.random() < 0.012:
            corrupt_row = random.randint(0, len(BANNER) - 1)

        for i, line in enumerate(BANNER):
            row = i + 1
            r0, g0, b0 = CRACK_GRADIENT[min(i, len(CRACK_GRADIENT) - 1)]

            # Медленный пульс яркости
            pulse = math.sin(f * 0.06 + i * 0.4) * 0.15
            r0 = _clamp(int(r0 + 50 * pulse))
            g0 = _clamp(int(g0 + 80 * pulse))
            b0 = _clamp(int(b0 + 50 * pulse))

            # Горизонтальный дрожание (VHS-эффект)
            jitter = global_shift
            if random.random() < 0.018:
                jitter += random.choice([-2, -1, 1, 2])
            col = max(1, 3 + jitter)

            # Скан-линия (яркая полоса бежит сверху вниз)
            scan_pos = (f % 80) / 80.0 * (len(BANNER) + 6) - 2
            scan_dist = abs(i - scan_pos)

            # Полностью «битая» строка?
            is_corrupt = i == corrupt_row

            parts: list[str] = []
            for j, ch in enumerate(line):
                # 1. Глитч отдельных символов (~0.7 % шанс)
                if random.random() < 0.007:
                    gch = random.choice(GLITCH_BLOCK)
                    gr, gg, gb = random.choice(GLITCH_COLORS)
                    parts.append(f"{rgb(gr, gg, gb)}{gch}")
                # 2. Битая строка целиком
                elif is_corrupt:
                    if random.random() < 0.3:
                        gc = random.choice(GLITCH_BLOCK + GLITCH_NOISE)
                        gr, gg, gb = random.choice(GLITCH_COLORS)
                        parts.append(f"{rgb(gr, gg, gb)}{gc}")
                    else:
                        cr, cg, cb = random.choice(GLITCH_COLORS)
                        parts.append(f"{rgb(cr, cg, cb)}{ch}")
                # 3. Скан-линия — яркое свечение
                elif scan_dist < 1.5:
                    t = (1.5 - scan_dist) / 1.5
                    r = _clamp(int(r0 + (255 - r0) * t * 0.6))
                    g = _clamp(int(g0 + (255 - g0) * t * 0.6))
                    b = _clamp(int(b0 + (255 - b0) * t * 0.6))
                    parts.append(f"{rgb(r, g, b)}{ch}")
                # 4. Обычный символ с мягкой волной
                else:
                    wave = math.sin(f * 0.04 + j * 0.12) * 0.08
                    r = _clamp(int(r0 + 40 * wave))
                    g = _clamp(int(g0 + 40 * wave))
                    b = _clamp(int(b0 + 40 * wave))
                    parts.append(f"{rgb(r, g, b)}{ch}")

            # Очищаем до конца строки (\033[K) чтобы артефакты от jitter не оставались
            buf.append(f"{_move(row, col)}{BOLD}{''.join(parts)}{RESET}\033[K")

        # === Подстрочник ===
        sub_row = len(BANNER) + 2
        if random.random() < 0.04:
            variants = [
                "  ░▒▓ C.R.A.C.K.E.D ▓▒░  ",
                "  ▓░▒ CRACKED ▒░▓  ",
                f"  ███ ERR{'O' * random.randint(1, 5)}R ███  ",
                "  ▒░▒ 0xDEADB33F ▒░▒  ",
                "  ░▓▒ NFOFORCE ▒▓░  ",
            ]
            sub_text = random.choice(variants)
            sub_color = rgb(*random.choice(GLITCH_COLORS))
        else:
            sub_text = "  ▓▒░ Bot Launcher ░▒▓  "
            glow = math.sin(f * 0.05) * 0.15
            sr = _clamp(int(0 + 40 * glow))
            sg = _clamp(int(200 + 55 * glow))
            sb = _clamp(int(100 + 40 * glow))
            sub_color = rgb(sr, sg, sb)

        pad = max(0, (52 - len(sub_text)) // 2)
        buf.append(
            f"{_move(sub_row, 3 + pad)}{BOLD}{sub_color}{sub_text}{RESET}\033[K"
        )

        # === Разделитель ===
        sep_row = len(BANNER) + 3
        sep = "─" * 54
        flicker = _clamp(int(60 + 15 * math.sin(f * 0.03)))
        buf.append(f"{_move(sep_row, 3)}{rgb(flicker, flicker, flicker + 10)}{sep}{RESET}")

        with _io_lock:
            sys.stdout.write(_save_cursor() + "".join(buf) + _restore_cursor())
            sys.stdout.flush()


# ── Входная анимация (быстрое «проявление из шума») ──────────

def intro_animation() -> None:
    """Строки баннера проявляются из случайного шума."""
    _hide_cursor()
    _clear()

    for i, line in enumerate(BANNER):
        row = i + 1
        r0, g0, b0 = CRACK_GRADIENT[min(i, len(CRACK_GRADIENT) - 1)]

        # 4 фазы: шум → шум с текстом → почти текст → чистый текст
        for phase in range(4):
            parts: list[str] = []
            for j, ch in enumerate(line):
                noise_chance = [1.0, 0.6, 0.2, 0.0][phase]
                if random.random() < noise_chance:
                    nc = random.choice(GLITCH_BLOCK + GLITCH_NOISE)
                    nr, ng, nb = random.choice(GLITCH_COLORS)
                    parts.append(f"{rgb(nr, ng, nb)}{nc}")
                else:
                    parts.append(f"{rgb(r0, g0, b0)}{ch}")
            sys.stdout.write(f"{_move(row, 3)}{BOLD}{''.join(parts)}{RESET}")
            sys.stdout.flush()
            time.sleep(0.03)

    # Подстрочник
    sub_row = len(BANNER) + 2
    sub_text = "  ▓▒░ Bot Launcher ░▒▓  "
    pad = max(0, (52 - len(sub_text)) // 2)
    print(f"{_move(sub_row, 3 + pad)}{BOLD}{rgb(0, 200, 100)}{sub_text}{RESET}")

    sep_row = len(BANNER) + 3
    sep = "─" * 54
    print(f"{_move(sep_row, 3)}{rgb(60, 60, 70)}{sep}{RESET}")

    # Курсор ниже баннера
    print(f"{_move(BANNER_HEIGHT + 1, 1)}", end="")
    _show_cursor()


# ── Утилиты ──────────────────────────────────────────────────
def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOGS["launcher"], "a", encoding="utf-8") as f:
        f.write(f"{ts}  {msg}\n")


def cprint(msg: str, color: str = "white"):
    with _io_lock:
        print(f"  {C.get(color, '')}{msg}{RESET}")


def read_env_lines() -> list[str]:
    if not ENV_FILE.exists():
        return []
    return ENV_FILE.read_text(encoding="utf-8-sig").splitlines()


def get_env(key: str, default: str = "") -> str:
    for line in read_env_lines():
        m = re.match(rf"^\s*{re.escape(key)}\s*=(.*)", line)
        if m:
            v = m.group(1).strip()
            if v:
                return v
    return default


def set_env(key: str, value: str):
    lines = read_env_lines()
    found = False
    result: list[str] = []
    for ln in lines:
        if re.match(rf"^\s*{re.escape(key)}\s*=", ln):
            result.append(f"{key}={value}")
            found = True
        else:
            result.append(ln)
    if not found:
        result.append(f"{key}={value}")
    ENV_FILE.write_text("\n".join(result) + "\n", encoding="utf-8")


# ── Проверка доступности сервисов и API ──────────────────────

# Целевые хосты для проверки прокси
PROXY_TEST_TARGETS: dict[str, str] = {
    "TELEGRAM_PROXY": "https://api.telegram.org",
    "NICEPAY_PROXY": "https://nicepay.io",
}

# Все внешние сервисы, от которых зависит бот.
# (имя, env-ключ URL, env-ключ прокси или None, URL по умолчанию, env-флаг включения)
SERVICE_CHECKS: list[tuple[str, str, str | None, str, str | None]] = [
    ("Telegram API",  "TELEGRAM_API_URL", "TELEGRAM_PROXY", "https://api.telegram.org", None),
    ("NicePay",       "NICEPAY_BASE_URL", "NICEPAY_PROXY",  "https://nicepay.io",       None),
    ("GiftAPI",       "GIFTAPI_BASE_URL", None,             "https://api.giftapi.io",   None),
]


def _check_url(url: str, proxy_url: str | None = None, timeout: int = 10) -> tuple[bool, int | None, str]:
    """HEAD-запрос к url (опционально через прокси).

    Возвращает (ok, http_status_or_None, message).
    """
    import urllib.request
    import urllib.error

    try:
        if proxy_url:
            handler = urllib.request.ProxyHandler({"http": proxy_url, "https": proxy_url})
            opener = urllib.request.build_opener(handler)
        else:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

        req = urllib.request.Request(url, method="HEAD")
        req.add_header("User-Agent", "CERBER-Launcher/1.0")
        resp = opener.open(req, timeout=timeout)
        return True, resp.status, "OK"
    except urllib.error.HTTPError as exc:
        # HTTP ответ получен (сервер доступен), просто не 2xx
        return True, exc.code, f"HTTP {exc.code}"
    except urllib.error.URLError as exc:
        return False, None, str(exc.reason)
    except Exception as exc:
        return False, None, str(exc)


def check_proxy(proxy_url: str, target_url: str, timeout: int = 10) -> tuple[bool, str]:
    """Обратная совместимость: проверка прокси."""
    if not proxy_url:
        return True, "(пусто — прямое подключение)"
    ok, _status, msg = _check_url(target_url, proxy_url=proxy_url, timeout=timeout)
    return ok, msg


def check_proxy_interactive(key: str, proxy_url: str) -> None:
    """Проверяет прокси и выводит результат пользователю."""
    if not proxy_url:
        return
    target = PROXY_TEST_TARGETS.get(key)
    if not target:
        return
    cprint(f"  ⏳ Проверяю прокси {proxy_url} → {target} ...", "dark_cyan")
    ok, msg = check_proxy(proxy_url, target)
    if ok:
        cprint(f"  ✓ Прокси работает: {msg}", "green")
    else:
        cprint(f"  ✗ Прокси НЕ работает: {msg}", "red")
        cprint("    Бот может не подключиться через этот прокси.", "yellow")


def preflight_check_services() -> None:
    """Проверяет доступность всех внешних сервисов перед запуском бота.

    Для каждого сервиса:
    - Определяет URL из .env (или берёт дефолт)
    - Если есть прокси — проверяет через прокси
    - Если прокси нет — проверяет напрямую
    - Показывает ✓ / ✗ с пояснением
    """
    cprint("[*] Проверка доступности сервисов...", "cyan")
    all_ok = True

    for name, url_key, proxy_key, default_url, enable_key in SERVICE_CHECKS:
        # Пропускаем отключённые сервисы
        if enable_key:
            enabled = get_env(enable_key, "true").lower()
            if enabled not in ("true", "1", "yes"):
                cprint(f"    {name}: пропуск (отключён)", "dark_gray")
                continue

        url = get_env(url_key, default_url) or default_url
        proxy = get_env(proxy_key, "") if proxy_key else ""

        via = f" через прокси {proxy}" if proxy else ""
        cprint(f"    {name} ({url}){via}", "dark_cyan")

        ok, status, msg = _check_url(url, proxy_url=proxy or None, timeout=10)
        if ok:
            status_str = f" [{status}]" if status else ""
            cprint(f"      ✓ Доступен{status_str}", "green")
        else:
            all_ok = False
            cprint(f"      ✗ Недоступен: {msg}", "red")
            if proxy:
                cprint(f"      ⚠ Проверьте прокси {proxy_key} в .env", "yellow")
            else:
                cprint("      ⚠ Проверьте интернет, VPN или настройте прокси в .env", "yellow")

    if all_ok:
        cprint("[OK] Все сервисы доступны.", "green")
    else:
        cprint("[!] Некоторые сервисы недоступны. Бот может работать с ограничениями.", "yellow")

    with _io_lock:
        print()


def wait_tunnel_url(log_file: Path, timeout: int = 30) -> Optional[str]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if log_file.exists():
            content = log_file.read_text(encoding="utf-8", errors="replace")
            m = re.search(r"(https://[a-zA-Z0-9\-]+\.trycloudflare\.com)", content)
            if m:
                return m.group(1)
        time.sleep(0.5)
    return None


# ── Описания переменных для интерактивного wizard'а ───────────
# Каждая запись: (ключ, описание, подсказка/варианты, значение по умолчанию)
# Группируем по секциям для удобного вывода.

ENV_SECTIONS: list[tuple[str, list[tuple[str, str, str, str]]]] = [
    ("Telegram Bot", [
        (
            "BOT_TOKEN",
            "Токен бота от @BotFather. Без него бот не запустится.",
            "Формат: 123456789:ABCdefGHIjklMNOpqrSTUvwxYZ",
            "",
        ),
        (
            "ADMIN_BOT_TOKEN",
            "Токен второго бота для админки, диспутов и оповещений модераторам.\n"
            "    Пусто — модерация остаётся в основном боте.\n"
            "    Задайте токен — появится отдельный бот с панелью для модераторов.",
            "Формат: 123456789:ABCdefGHIjklMNOpqrSTUvwxYZ (или пусто)",
            "",
        ),
        (
            "BOT_USERNAME",
            "Username бота без @. Нужен для Telegram Login Widget в веб-панели.",
            "Например: cerber_shop_bot",
            "",
        ),
        (
            "SUPPORT_URL",
            "Ссылка на аккаунт поддержки. Показывается пользователям в боте.",
            "Формат: https://t.me/ваш_аккаунт",
            "https://t.me/cerber_support",
        ),
    ]),
    ("База данных", [
        (
            "DATABASE_URL",
            "Строка подключения к БД.\n"
            "    SQLite (по умолчанию) — данные в файле, без отдельного сервера.\n"
            "    PostgreSQL — для продакшена с высокой нагрузкой.",
            "SQLite: sqlite+aiosqlite:///./data/cerber.db\n"
            "    PostgreSQL: postgresql+asyncpg://user:pass@localhost:5432/cerber",
            "sqlite+aiosqlite:///./data/cerber.db",
        ),
    ]),
    ("Валюта и платежи", [
        (
            "WALLET_CURRENCY",
            "Основная валюта кошелька пользователя.\n"
            "    RUB — рубли, USD — доллары. Влияет на отображение баланса и цен.",
            "RUB / USD",
            "RUB",
        ),
        (
            "PAYMENTS_CURRENCY",
            "Валюта, в которой проходят платежи через NicePay.",
            "RUB / USD",
            "RUB",
        ),
        (
            "PAYMENTS_MIN_AMOUNT",
            "Минимальная сумма пополнения кошелька.",
            "Число, например: 100",
            "100",
        ),
        (
            "PAYMENTS_MAX_AMOUNT",
            "Максимальная сумма пополнения кошелька.",
            "Число, например: 10000",
            "10000",
        ),
    ]),
    ("NicePay (платёжный шлюз)", [
        (
            "NICEPAY_BASE_URL",
            "Базовый URL API NicePay.",
            "https://nicepay.io",
            "https://nicepay.io",
        ),
        (
            "NICEPAY_MERCHANT_ID",
            "Merchant ID из личного кабинета NicePay. Без него пополнение не работает.",
            "Строка из личного кабинета NicePay",
            "",
        ),
        (
            "NICEPAY_SECRET",
            "Секретный ключ NicePay для подписи запросов.",
            "Строка из личного кабинета NicePay",
            "",
        ),
        (
            "NICEPAY_PROXY",
            "Прокси только для запросов к NicePay.\n"
            "    Оставьте пустым, если прямое подключение работает.\n"
            "    Полезно, когда NicePay недоступен без VPN/прокси.",
            "Пусто / socks5://127.0.0.1:1080 / http://host:port",
            "",
        ),
        (
            "NICEPAY_METHOD",
            "Метод оплаты по умолчанию. Пусто = NicePay покажет выбор пользователю.",
            "Пусто / card_rub / paypal_usd / crypto_usdt и др.",
            "",
        ),
        (
            "NICEPAY_WEBHOOK_PORT",
            "Порт, на котором бот слушает callback от NicePay.",
            "Число, по умолчанию 8080",
            "8080",
        ),
    ]),
    ("GiftAPI (каталог товаров)", [
        (
            "GIFTAPI_BASE_URL",
            "URL API GiftAPI.\n"
            "    Sandbox — для тестов (заказы не списывают деньги).\n"
            "    Production — реальные заказы.",
            "Sandbox: https://sandbox.giftapi.io/api/v1/partner\n"
            "    Production: https://api.giftapi.io/v1/partner",
            "https://api.giftapi.io/v1/partner",
        ),
        (
            "GIFTAPI_TOKEN",
            "API-токен партнёра GiftAPI.",
            "Строка из партнёрского кабинета GiftAPI",
            "",
        ),
        (
            "GIFTAPI_SECRET",
            "Секрет для HMAC-подписи заказов GiftAPI.",
            "Строка из партнёрского кабинета GiftAPI",
            "",
        ),
    ]),
    ("Web-панель и Mini App", [
        (
            "WEB_ENABLED",
            "Включить веб-панель (витрина, профиль, кошелёк через браузер).\n"
            "    true — панель доступна на WEB_PORT.\n"
            "    false — только Telegram-бот, без веб-интерфейса.",
            "true / false",
            "true",
        ),
        (
            "WEB_PORT",
            "Порт веб-панели. Также используется Cloudflare Tunnel.",
            "Число, по умолчанию 8088",
            "8088",
        ),
        (
            "WEB_BASE_URL",
            "Публичный HTTPS URL для Telegram Mini App.\n"
            "    Заполняется автоматически при запуске через Cloudflare Tunnel.\n"
            "    Оставьте пустым, если не используете Mini App.",
            "Пусто / https://xxx.trycloudflare.com",
            "",
        ),
    ]),
    ("Прокси для Telegram (при блокировке)", [
        (
            "TELEGRAM_PROXY",
            "Прокси для подключения бота к Telegram API.\n"
            "    Пусто — прямое подключение.\n"
            "    Нужен, если api.telegram.org заблокирован в вашей сети.",
            "Пусто / socks5://user:pass@host:port / http://host:port",
            "",
        ),
        (
            "TELEGRAM_API_URL",
            "Кастомный URL Telegram Bot API.\n"
            "    Пусто — стандартный api.telegram.org.\n"
            "    Используйте, если запускаете локальный Telegram Bot API сервер.",
            "Пусто / http://localhost:8081",
            "",
        ),
    ]),
    ("Дополнительно", [
        (
            "MODERATOR_IDS",
            "Telegram ID модераторов через запятую. Могут принимать сделки.",
            "Например: 123456789,987654321",
            "",
        ),
        (
            "REQUEST_TIMEOUT_SECONDS",
            "Таймаут HTTP-запросов к внешним API (секунды).",
            "Число, по умолчанию 15",
            "15",
        ),
        (
            "CATALOG_CACHE_TTL",
            "Время кеширования каталога товаров (секунды).\n"
            "    Чем больше — тем реже обращения к GiftAPI, но медленнее обновляется ассортимент.",
            "Число, по умолчанию 120",
            "120",
        ),
    ]),
]


def _mask_secret(value: str) -> str:
    """Маскирует секретные значения для отображения."""
    if not value or len(value) < 8:
        return value
    return value[:4] + "***" + value[-3:]


def _is_secret_key(key: str) -> bool:
    return any(s in key for s in ("TOKEN", "SECRET", "MERCHANT_ID"))


def env_wizard():
    """Интерактивный мастер настройки .env с пояснениями по каждой переменной."""
    sep = "─" * 54
    print()
    print(f"  {C['cyan']}{sep}{RESET}")
    print(f"  {BOLD}{C['white']}       Настройка .env{RESET}")
    print(f"  {C['cyan']}{sep}{RESET}")
    print()
    cprint("Для каждой переменной показаны:", "gray")
    cprint("  — описание и назначение", "gray")
    cprint("  — допустимые варианты", "gray")
    cprint("  — текущее значение (Enter = оставить как есть)", "gray")
    cprint("  — введите 'skip' чтобы пропустить оставшуюся секцию", "gray")
    print()

    changed = 0
    for section_name, variables in ENV_SECTIONS:
        print(f"  {BOLD}{C['yellow']}── {section_name} ──{RESET}")
        print()
        skip_section = False

        for key, description, hint, default in variables:
            if skip_section:
                break

            current = get_env(key, "")
            display_current = current if not _is_secret_key(key) else _mask_secret(current)

            # Описание
            for desc_line in description.split("\n"):
                print(f"    {C['white']}{desc_line}{RESET}")

            # Варианты
            for hint_line in hint.split("\n"):
                print(f"    {C['dark_cyan']}Варианты: {hint_line}{RESET}")

            # Текущее значение
            if current:
                print(f"    {C['green']}Текущее:  {display_current}{RESET}")
            elif default:
                print(f"    {C['gray']}По умолчанию: {default}{RESET}")
            else:
                print(f"    {C['gray']}Текущее:  (не задано){RESET}")

            # Ввод
            try:
                answer = input(f"  {C['dark_yellow']}{key}={RESET}").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                cprint("Настройка прервана. Изменения сохранены.", "yellow")
                return changed

            if answer.lower() == "skip":
                skip_section = True
                print()
                continue

            if answer:
                set_env(key, answer)
                changed += 1
                cprint(f"  ✓ {key} обновлён", "green")
                # Проверяем прокси сразу после ввода
                if key in PROXY_TEST_TARGETS:
                    check_proxy_interactive(key, answer)
            else:
                # Оставляем текущее; если нет текущего и есть default, ставим default
                if not current and default:
                    set_env(key, default)
                    changed += 1
                    cprint(f"  ✓ {key} = {default} (по умолчанию)", "gray")

            print()

        print()

    print(f"  {C['cyan']}{sep}{RESET}")
    if changed:
        cprint(f"Обновлено переменных: {changed}", "green")
    else:
        cprint("Ничего не изменено.", "gray")
    print(f"  {C['cyan']}{sep}{RESET}")
    print()
    return changed


# ── UI ────────────────────────────────────────────────────────
def show_tail(filepath: Path, lines: int = 30, label: str = ""):
    with _io_lock:
        print()
        print(f"  {C['cyan']}=== {label} (last {lines} lines) ==={RESET}")
        print(f"  {C['dark_gray']}File: {filepath}{RESET}")
        print()
        if filepath.exists():
            all_lines = filepath.read_text(encoding="utf-8", errors="replace").splitlines()
            tail = all_lines[-lines:] if len(all_lines) > lines else all_lines
            if tail:
                for ln in tail:
                    print(f"    {ln}")
            else:
                print(f"    {C['dark_gray']}(empty){RESET}")
        else:
            print(f"    {C['dark_gray']}(file not found){RESET}")
        print()


def show_status(
    components: list[tuple[str, subprocess.Popen[bytes]]],
    tunnel_url: str | None,
):
    with _io_lock:
        print()
        print(f"  {C['cyan']}=== Component Status ==={RESET}")
        print()
        for name, proc in components:
            if proc.poll() is not None:
                print(f"    {C['red']}[{name}] STOPPED (exit code {proc.returncode}){RESET}")
            else:
                print(f"    {C['green']}[{name}] RUNNING (PID {proc.pid}){RESET}")
        if tunnel_url:
            print()
            print(f"    {C['dark_cyan']}Tunnel URL: {tunnel_url}{RESET}")
        print()


def show_menu():
    with _io_lock:
        sep = "─" * 42
        print(f"  {C['gray']}{sep}{RESET}")
        print(f"  {C['white']}  [1] Bot log          [4] Status{RESET}")
        print(f"  {C['white']}  [2] Bot errors       [5] Clear screen{RESET}")
        print(f"  {C['white']}  [3] Tunnel log       [Q] Quit{RESET}")
        print(f"  {C['white']}  [6] Launcher log     [R] Restart bot{RESET}")
        print(f"  {C['gray']}{sep}{RESET}")


def read_key() -> str:
    """Неблокирующее чтение клавиши (Windows)."""
    if msvcrt.kbhit():
        return msvcrt.getwch()
    return ""


# ── Завершение старых процессов ──────────────────────────────

def _find_pids_by_cmdline(pattern: str) -> list[int]:
    """Ищет PID процессов, чья командная строка содержит pattern."""
    pids: list[int] = []

    # Попытка 1: PowerShell Get-CimInstance (надёжно в Windows 10/11)
    try:
        ps_cmd = (
            "Get-CimInstance Win32_Process | "
            f"Where-Object {{ $_.CommandLine -like '*{pattern}*' }} | "
            "ForEach-Object { $_.ProcessId }"
        )
        res = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if res.returncode == 0:
            for line in res.stdout.splitlines():
                if line.strip().isdigit():
                    pids.append(int(line.strip()))
            return pids
    except Exception:
        pass

    # Попытка 2: WMIC (устарел в Windows 11 24H2, используется как fallback)
    try:
        res = subprocess.run(
            ["wmic", "process", "get", "commandline,processid", "/format:csv"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if res.returncode == 0:
            for line in res.stdout.splitlines():
                if pattern.lower() not in line.lower():
                    continue
                parts = line.rsplit(",", 1)
                if len(parts) == 2 and parts[1].strip().isdigit():
                    pids.append(int(parts[1].strip()))
    except Exception:
        pass

    return pids


def kill_old_launchers() -> None:
    """Завершает предыдущие экземпляры launcher.py, cerber_bot и cloudflared."""
    current_pid = os.getpid()
    killed: list[int] = []

    for pattern in ("launcher.py", "cerber_bot"):
        for pid in _find_pids_by_cmdline(pattern):
            if pid == current_pid:
                continue
            try:
                subprocess.run(
                    ["taskkill", "/F", "/PID", str(pid)],
                    capture_output=True,
                    timeout=5,
                )
                killed.append(pid)
            except Exception:
                pass

    # cloudflared завершить по имени исполняемого файла
    try:
        subprocess.run(
            ["taskkill", "/F", "/IM", "cloudflared.exe"],
            capture_output=True,
            timeout=5,
        )
    except Exception:
        pass

    if killed:
        log(f"Завершены старые процессы: PID {', '.join(map(str, killed))}")


# ── Запуск / перезапуск бота ─────────────────────────────────

def _start_bot(
    components: list[tuple[str, subprocess.Popen[bytes]]],
    open_files: list,
    web_port: str,
    web_enabled: str,
    tunnel_url: str | None,
) -> None:
    """Запускает процесс бота и добавляет его в components/open_files."""
    cprint("[*] Starting bot...", "cyan")
    log("Starting bot")

    if web_enabled == "true":
        cprint(f"    Web: http://localhost:{web_port}", "dark_cyan")
        if tunnel_url:
            cprint(f"    Mini App: {tunnel_url}", "dark_cyan")

    bf = open(LOGS["bot"], "w", encoding="utf-8")
    ef = open(LOGS["bot_err"], "w", encoding="utf-8")
    open_files.extend([bf, ef])

    bot_proc = subprocess.Popen(
        [str(VENV_PY), "-m", "cerber_bot"],
        cwd=str(ROOT),
        stdout=bf,
        stderr=ef,
    )
    components.append(("Bot", bot_proc))
    time.sleep(2)
    log(f"Bot started (PID {bot_proc.pid})")


def _restart_bot(
    components: list[tuple[str, subprocess.Popen[bytes]]],
    open_files: list,
    web_port: str,
    web_enabled: str,
    tunnel_url: str | None,
) -> None:
    """Останавливает текущий процесс бота и запускает новый."""
    bot_log_paths = {LOGS["bot"], LOGS["bot_err"]}

    # Остановить старый процесс бота
    bot_entries = [(name, proc) for name, proc in components if name == "Bot"]
    for name, proc in bot_entries:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        components.remove((name, proc))
        log(f"Bot PID {proc.pid} остановлен для перезапуска")

    # Закрыть только лог-файлы бота (не трогать лог туннеля)
    to_close = [
        f for f in open_files
        if Path(getattr(f, "name", "")) in bot_log_paths
    ]
    for f in to_close:
        try:
            f.close()
        except Exception:
            pass
        open_files.remove(f)

    # Запустить новый процесс бота
    _start_bot(components, open_files, web_port, web_enabled, tunnel_url)


# ── Главная логика ────────────────────────────────────────────
def main(no_tunnel: bool = False, tunnel_only: bool = False) -> int:
    LOG_DIR.mkdir(exist_ok=True)

    # Сброс логов
    for lf in LOGS.values():
        lf.write_text("", encoding="utf-8")

    # Завершить старые экземпляры перед новым запуском
    kill_old_launchers()

    # Вступительная анимация (проявление из шума)
    intro_animation()

    # ── Выбор: настроить .env или запустить сразу ─────────────
    sep = "─" * 54
    print(f"\n  {C['cyan']}{sep}{RESET}")
    print(f"  {BOLD}{C['white']}  [1] Запустить бота{RESET}")
    print(f"  {BOLD}{C['white']}  [2] Настроить .env  →  затем запуск{RESET}")
    print(f"  {C['cyan']}{sep}{RESET}")
    print()

    while True:
        try:
            choice = input(f"  {C['dark_yellow']}Выбор (1/2): {RESET}").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if choice in ("1", "2", ""):
            break
        cprint("  Введите 1 или 2", "yellow")

    if choice == "2":
        env_wizard()

    # Запускаем непрерывную анимацию баннера в фоне
    animator = BannerAnimator()
    animator.start()

    try:
        return _run(animator, no_tunnel, tunnel_only)
    finally:
        animator.stop()


def _run(
    animator: BannerAnimator,
    no_tunnel: bool,
    tunnel_only: bool,
) -> int:
    # Предварительные проверки
    if not VENV_PY.exists():
        cprint(
            "[!] .venv not found. Run: python -m venv .venv && pip install -e .[dev]",
            "red",
        )
        return 1

    if not ENV_FILE.exists():
        cprint("[!] .env not found. Run: Copy-Item .env.example .env", "red")
        return 1

    token = get_env("BOT_TOKEN")
    if not token or token == "your_bot_token_from_botfather":
        cprint("[!] BOT_TOKEN not set in .env", "red")
        return 1

    log("Launcher started")

    # ── Проверка доступности сервисов ─────────────────────────
    preflight_check_services()

    web_port = get_env("WEB_PORT", "8088")
    web_enabled = get_env("WEB_ENABLED", "true")

    components: list[tuple[str, subprocess.Popen[bytes]]] = []
    tunnel_url: str | None = None
    open_files: list = []

    try:
        # ── 1. Cloudflare Tunnel ──────────────────────────────
        start_tunnel = (not no_tunnel) and (web_enabled == "true")
        if start_tunnel:
            if not shutil.which("cloudflared"):
                cprint("[*] cloudflared not found in PATH", "yellow")
                log("cloudflared not found")
            else:
                cprint(f"[*] Starting Cloudflare Tunnel on port {web_port}...", "cyan")
                log(f"Starting tunnel on port {web_port}")

                tf = open(LOGS["tunnel"], "w", encoding="utf-8")
                open_files.append(tf)
                tunnel_proc = subprocess.Popen(
                    ["cloudflared", "tunnel", "--url", f"http://localhost:{web_port}"],
                    stderr=tf,
                    stdout=subprocess.DEVNULL,
                )
                components.append(("Tunnel", tunnel_proc))

                cprint("    Waiting for tunnel URL...", "dark_cyan")
                tunnel_url = wait_tunnel_url(LOGS["tunnel"])
                if tunnel_url:
                    cprint(f"    Tunnel: {tunnel_url}", "green")
                    set_env("WEB_BASE_URL", tunnel_url)
                    cprint("    .env updated automatically", "dark_cyan")
                    log(f"Tunnel URL: {tunnel_url} -> .env")
                else:
                    cprint(
                        "    [!] Tunnel URL not detected (timeout 30s)", "yellow"
                    )
                    log("Tunnel URL detection timeout")
                with _io_lock:
                    print()

        # ── 2. Bot + Web ──────────────────────────────────────
        if not tunnel_only:
            _start_bot(components, open_files, web_port, web_enabled, tunnel_url)

        with _io_lock:
            print()
        cprint("[OK] All components started.", "green")
        cprint(f"    Logs: {LOG_DIR}", "dark_gray")
        with _io_lock:
            print()
        log("All components running")

        # ── Интерактивное меню ────────────────────────────────
        show_menu()
        last_check = time.time()

        while True:
            with _io_lock:
                sys.stdout.write(f"\r  {C['dark_yellow']}> {RESET}")
                sys.stdout.flush()

            ch = ""
            while not ch:
                ch = read_key()
                if not ch:
                    if time.time() - last_check > 5:
                        for name, proc in components:
                            if proc.poll() is not None:
                                with _io_lock:
                                    print()
                                cprint(
                                    f"[!] {name} exited (code {proc.returncode})",
                                    "red",
                                )
                                log(f"{name} exited unexpectedly: {proc.returncode}")
                        last_check = time.time()
                    time.sleep(0.1)

            with _io_lock:
                print(ch)

            match ch.lower():
                case "1":
                    animator.pause()
                    show_tail(LOGS["bot"], 40, "Bot Output")
                    show_menu()
                    animator.resume()
                case "2":
                    animator.pause()
                    show_tail(LOGS["bot_err"], 40, "Bot Errors")
                    show_menu()
                    animator.resume()
                case "3":
                    animator.pause()
                    show_tail(LOGS["tunnel"], 40, "Cloudflare Tunnel")
                    show_menu()
                    animator.resume()
                case "4":
                    animator.pause()
                    show_status(components, tunnel_url)
                    show_menu()
                    animator.resume()
                case "5":
                    _clear()
                    # Курсор ниже области баннера
                    with _io_lock:
                        sys.stdout.write(f"{_move(BANNER_HEIGHT + 1, 1)}")
                        sys.stdout.flush()
                    show_menu()
                    # Анимация продолжается — баннер перерисуется сам
                case "6":
                    animator.pause()
                    show_tail(LOGS["launcher"], 40, "Launcher")
                    show_menu()
                    animator.resume()
                case "r":
                    animator.pause()
                    cprint("[*] Перезапускаю бота...", "yellow")
                    log("Перезапуск бота по запросу пользователя")
                    _restart_bot(components, open_files, web_port, web_enabled, tunnel_url)
                    bot_pid = next(
                        (proc.pid for name, proc in components if name == "Bot"), None
                    )
                    if bot_pid:
                        cprint(f"    Бот перезапущен (PID {bot_pid})", "green")
                        log(f"Бот перезапущен PID {bot_pid}")
                    show_menu()
                    animator.resume()
                case "q":
                    raise KeyboardInterrupt
                case _:
                    cprint("Unknown key. Press 1-6, R or Q.", "dark_gray")

    except KeyboardInterrupt:
        pass
    finally:
        with _io_lock:
            print()
        cprint("[*] Shutting down...", "yellow")
        log("Shutdown")

        for name, proc in components:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                cprint(f"    Stopped: {name} (PID {proc.pid})", "dark_yellow")
                log(f"Stopped {name} PID {proc.pid}")

        for f in open_files:
            try:
                f.close()
            except Exception:
                pass

        with _io_lock:
            print()
        cprint(f"[OK] Done. Logs saved in: {LOG_DIR}", "green")
        log("Launcher stopped")

    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CERBER Bot Launcher")
    parser.add_argument("--no-tunnel", action="store_true", help="Не запускать tunnel")
    parser.add_argument(
        "--tunnel-only", action="store_true", help="Запустить только tunnel"
    )
    args = parser.parse_args()
    sys.exit(main(no_tunnel=args.no_tunnel, tunnel_only=args.tunnel_only))
