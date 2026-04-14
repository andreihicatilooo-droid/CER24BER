"""
CERBER Bot Launcher — интерактивный запуск с анимированным ASCII-баннером.

Использование:
    python launcher.py
    python launcher.py --no-tunnel
    python launcher.py --tunnel-only
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
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


def rgb(r: int, g: int, b: int) -> str:
    return f"\033[38;2;{r};{g};{b}m"


def _move(row: int, col: int) -> str:
    return f"\033[{row};{col}H"


def _clear():
    print("\033[2J\033[H", end="", flush=True)


def _hide_cursor():
    print("\033[?25l", end="", flush=True)


def _show_cursor():
    print("\033[?25h", end="", flush=True)


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

# Огненный градиент: тёмно-красный → алый → оранжевый → жёлтый
FIRE = [
    (140, 20, 0),
    (200, 40, 0),
    (240, 80, 0),
    (255, 130, 10),
    (255, 180, 40),
    (255, 220, 80),
]


def _fire_color(row: int) -> tuple[int, int, int]:
    return FIRE[min(row, len(FIRE) - 1)]


# ── Анимация баннера ──────────────────────────────────────────
def animate_banner():
    """Огненная анимация ASCII-баннера CERBER."""
    _hide_cursor()
    _clear()

    try:
        # Фаза 1 — построчное появление
        for i, line in enumerate(BANNER):
            r, g, b = _fire_color(i)
            print(f"  {BOLD}{rgb(r, g, b)}{line}{RESET}")
            time.sleep(0.07)

        # Фаза 2 — бегущий блик слева направо (2 волны)
        banner_row = 1  # 1-based
        line_len = max(len(l) for l in BANNER)

        for wave in range(2):
            step = 3 if wave == 0 else 4
            for wave_pos in range(-8, line_len + 10, step):
                for i, line in enumerate(BANNER):
                    r0, g0, b0 = _fire_color(i)
                    parts: list[str] = []
                    for j, ch in enumerate(line):
                        dist = abs(j - wave_pos)
                        if dist < 7:
                            t = (7 - dist) / 7.0
                            r = min(255, int(r0 + (255 - r0) * t * 0.8))
                            g = min(255, int(g0 + (255 - g0) * t * 0.8))
                            b = min(255, int(b0 + (255 - b0) * t * 0.8))
                            parts.append(f"{rgb(r, g, b)}{ch}")
                        else:
                            parts.append(f"{rgb(r0, g0, b0)}{ch}")
                    print(
                        f"{_move(banner_row + i, 3)}{BOLD}{''.join(parts)}{RESET}",
                        end="",
                    )
                sys.stdout.flush()
                time.sleep(0.012)

        # Фаза 3 — пульс (2 вспышки: ярче → тише)
        for pulse in range(2):
            for brightness in (0.5, 0.25, 0.0):
                for i, line in enumerate(BANNER):
                    r0, g0, b0 = _fire_color(i)
                    r = min(255, int(r0 + (255 - r0) * brightness))
                    g = min(255, int(g0 + (255 - g0) * brightness))
                    b = min(255, int(b0 + (255 - b0) * brightness))
                    print(
                        f"{_move(banner_row + i, 3)}{BOLD}{rgb(r, g, b)}{line}{RESET}",
                        end="",
                    )
                sys.stdout.flush()
                time.sleep(0.05)

        # Финальный вид
        for i, line in enumerate(BANNER):
            r, g, b = _fire_color(i)
            print(
                f"{_move(banner_row + i, 3)}{BOLD}{rgb(r, g, b)}{line}{RESET}",
                end="",
            )

        # Курсор под баннер
        below = banner_row + len(BANNER) + 1
        print(f"{_move(below, 1)}", end="")

        sep = "─" * 54
        print(f"  {C['gray']}{sep}{RESET}")
        print(f"  {BOLD}{C['white']}          Bot Launcher{RESET}")
        print(f"  {C['gray']}{sep}{RESET}")
        print()
    finally:
        _show_cursor()


def print_static_banner():
    """Статичный баннер (для Clear screen)."""
    for i, line in enumerate(BANNER):
        r, g, b = _fire_color(i)
        print(f"  {BOLD}{rgb(r, g, b)}{line}{RESET}")
    print()


# ── Утилиты ──────────────────────────────────────────────────
def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOGS["launcher"], "a", encoding="utf-8") as f:
        f.write(f"{ts}  {msg}\n")


def cprint(msg: str, color: str = "white"):
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
            "ENABLE_GIFTAPI_PROVIDER",
            "Включить каталог GiftAPI (подарочные карты, eSIM и др.).\n"
            "    true — товары GiftAPI появятся в витрине бота.\n"
            "    false — каталог GiftAPI отключён.",
            "true / false",
            "true",
        ),
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
            "ENABLE_DEMO_PROVIDER",
            "Демо-провайдер каталога с тестовыми товарами.\n"
            "    true — в витрине появятся демо-товары (для проверки).\n"
            "    false — только реальные провайдеры.",
            "true / false",
            "false",
        ),
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
    sep = "─" * 42
    print(f"  {C['gray']}{sep}{RESET}")
    print(f"  {C['white']}  [1] Bot log          [4] Status{RESET}")
    print(f"  {C['white']}  [2] Bot errors       [5] Clear screen{RESET}")
    print(f"  {C['white']}  [3] Tunnel log       [Q] Quit{RESET}")
    print(f"  {C['white']}  [6] Launcher log{RESET}")
    print(f"  {C['gray']}{sep}{RESET}")


def read_key() -> str:
    """Неблокирующее чтение клавиши (Windows)."""
    if msvcrt.kbhit():
        return msvcrt.getwch()
    return ""


# ── Главная логика ────────────────────────────────────────────
def main(no_tunnel: bool = False, tunnel_only: bool = False) -> int:
    LOG_DIR.mkdir(exist_ok=True)

    # Сброс логов
    for lf in LOGS.values():
        lf.write_text("", encoding="utf-8")

    # Анимация баннера
    animate_banner()

    # Предварительные проверки
    if not VENV_PY.exists():
        cprint(
            "[!] .venv not found. Run: python -m venv .venv && pip install -e .[dev]",
            "red",
        )
        return 1

    if not ENV_FILE.exists():
        cprint("[!] .env не найден. Создаю из шаблона...", "yellow")
        example = ROOT / ".env.example"
        if example.exists():
            import shutil as _shutil
            _shutil.copy2(example, ENV_FILE)
            cprint("    .env создан из .env.example", "green")
        else:
            cprint("[!] .env.example тоже не найден. Создайте .env вручную.", "red")
            return 1

    # ── Предложение настроить .env ────────────────────────────
    cprint("Настроить .env перед запуском? (y/n): ", "cyan")
    try:
        choice = input(f"  {C['dark_yellow']}> {RESET}").strip().lower()
    except (EOFError, KeyboardInterrupt):
        choice = "n"

    if choice in ("y", "yes", "д", "да"):
        env_wizard()

    token = get_env("BOT_TOKEN")
    if not token or token == "your_bot_token_from_botfather":
        cprint("[!] BOT_TOKEN not set in .env", "red")
        return 1

    log("Launcher started")

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
                print()

        # ── 2. Bot + Web ──────────────────────────────────────
        if not tunnel_only:
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

        print()
        cprint("[OK] All components started.", "green")
        cprint(f"    Logs: {LOG_DIR}", "dark_gray")
        print()
        log("All components running")

        # ── Интерактивное меню ────────────────────────────────
        show_menu()
        last_check = time.time()

        while True:
            print(f"\r  {C['dark_yellow']}> {RESET}", end="", flush=True)

            ch = ""
            while not ch:
                ch = read_key()
                if not ch:
                    if time.time() - last_check > 5:
                        for name, proc in components:
                            if proc.poll() is not None:
                                print()
                                cprint(
                                    f"[!] {name} exited (code {proc.returncode})",
                                    "red",
                                )
                                log(f"{name} exited unexpectedly: {proc.returncode}")
                        last_check = time.time()
                    time.sleep(0.1)

            print(ch)

            match ch.lower():
                case "1":
                    show_tail(LOGS["bot"], 40, "Bot Output")
                    show_menu()
                case "2":
                    show_tail(LOGS["bot_err"], 40, "Bot Errors")
                    show_menu()
                case "3":
                    show_tail(LOGS["tunnel"], 40, "Cloudflare Tunnel")
                    show_menu()
                case "4":
                    show_status(components, tunnel_url)
                    show_menu()
                case "5":
                    _clear()
                    print_static_banner()
                    show_menu()
                case "6":
                    show_tail(LOGS["launcher"], 40, "Launcher")
                    show_menu()
                case "q":
                    raise KeyboardInterrupt
                case _:
                    cprint("Unknown key. Press 1-6 or Q.", "dark_gray")

    except KeyboardInterrupt:
        pass
    finally:
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
